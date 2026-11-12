"""Step 2: pick the postings worth applying to and write the queue, jobs.txt.

A posting is queued when its title matches an `include` keyword and no `exclude` keyword, its location
matches one of `locations` (or the list is empty), it is at most `max_age_days` old, and its URL is not
already in applied.csv. jobs.txt (url, company, title, platform, location, and the job's form on its board) is rebuilt every run, so a job leaves the queue once it is logged. A job logged
as needs_info comes back once answers.md has changed since.

Usage: python filter.py [DIR]   (DIR holds config.toml, postings.jsonl, applied.csv; default: this folder)
"""

from __future__ import annotations

import csv
import json
import re
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path


def words(keywords: list[str]) -> re.Pattern | None:
    """Whole-word, case-insensitive match, so "ML" doesn't match "HTML"."""
    if not keywords:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(k) for k in keywords) + r")(?!\w)", re.I)


def posted_at(value: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def logged_urls(applied: Path, answers: Path) -> set[str]:
    """URLs not to queue again: every logged job, except one logged needs_info before answers.md last changed
    (you added the missing answer, so it gets another try)."""
    if not applied.exists():
        return set()
    with applied.open(newline="") as f:
        last = {row["url"]: row for row in csv.DictReader(f)}
    edited = datetime.fromtimestamp(answers.stat().st_mtime, timezone.utc) if answers.exists() else None
    return {url for url, row in last.items()
            if not (row["status"] == "needs_info" and edited and (posted_at(row["time"]) or edited) < edited)}


def main(folder: Path) -> None:
    rules = tomllib.loads((folder / "config.toml").read_text())["filter"]
    include, exclude = words(rules.get("include", [])), words(rules.get("exclude", []))
    places = [p.casefold() for p in rules.get("locations", [])]
    oldest = datetime.now(timezone.utc) - timedelta(days=rules.get("max_age_days", 30))
    answers = folder / tomllib.loads((folder / "config.toml").read_text())["apply"].get("answers", "answers.md")
    done = logged_urls(folder / "applied.csv", answers)

    queue, seen = [], set()
    store = folder / "postings.jsonl"
    for line in store.open() if store.exists() else []:
        job = json.loads(line)
        title = job["title"]
        if job["url"] in done or job["url"] in seen:
            continue
        if include and not include.search(title):
            continue
        if exclude and exclude.search(title):
            continue
        if places and not any(p in job["location"].casefold() for p in places):
            continue
        posted = posted_at(job.get("posted", ""))
        if posted and posted < oldest:
            continue
        seen.add(job["url"])
        queue.append(job)

    queue.sort(key=lambda j: j.get("posted", ""), reverse=True)  # newest first
    with (folder / "jobs.txt").open("w") as out:
        for job in queue:
            out.write("\t".join([job["url"], job["company"], job["title"], job["platform"], job["location"], job.get("board", "")]) + "\n")
    print(f"{len(queue)} job(s) queued in jobs.txt")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent)
