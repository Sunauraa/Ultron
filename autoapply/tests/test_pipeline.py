"""Tests of the pipeline around Ultron, offline: fetch.py reading every board's job list (real feeds saved in
fixtures/feeds) and every form of companies.txt line, including a company's own careers page; filter.py's queue;
the job's page on the company's own site (Greenhouse) with the board's form as fallback;
jobinfo.py reading a posting on the newer boards (for research_company);
run.sh end to end with a stand-in `claude` (Workday jobs are logged needs_human without an agent run, a job the
agent didn't log is logged needs_human, the per-run cap counts only agent runs).
Usage: python tests/test_pipeline.py   (exit code 0 when every check passes)
"""

from __future__ import annotations

import csv
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
FEEDS = HERE / "fixtures" / "feeds"
WORK = ROOT.parent / "tmp" / "pipeline_test"
sys.path.insert(0, str(ROOT))
import fetch  # noqa: E402
import jobinfo  # noqa: E402

failures: list[str] = []


def check(condition: bool, what: str) -> None:
    print(("PASS " if condition else "FAIL ") + what)
    if not condition:
        failures.append(what)


# What each board's list address answers, from the saved real feeds (fetched 2026-11-11).
ANSWERS = {
    "https://career.teamtailor.com/jobs.rss": FEEDS / "teamtailor.rss",
    "https://f24.jobs.personio.de/xml": FEEDS / "personio.xml",
    "https://onezero.bamboohr.com/careers/list": FEEDS / "bamboohr.json",
    "https://api.gem.com/job_board/v0/gem/job_posts/": FEEDS / "gem.json",
    "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/siteMap.xml": FEEDS / "workday.xml",
    "https://boards-api.greenhouse.io/v1/boards/airbnb/jobs": FEEDS / "greenhouse_airbnb.json",  # first jobs only
    "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs": FEEDS / "greenhouse_anthropic.json",
}
PAGES = {  # careers pages, as their HTML names (or doesn't name) a board
    "https://kappa.example/careers": b'<a href="https://jobs.ashbyhq.com/kappa">Open roles</a>',
    "https://lambda.example/jobs": b'<script>var u = "https:\\/\\/boards.greenhouse.io\\/embed\\/job_board\\/js?for=lambda";</script>',
    "https://vc.example/portfolio-jobs": b'<a href="https://jobs.lever.co/one">1</a><a href="https://jobs.lever.co/two">2</a>',
    "https://script.example/careers": b"<div id=app></div>",
}


def fake_get(url: str, agent: str = "") -> bytes:
    if url in ANSWERS:
        return ANSWERS[url].read_bytes()
    if url in PAGES:
        return PAGES[url]
    raise OSError(f"no network in tests: {url}")


def test_lines() -> None:
    cases = {
        "greenhouse anthropic": ("greenhouse", "anthropic"),
        "https://job-boards.greenhouse.io/anthropic": ("greenhouse", "anthropic"),
        "https://job-boards.greenhouse.io/embed/job_app?for=stripe&token=8172487": ("greenhouse", "stripe"),
        "https://jobs.lever.co/palantir/abc": ("lever", "palantir"),
        "https://career.teamtailor.com/jobs": ("teamtailor", "career.teamtailor.com"),
        "https://f24.jobs.personio.de/": ("personio", "f24"),
        "https://onezero.bamboohr.com/careers": ("bamboohr", "onezero"),
        "https://jobs.gem.com/gem": ("gem", "gem"),
        "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite": ("workday", "nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"),
        "https://stripe.com/jobs  # their own site": ("site", "https://stripe.com/jobs"),
        "# a comment": None,
    }
    for line, want in cases.items():
        got = fetch.parse_company(line)
        check(got == want, f"[lines] {line!r} -> {want}")
    try:
        fetch.parse_company("stripe")
        check(False, "[lines] a bare word is refused")
    except ValueError:
        check(True, "[lines] a bare word is refused")


def test_boards() -> None:
    fetch.get = fake_get
    expect = {
        ("teamtailor", "career.teamtailor.com"): ("Enterprise Account Executive - Chicago", "Chicago, United States (hybrid)",
                                                 "https://career.teamtailor.com/jobs/8706432-enterprise-account-executive-chicago/applications/new", "Teamtailor"),
        ("personio", "f24"): ("Initiativbewerbung (all genders)", "Munich / DEU", "https://f24.jobs.personio.de/job/122150/apply?display=en", "f24"),
        ("bamboohr", "onezero"): ("Technical Project Manager", "Somerville, Massachusetts", "https://onezero.bamboohr.com/careers/279", "onezero"),
        ("gem", "gem"): ("Engineering Manager (AI Products)", "San Francisco, United States (hybrid)",
                         "https://jobs.gem.com/gem/am9icG9zdDoxt66pB6mvVDH0kCIS4bLF", "gem"),
        ("workday", "nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"): (
            "Senior Board Design Engineer", "Israel Yokneam",
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/Israel-Yokneam/Senior-Board-Design-Engineer_JR2029481", "nvidia"),
    }
    for board, (title, location, url, company) in expect.items():
        rows = fetch.postings(*board)
        first = rows[0]
        check(len(rows) == 2 if board[0] != "gem" else len(rows) == 1, f"[boards] {board[0]}: every job read")
        check((first["title"], first["location"], first["url"], first["company"]) == (title, location, url, company),
              f"[boards] {board[0]}: title, place, form address and company name")
        check(first["key"].startswith(f"{board[0]}:{board[1]}:") and len({r["key"] for r in rows}) == len(rows), f"[boards] {board[0]}: unique keys")
    for row in [r for board in expect for r in fetch.postings(*board)]:
        check(row["board"] == row["url"], f"[boards] {row['platform']}: no company page named, so the board's form is both url and board")
    airbnb = fetch.postings("greenhouse", "airbnb")[0]
    check(airbnb["url"] == "https://careers.airbnb.com/positions/8365363?gh_jid=8365363"
          and airbnb["board"] == "https://job-boards.greenhouse.io/embed/job_app?for=airbnb&token=8365363",
          "[boards] greenhouse: a job listed on the company's own site is applied there, with the board's form as fallback")
    anthropic = fetch.postings("greenhouse", "anthropic")[0]
    check(anthropic["url"] == anthropic["board"] == "https://job-boards.greenhouse.io/embed/job_app?for=anthropic&token=5456619008",
          "[boards] greenhouse: a job listed only on greenhouse.io is applied on the board's form")
    tt = fetch.postings("teamtailor", "career.teamtailor.com")[0]
    check(tt["posted"] == "2026-11-11T17:34:36+01:00", "[boards] teamtailor: RSS date read")


def test_sites() -> None:
    fetch.get = fake_get
    fetch.rendered = lambda url: (_ for _ in ()).throw(ImportError())  # no browser in this test
    check(fetch.board_of_site("https://kappa.example/careers") == ("ashby", "kappa"), "[sites] a careers page linking its board")
    check(fetch.board_of_site("https://lambda.example/jobs") == ("greenhouse", "lambda"), "[sites] a board named inside an escaped script")
    for url, why in [("https://vc.example/portfolio-jobs", "several job boards"), ("https://script.example/careers", "names no job board")]:
        try:
            fetch.board_of_site(url)
            check(False, f"[sites] {url} refused")
        except ValueError as error:
            check(why in str(error), f"[sites] {url}: refused ({why})")
    fetch.rendered = lambda url: 'request https://api.ashbyhq.com/posting-api/job-board/scripted'
    check(fetch.board_of_site("https://script.example/careers") == ("ashby", "scripted"), "[sites] a page that loads its board by script, read rendered")


def test_fetch_and_filter() -> None:
    fetch.get = fake_get
    fetch.rendered = lambda url: (_ for _ in ()).throw(ImportError())
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    (WORK / "companies.txt").write_text("teamtailor career.teamtailor.com\nhttps://onezero.bamboohr.com/careers\n"
                                        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite\nhttps://script.example/careers\n"
                                        "https://kappa.example/careers\n")
    fetch.time.sleep = lambda s: None
    fetch.main(WORK)
    rows = [json.loads(line) for line in (WORK / "postings.jsonl").read_text().splitlines()]
    check(len(rows) == 6 and {r["platform"] for r in rows} == {"teamtailor", "bamboohr", "workday"},
          "[fetch] every listed board read; a careers page naming no board and an unreachable board are skipped, not fatal")
    known = json.loads((WORK / "boards.json").read_text())
    check(known == {"https://kappa.example/careers": ["ashby", "kappa"]}, "[fetch] only careers pages that named a board are remembered")
    fetch.main(WORK)
    check(len((WORK / "postings.jsonl").read_text().splitlines()) == 6, "[fetch] a second run adds nothing already seen")
    config = (ROOT / "config.example.toml").read_text()
    config = config.replace('include = ["machine learning", "ML", "AI", "research engineer", "software engineer", "intern", "new grad"]',
                            'include = ["engineer", "manager", "executive"]').replace('exclude = ["senior", "staff", "principal", "lead", "manager", "director", "head of"]',
                                                                                    'exclude = ["director"]')
    config = config.replace('locations = ["remote", "san francisco", "new york"]', "locations = []").replace("max_age_days = 30", "max_age_days = 100000")
    (WORK / "config.toml").write_text(config)
    (WORK / "answers.md").write_text("Email: a@b.c\n")
    subprocess.run([sys.executable, str(ROOT / "filter.py"), str(WORK)], check=True)
    queue = [line.split("\t") for line in (WORK / "jobs.txt").read_text().splitlines()]
    check(len(queue) == 6 and all(len(q) == 6 and q[5] == q[0] for q in queue), "[filter] the new boards' jobs are queued with their platform and board form")


class Version(http.server.BaseHTTPRequestHandler):
    """Answers /json/version, so browser.sh sees a browser already up (no browser in this test)."""
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


def test_jobinfo() -> None:
    """research_company's reading of a posting on the boards added for the wide set (real answers saved 2026-11-11)."""
    detail = FEEDS / "detail"
    answers = {"https://career.teamtailor.com/jobs.rss": detail / "teamtailor.rss",
               "https://f24.jobs.personio.de/xml?language=en": detail / "personio_en.xml",
               "https://f24.jobs.personio.de/xml": detail / "personio_default.xml",
               "https://onezero.bamboohr.com/careers/316/detail": detail / "bamboohr_316.json",
               "https://api.gem.com/job_board/v0/gem/job_posts/": detail / "gem.json"}
    asked = []

    def urlopen(request, timeout=None):
        asked.append(request.full_url)
        return io.BytesIO(answers[request.full_url].read_bytes())

    real, jobinfo.urllib.request.urlopen = jobinfo.urllib.request.urlopen, urlopen
    try:
        cases = [
            ("https://career.teamtailor.com/jobs/8706432-enterprise-account-executive-chicago/applications/new", "",
             ("Teamtailor", "Enterprise Account Executive - Chicago", "Chicago", "Teamtailor is a global")),
            ("https://jobs.example.com/jobs/8706432-enterprise-account-executive-chicago/applications/new", "teamtailor", None),
            ("https://f24.jobs.personio.de/job/2676311/apply?display=en", "",
             ("F24 AG", "Junior Full Stack Engineer - Suite", "Zagreb / HR", "Junior Software Engineer")),
            ("https://f24.jobs.personio.de/job/1316737/apply?display=en", "",
             ("F24 Schweiz AG", "Initiativbewerbung (all genders)", "Wollerau / CH", "Initiativbewerbung")),
            ("https://onezero.bamboohr.com/careers/316", "", ("", "Desktop Support Engineer", "Somerville, Massachusetts", "oneZero")),
            ("https://jobs.gem.com/gem/am9icG9zdDoxt66pB6mvVDH0kCIS4bLF", "",
             ("", "Engineering Manager (AI Products)", "San Francisco, United States", "$242,000")),
            ("https://jobs.gem.com/gem/no-such-job", "", None),
        ]
        for url, platform, want in cases:
            try:
                found = jobinfo.about_job(url, platform)
            except KeyError:  # a custom domain: its feed isn't in the saved answers, so it was asked for
                found = "asked " + asked[-1]
            if want is None and platform:
                check(found == "asked https://jobs.example.com/jobs.rss", f"[jobinfo] a {platform} board on its own domain is read from that domain")
                continue
            ok = found == want if want is None else (found and (found["company"], found["title"], found["location"]) == want[:3]
                                                     and want[3] in found["description"])
            check(bool(ok), f"[jobinfo] {url}: " + ("not listed, so None" if want is None else "company, role, place and description"))
        check("https://f24.jobs.personio.de/xml?language=en" in asked and asked.count("https://f24.jobs.personio.de/xml") == 1,
              "[jobinfo] Personio: asked in the form's language; the default language only when that has no description")
    finally:
        jobinfo.urllib.request.urlopen = real


def test_run_sh() -> None:
    folder = WORK / "app"
    folder.mkdir()
    for name in ("run.sh", "browser.sh", "fetch.py", "filter.py", "mark.py", "questions.py", "prompt.md"):
        shutil.copy(ROOT / name, folder / name)
    shutil.copytree(ROOT / "playbooks", folder / "playbooks")
    for name in ("companies.txt", "config.toml", "answers.md"):
        shutil.copy(WORK / name, folder / name)
    (folder / "config.toml").write_text((folder / "config.toml").read_text().replace("max_jobs_per_run = 5", "max_jobs_per_run = 2"))
    # Offline: Python started by run.sh answers the boards' addresses from the saved feeds (sitecustomize).
    hooks = WORK / "hooks"
    hooks.mkdir()
    (hooks / "sitecustomize.py").write_text(f"""
import io, urllib.request
FEEDS = {json.dumps({k: str(v) for k, v in ANSWERS.items()})}
PAGES = {json.dumps({k: v.decode() for k, v in PAGES.items()})}
def urlopen(request, timeout=None):
    url = request.full_url if hasattr(request, "full_url") else request
    if url in FEEDS:
        return io.BytesIO(open(FEEDS[url], "rb").read())
    if url in PAGES:
        return io.BytesIO(PAGES[url].encode())
    raise OSError("no network in tests: " + url)
urllib.request.urlopen = urlopen
""")
    bin_dir = WORK / "bin"
    bin_dir.mkdir()
    calls = WORK / "claude_calls.txt"
    (bin_dir / "claude").write_text(f"#!/bin/bash\necho \"$2\" | tail -n 1 >> '{calls}'\necho '{{\"result\": \"stand-in\"}}'\n")
    (bin_dir / "claude").chmod(0o755)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Version)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "PYTHONPATH": str(hooks), "ULTRON_PYTHON": sys.executable,
           "ULTRON_PORT": str(server.server_address[1])}
    done = subprocess.run(["bash", str(folder / "run.sh")], env=env, capture_output=True, text=True, timeout=300)
    print(done.stdout[-1500:], done.stderr[-1500:])
    rows = list(csv.DictReader((folder / "applied.csv").open()))
    agent_runs = calls.read_text().splitlines() if calls.exists() else []
    workday = [r for r in rows if r["platform"] == "workday"]
    others = [r for r in rows if r["platform"] != "workday"]
    check(done.returncode == 0, "[run.sh] the run ends cleanly")
    check(len(workday) == 2 and all(r["status"] == "needs_human" and "account" in r["notes"] for r in workday),
          "[run.sh] Workday jobs are logged needs_human, with the reason, without an agent run")
    check(len(agent_runs) == 2 and all(a.startswith("URL: https://") and "myworkdayjobs" not in a for a in agent_runs),
          "[run.sh] the agent runs only max_jobs_per_run jobs, none of them Workday")
    check(len(others) == 2 and all(r["status"] == "needs_human" and "Agent ended without logging" in r["notes"] for r in others),
          "[run.sh] a job the agent didn't log is logged needs_human, not retried blindly")
    check(len(list((folder / "logs").glob("*.log"))) == len(agent_runs), "[run.sh] each agent run keeps its own log")
    done = subprocess.run(["bash", str(folder / "run.sh")], env=env, capture_output=True, text=True, timeout=300)
    server.shutdown()
    rows = list(csv.DictReader((folder / "applied.csv").open()))
    check(len(rows) == 6 and len(calls.read_text().splitlines()) == 4, "[run.sh] the next run takes the rest of the queue, nothing twice")


test_lines()
test_boards()
test_sites()
test_fetch_and_filter()
test_jobinfo()
test_run_sh()
print(f"\n{len(failures)} failure(s)" + (": " + "; ".join(failures) if failures else ""))
sys.exit(1 if failures else 0)
