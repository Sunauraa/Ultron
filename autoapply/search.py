"""Step 0: find companies hiring for your roles, so you don't have to list them.

Claude Code web-searches each role in config.toml's [search] on the job boards Ultron reads (one search per role and
board site), with no other tool. Every company board named in the search results is checked by reading its job list
(the same public list fetch.py reads); boards that answer are added to found_boards.txt, which fetch.py reads next to
companies.txt. Only addresses from the search results themselves count, never ones the model writes, and a board that
doesn't answer is never added. Boards in [search] skip (sites that repost other companies' jobs) are never added.

Search finds companies, not fresh jobs: results are ranked by relevance, so a job published today rarely shows up.
The fresh jobs come from reading the found boards every run (fetch.py, no LLM).

The search runs at most once every 20 hours (the time is kept in searched.json), so running run.sh again the same
morning costs no new search.

Usage: python search.py [DIR]   (DIR holds config.toml, companies.txt, found_boards.txt; default: this folder)
Needs Claude Code (`claude`); with AGENT=codex the search is skipped.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import fetch

FOUND = "found_boards.txt"
LAST = "searched.json"
EVERY = timedelta(hours=20)
# The board sites searched, one search each per role. The smaller boards share one search.
SITES = [["job-boards.greenhouse.io", "boards.greenhouse.io"], ["jobs.lever.co"], ["jobs.ashbyhq.com"], ["apply.workable.com"],
         ["recruitee.com", "teamtailor.com", "jobs.personio.de", "bamboohr.com", "jobs.gem.com"]]


def known_boards(folder: Path) -> set[tuple[str, str]]:
    """Boards already read: companies.txt (board lines; careers pages through boards.json) and found_boards.txt."""
    known = set()
    for name in ("companies.txt", FOUND):
        path = folder / name
        for line in path.read_text().splitlines() if path.exists() else []:
            try:
                company = fetch.parse_company(line)
            except ValueError:
                continue
            if company and company[0] != "site":
                known.add(company)
    pages = folder / "boards.json"
    known |= {tuple(b) for b in json.loads(pages.read_text()).values()} if pages.exists() else set()
    return known


def prompt(roles: list[str]) -> str:
    searches = [f'- query "{role}", allowed_domains {json.dumps(sites)}' for role in roles for sites in SITES]
    return ("Run each of these web searches with the WebSearch tool, exactly as given, one search per line:\n"
            + "\n".join(searches)
            + "\n\nDon't open any page and don't do anything else. When all searches are done, reply with just: done")


def search(roles: list[str]) -> tuple[str, dict]:
    """Every search result, as Claude Code's own record of the tool results, and its final summary line."""
    command = ["claude", "-p", prompt(roles), "--allowedTools", "WebSearch",
               "--disallowedTools", "Bash,Edit,Write,MultiEdit,NotebookEdit,WebFetch,Task,Read,Glob,Grep",
               "--strict-mcp-config", "--max-turns", str(len(roles) * len(SITES) + 5),
               "--output-format", "stream-json", "--verbose"]
    done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1200)
    results, summary = [], {}
    for line in done.stdout.splitlines():
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if message.get("type") == "result":
            summary = message
        if message.get("type") != "user":  # tool results come back in user turns; the model's own text is not used
            continue
        for block in message.get("message", {}).get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                results.append(json.dumps(block.get("content")))
    if not summary:
        raise RuntimeError(f"claude gave no result (exit {done.returncode}): {(done.stderr or done.stdout)[-300:]}")
    return "\n".join(results), summary


def main(folder: Path) -> None:
    config = tomllib.loads((folder / "config.toml").read_text()).get("search", {})
    roles = [r for r in config.get("roles", []) if r.strip()]
    if not roles:
        print("search: no roles in config.toml [search], so no search (companies.txt only)")
        return
    if os.environ.get("AGENT", "claude") != "claude":
        print("search: needs Claude Code, skipped (companies.txt and boards found earlier are still read)")
        return
    last = folder / LAST
    if last.exists():
        when = datetime.fromisoformat(json.loads(last.read_text())["last"])
        if datetime.now(timezone.utc) - when < EVERY:
            print(f"search: already searched at {when:%Y-%m-%d %H:%M} UTC, next one from {when + EVERY:%Y-%m-%d %H:%M} UTC")
            return
    skip = {fetch.parse_company(line) for line in config.get("skip", [])}
    results, summary = search(roles)
    last.write_text(json.dumps({"last": datetime.now(timezone.utc).isoformat(timespec="seconds")}) + "\n")
    known = known_boards(folder)
    candidates = [b for b in fetch.boards_in(results) if b[0] != "workday" and b not in known and b not in skip]
    def answers(board: tuple[str, str]) -> bool:
        try:
            return bool(fetch.postings(*board))
        except Exception:  # an address that isn't a live board is never added
            return False
    live = fetch.per_platform(candidates, answers)
    added = [board for board in candidates if live[board]]
    if added:
        with (folder / FOUND).open("a") as out:
            out.writelines(f"{platform} {name}   # found {date.today().isoformat()}\n" for platform, name in added)
    cost = summary.get("total_cost_usd")
    print(f"search: {len(roles) * len(SITES)} searches; {len(added)} new company board(s) added to {FOUND}"
          + (f", {len(candidates) - len(added)} found but not answering" if len(candidates) > len(added) else "")
          + (f" (${cost:.2f})" if isinstance(cost, (int, float)) else ""))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent)
