"""What a run did: every job logged in applied.csv since the run started, with its status and notes.

applied.csv is only ever appended to, so a run's jobs are the rows after the ones there when it started.
Usage: python report.py --count      how many rows applied.csv has now (run.sh, at its start)
       python report.py ROWS         the report: every row after the first ROWS
"""

import csv
import sys
from collections import Counter
from pathlib import Path

APPLIED = Path(__file__).parent / "applied.csv"

WHAT_NEXT = {
    "ready": "filled and waiting in its Chrome tab: check it, press Submit, then python mark.py URL submitted",
    "submitted": "sent; the page confirmed it",
    "needs_info": "a required question isn't in answers.md: answer it (python ask.py) and it is retried next run",
    "needs_human": "apply yourself at the link (captcha, sign-in, Workday or an error; see notes)",
    "skipped": "closed, or no form",
}


def logged() -> list[dict]:
    return list(csv.DictReader(APPLIED.open(newline=""))) if APPLIED.exists() else []


def main(before: int) -> None:
    rows = logged()[before:]
    if not rows:
        print("This run logged no job.")
        return
    counts = Counter(r["status"] for r in rows)
    print(f"This run: {len(rows)} job(s): " + ", ".join(f"{n} {status}" for status, n in counts.most_common()))
    for status in WHAT_NEXT:
        jobs = [r for r in rows if r["status"] == status]
        if jobs:
            print(f"\n{status} ({len(jobs)}): {WHAT_NEXT[status]}")
            for r in jobs:
                print(f"  - {r['company']} | {r['title'].strip()} | {r['url']}" + (f"\n    {r['notes'][:300]}" if r["notes"] else ""))


if __name__ == "__main__":
    if sys.argv[1:] == ["--count"]:
        print(len(logged()))
    else:
        main(int(sys.argv[1]))
