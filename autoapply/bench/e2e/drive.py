"""End-to-end test of the whole pipeline with a local model standing in for Claude Code.

One lane = one app folder (a frozen copy of autoapply), one CDP port, one LLM server. For each page: the recorded
page is served offline (bench/replay.py), its posting is added to postings.jsonl as fetch.py would write it, and
the real run.sh runs (fetch -> filter -> stand-in `claude` with only Ultron's tools -> mark.py), one job per run.
Afterwards: the row run.sh/Ultron wrote in applied.csv, what the page would have sent, and the score where the page
has gold answers (bench/pages).

Usage: python drive.py LANE MODE LLM_PORT CDP_PORT PAGE [PAGE ...]   MODE: approval | auto_review
Lanes and results go to ../tmp/e2e (beside autoapply); summarise them with analyze.py. The model server used:
  CUDA_VISIBLE_DEVICES=6 python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen3-32B-AWQ --served-model-name local
    --port 8021 --max-model-len 32768 --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3
bin/claude puts claude_standin.py where run.sh calls `claude -p`: the same flags, Ultron's MCP tools only.
"""

import asyncio
import csv
import json
import re
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent.parent  # autoapply
HERE = CODE.parent / "tmp" / "e2e"  # lanes, results (outside the code)
BIN = Path(__file__).resolve().parent / "bin"
sys.path.insert(0, str(CODE / "bench"))
from replay import Replay  # noqa: E402
import score  # noqa: E402

PY = str(CODE.parent / ".venv" / "bin" / "python")
# Pages without a meta.json posting (the wide set): platform, company, title, location as the board lists them.
WIDE = {
    "bamboohr_onezero": ("bamboohr", "onezero", "Desktop Support Engineer", "Somerville, Massachusetts"),
    "gem_gem": ("gem", "Gem", "Engineering Manager (AI Products)", "San Francisco, United States"),
    "personio_f24": ("personio", "F24", "Initiativbewerbung (all genders)", "Wollerau / CH"),
    "teamtailor_teamtailor": ("teamtailor", "Teamtailor", "SMB Account Executive", "Sydney"),
    "site_airbnb": ("greenhouse", "airbnb", "Account Executive (Hotels)", "Barcelona, Spain"),
    "site_databricks": ("greenhouse", "databricks", "Delivery Solutions Architect", "Tokyo, Japan"),
    "site_stripe": ("greenhouse", "stripe", "Abuse Investigator", "Remote"),
    "site_coinbase": ("greenhouse", "coinbase", "Open position", "Remote"),
    "workday_nvidia": ("workday", "nvidia", "Senior engineer", "Zurich, Switzerland"),
}
RUNTIME = ["run.sh", "browser.sh", "fetch.py", "filter.py", "mark.py", "questions.py", "ask.py", "prompt.md", "ultron_mcp.py",
           "popups.py", "jobinfo.py"]


def make_app(lane: Path, mode: str) -> Path:
    app = lane / "app"
    shutil.rmtree(lane, ignore_errors=True)
    app.mkdir(parents=True)
    for name in RUNTIME:
        shutil.copy(CODE / name, app / name)
    for name in ("playbooks", "models"):
        shutil.copytree(CODE / name, app / name)
    shutil.copy(CODE / "bench" / "persona" / "answers.md", app / "answers.md")
    shutil.copy(CODE / "bench" / "persona" / "resume.pdf", app / "resume.pdf")
    (app / "companies.txt").write_text("")
    config = (CODE / "config.example.toml").read_text()
    config = (config.replace('include = ["machine learning", "ML", "AI", "research engineer", "software engineer", "intern", "new grad"]', "include = []")
              .replace('exclude = ["senior", "staff", "principal", "lead", "manager", "director", "head of"]', "exclude = []")
              .replace('locations = ["remote", "san francisco", "new york"]', "locations = []")
              .replace("max_age_days = 30", "max_age_days = 100000")
              .replace("max_jobs_per_run = 5", "max_jobs_per_run = 1"))
    if mode == "auto_review":
        config = config.replace("auto_submit = false", "auto_submit = true").replace("review = false", "review = true")
    assert "include = []" in config and "max_jobs_per_run = 1" in config
    (app / "config.toml").write_text(config)
    return app


async def one(app: Path, lane: Path, name: str, env: dict, cdp: int) -> dict:
    folder = CODE / "bench" / ("pages" if (CODE / "bench" / "pages" / name).exists() else "pages_wide") / name
    meta = json.loads((folder / "meta.json").read_text())
    platform, company, title, location = WIDE.get(name) or (meta["platform"], meta["company"], meta["title"], meta["location"])

    async def run(url: str) -> str:
        # board: the job's form on its board, as fetch.py writes it; for a company's own page, Greenhouse's embed form
        # (not recorded, so a fallback to it finds no form offline).
        token = re.search(r"(?:gh_jid=|/)(\d{6,})\b", url) if name.startswith("site_") else None
        board = f"https://job-boards.greenhouse.io/embed/job_app?for={company}&token={token.group(1)}" if token else url
        posting = {"id": name, "title": title, "location": location, "url": url, "board": board, "posted": meta.get("posted") or "",
                   "key": f"e2e:{name}", "platform": platform, "company": company, "fetched": datetime.now(timezone.utc).isoformat()}
        with (app / "postings.jsonl").open("a") as f:
            f.write(json.dumps(posting) + "\n")
        process = await asyncio.create_subprocess_exec("bash", str(app / "run.sh"), env=env, stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(process.communicate(), 1800)
        return out.decode()[-3000:]

    # The browser is up for every job, as browser.sh keeps it in real use (run.sh never opens a Workday job).
    async with Replay(folder, cdp, lane / "profiles" / name) as replay:
        url = meta["url"] if platform == "workday" else replay.url
        output = await run(url)
        await asyncio.sleep(2)
        sent = list(replay.sent)
    rows = [r for r in csv.DictReader((app / "applied.csv").open())] if (app / "applied.csv").exists() else []
    row = next((r for r in reversed(rows) if r["url"] == url), None)
    scored = score.score(name, sent) if (folder / "fields.json").exists() else None
    return {"page": name, "url": url, "row": row, "sent_count": len(sent), "sent": sent, "score": scored, "run_output": output}


async def main(lane_id: str, mode: str, llm_port: int, cdp: int, pages: list[str]) -> None:
    lane = HERE / "lanes" / f"{mode}_{lane_id}"
    app = make_app(lane, mode)
    env = {"PATH": f"{BIN}:{os.environ['PATH']}", "HOME": str(lane), "E2E_PYTHON": PY, "ULTRON_PYTHON": PY,
           "ULTRON_PORT": str(cdp), "ULTRON_CDP": f"http://127.0.0.1:{cdp}", "LLM_URL": f"http://127.0.0.1:{llm_port}/v1",
           "PLAYWRIGHT_BROWSERS_PATH": os.environ["PLAYWRIGHT_BROWSERS_PATH"], "E2E_SEED": "1", "LANG": "C.UTF-8"}
    out = HERE / "results" / f"{mode}_{lane_id}.jsonl"
    out.parent.mkdir(exist_ok=True)
    out.write_text("")
    for name in pages:
        try:
            result = await one(app, lane, name, env, cdp)
        except Exception as error:
            result = {"page": name, "error": f"{type(error).__name__}: {error}"}
        with out.open("a") as f:
            f.write(json.dumps(result) + "\n")
        print(name, (result.get("row") or {}).get("status"), result.get("error", ""), flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5:]))
