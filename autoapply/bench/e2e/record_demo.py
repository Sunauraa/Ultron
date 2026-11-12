"""Record the demo: real Claude Code applies to one recorded job page, through Ultron and through Playwright MCP.

Both arms get the same page (bench/replay.py: served offline from its recording, nothing reaches the site), the same
fictional applicant (bench/persona) and the same Claude Code flags as run.sh (only the arm's MCP tools, max 40 turns).
- ultron: the real run.sh (fetch -> filter -> claude -p with Ultron -> applied.csv), approval mode with review.
- playwright: claude -p with Playwright MCP and the benchmark's prompt (bench.PLAYWRIGHT_PROMPT, facts in the prompt),
  changed only to stop before sending, as approval mode does.
When the agent is done, this script presses the form's Submit button itself, as you would in approval mode. The
replay captures the request the page sends, which is scored against the page's gold answers (bench/score.py).

Screenshots of the page are saved every 0.5 s; compose_demo.py turns them into the video.
Usage: python record_demo.py ARM [PAGE]   ARM: ultron | playwright; PAGE defaults to greenhouse_figma.
Uses your Claude Code login and plan: one agent run per call.
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = HERE.parent.parent  # autoapply
sys.path[:0] = [str(HERE), str(CODE / "bench")]
import bench  # noqa: E402
import drive  # noqa: E402
import realbench  # noqa: E402
import score  # noqa: E402
from replay import Replay  # noqa: E402

OUT = CODE.parent / "tmp" / "demo"
PORT = 9333
DISALLOWED = "Bash,Edit,Write,MultiEdit,NotebookEdit,WebFetch,WebSearch,Task"
BASELINE_PROMPT = bench.PLAYWRIGHT_PROMPT.replace(
    "4. Check the form, fix any problem, then submit it.",
    "4. Check the form and fix any problem, but don't submit it: I check it and press Submit myself.").replace(
    "Finish with one line: submitted, or not submitted and why.",
    "Finish with one line: ready for me to submit, or not ready and why.")
assert BASELINE_PROMPT.count("don't submit it") == 1 and "ready for me" in BASELINE_PROMPT


async def screenshots(replay: Replay, folder: Path, start: float, stop: asyncio.Event) -> None:
    """The page the agent works on (the newest tab that isn't blank), every 0.5 s."""
    folder.mkdir(parents=True)
    n = 0
    while not stop.is_set():
        pages = [p for p in replay.context.pages if p.url not in ("about:blank", "")]
        if pages:
            try:
                (folder / f"{n:05d}_{time.monotonic() - start:08.2f}.jpg").write_bytes(
                    await pages[-1].screenshot(type="jpeg", quality=80, timeout=2000))
                n += 1
            except Exception:
                pass
        await asyncio.sleep(0.5)


async def press_submit(replay: Replay) -> str:
    """What you do in approval mode: press the form's own Submit button (offline: the replay captures the request)."""
    pages = [p for p in replay.context.pages if p.url not in ("about:blank", "")]
    for page in reversed(pages):
        for frame in page.frames:
            button = frame.get_by_role("button", name=re.compile(r"submit", re.I))
            if await button.count():
                await button.first.click(timeout=5000)
                await page.wait_for_timeout(4000)
                return frame.url
    return ""


async def main(arm: str, name: str) -> None:
    out = OUT / arm
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    folder = CODE / "bench" / "pages" / name
    meta = json.loads((folder / "meta.json").read_text())
    env = {**os.environ, "ULTRON_PYTHON": drive.PY, "ULTRON_PORT": str(PORT), "ULTRON_CDP": f"http://127.0.0.1:{PORT}",
           "LANG": "C.UTF-8"}
    async with Replay(folder, PORT, out / "profile") as replay:
        if arm == "ultron":
            app = drive.make_app(out / "lane", "approval")
            config = (app / "config.toml").read_text()
            (app / "config.toml").write_text(config.replace("review = false", "review = true"))
            posting = {"id": name, "title": meta["title"], "location": meta["location"], "url": replay.url, "board": replay.url,
                       "posted": meta.get("posted") or "", "key": f"demo:{name}", "platform": meta["platform"],
                       "company": meta["company"], "fetched": datetime.now(timezone.utc).isoformat()}
            (app / "postings.jsonl").write_text(json.dumps(posting) + "\n")
            command, cwd = ["bash", str(app / "run.sh")], app
        else:
            work = out / "lane"
            work.mkdir(parents=True)
            shutil.copy(realbench.PERSONA / "resume.pdf", work / "resume.pdf")
            (work / "mcp.json").write_text(json.dumps({"mcpServers": {"playwright": {
                "command": str(bench.NODE), "args": [str(bench.PW_MCP), "--cdp-endpoint", f"http://127.0.0.1:{PORT}",
                                                     "--output-dir", str(work / "out")]}}}))
            prompt = BASELINE_PROMPT.format(document=realbench.document().format(resume=work / "resume.pdf"), url=replay.url)
            command = ["claude", "-p", prompt, "--mcp-config", str(work / "mcp.json"), "--strict-mcp-config",
                       "--allowedTools", "mcp__playwright", "--disallowedTools", DISALLOWED,
                       "--max-turns", "40", "--output-format", "json"]
            cwd = work
        stop = asyncio.Event()
        start, start_wall = time.monotonic(), time.time()
        shooter = asyncio.create_task(screenshots(replay, out / "frames", start, stop))
        process = await asyncio.create_subprocess_exec(*command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                                       stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        output, _ = await asyncio.wait_for(process.communicate(), 1800)
        agent_seconds = time.monotonic() - start
        await asyncio.sleep(1.5)
        sent_by_agent = score.score(name, list(replay.sent))["applications"]  # other requests (a resume parse) don't count
        pressed = await press_submit(replay) if not sent_by_agent else ""
        await asyncio.sleep(2)
        stop.set()
        await shooter
        sent = list(replay.sent)
    if arm == "ultron":
        logs = sorted((app / "logs").glob("*-1-*.log"))
        result = json.loads(logs[-1].read_text()) if logs else {}
        row = (app / "applied.csv").read_text() if (app / "applied.csv").exists() else ""
    else:
        result = json.loads(output.decode() or "{}")
        row = ""
    record = {"arm": arm, "page": name, "url": replay.url, "agent_seconds": round(agent_seconds, 1), "start_wall": start_wall, "claude": result,
              "applied_csv": row, "sent_by_agent": sent_by_agent, "pressed_submit_in": pressed,
              "score": score.score(name, sent), "run_output": output.decode()[-3000:]}
    (out / "result.json").write_text(json.dumps(record, indent=1))
    print(json.dumps({k: record[k] for k in ("arm", "agent_seconds", "sent_by_agent", "pressed_submit_in")}),
          {k: result.get(k) for k in ("num_turns", "total_cost_usd", "duration_ms", "is_error", "session_id")},
          {k: record["score"].get(k) for k in ("submitted", "wrong", "missing", "extra")}, flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "greenhouse_figma"))
