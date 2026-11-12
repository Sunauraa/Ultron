"""The daily routine with real Claude Code: in a copy of the app, ask exactly what the user asks every morning and
check that CLAUDE.md leads it to run.sh --hours 24, that only the job published within 24 hours is applied to, and
what it reports back.

Postings (as fetch.py would have stored them; companies.txt is empty, so nothing is fetched):
- the recorded Greenhouse Figma page, published 2 hours ago (served offline by bench/replay.py);
- a job published 5 days ago, and an undated job that was in its board's first read: both must be left out, and
  their addresses are never opened (they would be live sites).
Usage: python daily_check.py ["the request"]   Uses your Claude Code login and plan.
"""

import asyncio
import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = HERE.parent.parent
sys.path[:0] = [str(HERE), str(CODE / "bench")]
import drive  # noqa: E402
from replay import Replay  # noqa: E402

OUT = CODE.parent / "tmp" / "daily_check"
PORT = 9334
REQUEST = "submit job applications to those that just published within 24 hours"


async def main(request: str) -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    app = drive.make_app(OUT / "lane", "approval")
    shutil.copy(CODE / "CLAUDE.md", app / "CLAUDE.md")
    folder = CODE / "bench" / "pages" / "greenhouse_figma"
    meta = json.loads((folder / "meta.json").read_text())
    now = datetime.now(timezone.utc)
    ago = lambda **k: (now - timedelta(**k)).isoformat(timespec="seconds")  # noqa: E731
    async with Replay(folder, PORT, OUT / "profile") as replay:
        rows = [
            {"id": "f", "title": meta["title"], "location": meta["location"], "url": replay.url, "board": replay.url, "posted": ago(hours=2),
             "key": "greenhouse:figma:f", "platform": "greenhouse", "company": "figma", "fetched": ago(hours=1)},
            {"id": "old", "title": "Account Executive", "location": "Remote", "url": "https://jobs.lever.co/example-old/1", "posted": ago(days=5),
             "key": "lever:example-old:1", "platform": "lever", "company": "example-old", "fetched": ago(hours=1)},
            {"id": "u", "title": "Support Engineer", "location": "Remote", "url": "https://example.bamboohr.com/careers/9", "posted": "",
             "key": "bamboohr:example:9", "platform": "bamboohr", "company": "example", "fetched": ago(hours=1)},
        ]
        (app / "postings.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (app / "boards_read.json").write_text(json.dumps({"bamboohr:example": ago(hours=1)}))
        env = {**os.environ, "ULTRON_PYTHON": drive.PY, "ULTRON_PORT": str(PORT), "ULTRON_CDP": f"http://127.0.0.1:{PORT}"}
        command = ["claude", "-p", request, "--allowedTools", "Bash(./run.sh:*)", "Bash(python ask.py:*)", "Read",
                   "--max-turns", "30", "--output-format", "json"]
        process = await asyncio.create_subprocess_exec(*command, cwd=app, env=env, stdin=subprocess.DEVNULL,
                                                       stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        output, _ = await asyncio.wait_for(process.communicate(), 2400)
        opened = sorted({p.url for p in replay.context.pages})
    result = json.loads(output.decode() or "{}")
    logged = list(csv.DictReader((app / "applied.csv").open())) if (app / "applied.csv").exists() else []
    record = {"request": request, "claude": result, "applied": logged, "pages_opened": opened,
              "agent_logs": sorted(p.name for p in (app / "logs").glob("*.log"))}
    (OUT / "result.json").write_text(json.dumps(record, indent=1))
    print("REPLY:\n" + str(result.get("result")))
    print("\nturns", result.get("num_turns"), "cost", result.get("total_cost_usd"), "error", result.get("is_error"))
    print("applied.csv:", [(r["company"], r["status"]) for r in logged])
    print("pages opened:", opened)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else REQUEST))
