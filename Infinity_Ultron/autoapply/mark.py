"""Log a job's status by hand, e.g. after you submit a "ready" form yourself.

Usage: python mark.py URL STATUS [NOTES]   (STATUS: submitted, skipped, needs_info, needs_human, ready)
       python mark.py --if-missing URL STATUS NOTES   (only if the URL isn't logged yet; used by run.sh)
"""

import csv
import fcntl
import sys
from datetime import datetime, timezone
from pathlib import Path

FOLDER = Path(__file__).parent
COLUMNS = ["time", "url", "company", "title", "platform", "status", "notes"]
STATUSES = {"submitted", "skipped", "needs_info", "needs_human", "ready"}


def main(args: list[str]) -> None:
    only_if_missing = args[:1] == ["--if-missing"]
    url, status, notes = (args[1:] if only_if_missing else args) + [""] * (3 - len(args[1:] if only_if_missing else args))
    if status not in STATUSES:
        sys.exit(f"STATUS must be one of {sorted(STATUSES)}")
    path = FOLDER / "applied.csv"
    if only_if_missing and path.exists() and any(row["url"] == url for row in csv.DictReader(path.open())):
        return
    job = next((line.split("\t") for line in (FOLDER / "jobs.txt").read_text().splitlines() if line.startswith(url + "\t")), None) \
        if (FOLDER / "jobs.txt").exists() else None
    company, title, platform = (job[1], job[2], job[3]) if job else ("", "", "")
    with path.open("a", newline="") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        writer = csv.DictWriter(f, COLUMNS)
        if f.tell() == 0:
            writer.writeheader()
        writer.writerow(dict(time=datetime.now(timezone.utc).isoformat(timespec="seconds"), url=url, company=company,
                             title=title, platform=platform, status=status, notes=notes))
    print(f"Logged {url} as {status}.")


if __name__ == "__main__":
    main(sys.argv[1:])
