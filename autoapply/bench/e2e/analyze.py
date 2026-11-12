"""Summarise the end-to-end lanes: per page and mode, the status logged, whether an application was sent, its score,
and the agent run (turns, how it ended). Usage: python analyze.py"""

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent.parent / "tmp" / "e2e"  # where drive.py writes lanes and results
rows = []
for path in sorted((HERE / "results").glob("*.jsonl")):
    mode = path.stem.rsplit("_", 1)[0]
    for line in path.read_text().splitlines():
        r = json.loads(line)
        log = {}
        notes = ((r.get("row") or {}).get("notes") or "")
        lane = HERE / "lanes" / path.stem
        if "see logs/" in notes:
            log = json.loads((lane / "app" / notes.split("see ", 1)[1]).read_text() or "{}")
        else:
            logs = sorted((lane / "app" / "logs").glob("*.log"))
            match = [p for p in logs if r["page"] and r.get("url") and r["url"][:60] in p.read_text()[:20000]]
            if match:
                try:
                    log = json.loads(match[-1].read_text())
                except ValueError:
                    log = {"subtype": "unreadable log"}
        score = r.get("score") or {}
        rows.append(dict(mode=mode, page=r["page"], status=(r.get("row") or {}).get("status", r.get("error", "NO ROW")),
                         notes=notes[:160], sent=r.get("sent_count"), submitted=score.get("submitted"), correct=score.get("correct"),
                         turns=log.get("num_turns"), end=log.get("subtype"), tools=[a["tool"] for a in log.get("actions", [])]))
for r in sorted(rows, key=lambda r: (r["page"], r["mode"])):
    print(f"{r['page']:24} {r['mode']:11} {r['status']:12} sent={r['sent']!s:3} sub={r['submitted']!s:5} ok={r['correct']!s:5} "
          f"turns={r['turns']!s:3} end={r['end']}  | {r['notes']}")
for mode in ("approval", "auto_review"):
    print(mode, Counter(r["status"] for r in rows if r["mode"] == mode))
if "-v" in sys.argv:
    for r in rows:
        print(r["page"], r["mode"], " ".join(r["tools"]))
