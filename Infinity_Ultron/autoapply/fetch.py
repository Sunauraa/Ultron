"""Step 1: fetch every posting from the companies in companies.txt through the public job lists of Greenhouse,
Lever, Ashby, Workable, Recruitee, Teamtailor, Personio, BambooHR, Gem and Workday (no keys, no login, no LLM).
New postings are appended to postings.jsonl. Each posting's url is where the agent applies: the job's page on the
company's own site when the board names one (Greenhouse's absolute_url off greenhouse.io), else the board's form;
board is the board's form, which Ultron falls back to when the company's page has no usable form.

companies.txt has one company per line, in any of three forms. `#` starts a comment.
- `PLATFORM NAME`: `greenhouse anthropic`, `lever palantir`, `ashby openai`, `workable huggingface`, `recruitee bunq`,
  `teamtailor career.teamtailor.com` (its careers site's address), `personio f24`, `bamboohr onezero`, `gem gem`.
- A job-board URL: job-boards.greenhouse.io/<name>, jobs.lever.co/<name>, jobs.ashbyhq.com/<name>,
  apply.workable.com/<name>, <name>.recruitee.com, <name>.teamtailor.com, <name>.jobs.personio.de,
  <name>.bamboohr.com, jobs.gem.com/<name>, <tenant>.wd<N>.myworkdayjobs.com/<site>.
- The company's own careers page (https://linear.app/careers): it is read once to find which of these job boards it
  shows (the application form, often in a frame on the company's page, is that board's form); the answer is kept in
  boards.json. Pages that load their jobs by script are opened in a headless browser. A page that names no board, or
  several, is reported: add the board's own address for it instead.
Workday jobs are listed but not applied to by the agent: Workday asks for an account first, so run.sh logs them
as needs_human with their link, for you to apply yourself. SmartRecruiters is left out: its application pages sit
behind DataDome bot protection, and iCIMS / Oracle need an account too.

Usage: python fetch.py [DIR]   (DIR holds companies.txt and postings.jsonl; default: this folder)
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

APIS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{}",
    "recruitee": "https://{}.recruitee.com/api/offers/",
    "teamtailor": "https://{}/jobs.rss",
    "personio": "https://{}.jobs.personio.de/xml",
    "bamboohr": "https://{}.bamboohr.com/careers/list",
    "gem": "https://api.gem.com/job_board/v0/{}/job_posts/",
    "workday": "https://{}/siteMap.xml",
}
# A board's address, wherever it appears: in companies.txt, or in a company's careers page (links, frames, scripts).
BOARD_URL = re.compile(r"(?:job-boards|boards)\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?(?!embed\b)([\w-]+)"
                       r"|boards-api\.greenhouse\.io/v1/boards/([\w-]+)|greenhouse\.io/embed/job_app\?(?:[\w=%.-]*&(?:amp;)?)*for=([\w-]+)"
                       r"|jobs\.lever\.co/([\w.-]+)|api\.lever\.co/v0/postings/([\w.-]+)"
                       r"|jobs\.ashbyhq\.com/([\w.%-]+)|api\.ashbyhq\.com/posting-api/job-board/([\w.%-]+)"
                       r"|apply\.workable\.com/(?!api\b)([\w-]+)"
                       r"|(?<![\w.-])([\w-]+)\.recruitee\.com"
                       r"|(?<![\w.-])([\w-]+\.teamtailor\.com)"
                       r"|(?<![\w.-])([\w-]+)\.jobs\.personio\.(?:de|com)"
                       r"|(?<![\w.-])([\w-]+)\.bamboohr\.com"
                       r"|jobs\.gem\.com/([\w-]+)"
                       r"|(?<![\w.-])([\w-]+\.wd\d+\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?[\w-]+)")
GROUPS = ("greenhouse", "greenhouse", "greenhouse", "lever", "lever", "ashby", "ashby", "workable", "recruitee", "teamtailor", "personio",
          "bamboohr", "gem", "workday")
PLATFORMS = tuple(APIS)
# Subdomains and paths that belong to the board itself, not to a company.
NOT_COMPANIES = {"www", "api", "app", "embed", "assets", "static", "cdn", "help", "support", "docs", "status", "blog", "jobs",
                 "careers", "boards", "js"}


def boards_in(text: str) -> list[tuple[str, str]]:
    """Every job board named in a text, in order, without repeats."""
    found = []
    for match in BOARD_URL.finditer(text):
        k = next(i for i, g in enumerate(match.groups()) if g)
        name = match.group(k + 1)
        if GROUPS[k] == "workday":  # tenant host + site, without the language part
            name = re.sub(r"/[a-z]{2}-[A-Z]{2}/", "/", name)
        if name.split(".")[0].lower() in NOT_COMPANIES and GROUPS[k] != "workday" or name.lower() in NOT_COMPANIES:
            continue
        if (GROUPS[k], name) not in found:
            found.append((GROUPS[k], name))
    return found


def parse_company(line: str) -> tuple[str, str] | None:
    """(platform, name) for a companies.txt line; ("site", URL) for a company's own careers page."""
    line = line.split("#", 1)[0].strip()
    if not line:
        return None
    platform, _, name = line.partition(" ")
    if platform.lower() in APIS and name.strip():
        return platform.lower(), name.strip()
    boards = boards_in(line)
    if boards:
        return boards[0]
    if re.match(r"https?://[\w.-]+\.\w+", line):
        return "site", line
    raise ValueError(f"can't read company line {line!r}: use 'PLATFORM NAME' ({', '.join(PLATFORMS)}), a job-board URL "
                     "or the company's careers page URL")


def rendered(url: str) -> str:
    """A careers page as a browser shows it: its HTML, links, frames and every address it requested."""
    import asyncio
    from playwright.async_api import async_playwright

    async def load() -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(locale="en-US")
            requested = []
            page.on("request", lambda r: requested.append(r.url))
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            seen = " ".join(requested + [await page.content()] + [f.url for f in page.frames])
            await browser.close()
            return seen
    return asyncio.run(load())


def board_of_site(url: str) -> tuple[str, str]:
    """The job board a company's careers page shows: from its HTML, else from the page as a browser renders it.
    Raises if the page names none, or more than one (a page listing several companies' jobs)."""
    html = get(url, "Mozilla/5.0 (compatible; ultron-autoapply/0.1)").decode("utf-8", "replace")  # some sites refuse non-browsers
    boards = boards_in(unquote(html.replace("\\/", "/")))  # addresses inside scripts are often escaped
    if not boards:
        try:
            boards = boards_in(unquote(rendered(url).replace("\\/", "/")))
        except ImportError:
            pass
    if not boards:
        raise ValueError("its careers page names no job board this tool reads (it may be another system, or sit "
                         "behind a bot check): add the board's own address instead")
    if len(boards) > 1:  # keep the ones whose job list answers (a vendor's own pages: "trust.teamtailor.com")
        def answers(board: tuple[str, str]) -> bool:
            try:
                postings(*board)
                return True
            except Exception:
                return False
        boards = [b for b in boards if answers(b)] or boards
    if len(boards) > 1:
        raise ValueError(f"its careers page names several job boards ({', '.join(f'{p} {n}' for p, n in boards[:4])}): "
                         "add the right one as a line of its own")
    return boards[0]


def resolve(folder: Path, url: str) -> tuple[str, str]:
    """board_of_site, remembered in boards.json so each careers page is read once."""
    path = folder / "boards.json"
    known = json.loads(path.read_text()) if path.exists() else {}
    if url not in known:
        known[url] = list(board_of_site(url))
        path.write_text(json.dumps(known, indent=1) + "\n")
        print(f"{url}: {known[url][0]} {known[url][1]}", file=sys.stderr)
    return tuple(known[url])


def get(url: str, agent: str = "ultron-autoapply/0.1") -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": agent})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(5_000_000)


def get_json(url: str):
    return json.loads(get(url))


def text(node, path: str, ns: dict | None = None) -> str:
    found = node.find(path, ns or {})
    return (found.text or "").strip() if found is not None else ""


def iso(value) -> str:
    """Posting time as an ISO string. Lever gives milliseconds since the epoch."""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()
    return value or ""


def postings(platform: str, company: str) -> list[dict]:
    if platform in ("teamtailor", "personio", "workday"):
        return feed_postings(platform, company)
    data = get_json(APIS[platform].format(company))
    rows = []
    if platform == "greenhouse":
        for job in data["jobs"]:
            # The form's own page on the board; when the company lists the job on its own site (absolute_url off
            # greenhouse.io), that page is where the application is made, with the board's form as the fallback.
            form = f"https://job-boards.greenhouse.io/embed/job_app?for={company}&token={job['id']}"
            own = job.get("absolute_url") or ""
            own = own if own.startswith("https://") and not re.search(r"(^|\.)greenhouse\.io$", urlparse(own).netloc) else ""
            rows.append(dict(id=job["id"], title=job["title"], location=(job.get("location") or {}).get("name", ""),
                             url=own or form, board=form, posted=job.get("first_published") or job.get("updated_at", "")))
    elif platform == "lever":
        for job in data:
            categories = job.get("categories") or {}
            location = "; ".join(categories.get("allLocations") or [categories.get("location", "")])
            rows.append(dict(id=job["id"], title=job["text"], location=f"{location} ({job.get('workplaceType', '')})".replace(" ()", ""),
                             url=job.get("applyUrl") or job["hostedUrl"], posted=iso(job.get("createdAt"))))
    elif platform == "workable":
        for job in data["jobs"]:
            places = [", ".join(x for x in (p.get("city"), p.get("country")) if x) for p in job.get("locations") or []]
            location = "; ".join(places) or ", ".join(x for x in (job.get("city"), job.get("country")) if x)
            rows.append(dict(id=job["shortcode"], title=job["title"], location=location + (" (remote)" if job.get("telecommuting") else ""),
                             url=job.get("application_url") or job["url"], posted=job.get("published_on") or job.get("created_at", "")))
    elif platform == "recruitee":
        for job in data["offers"]:
            if job.get("status", "published") != "published":
                continue
            location = job.get("location") or ", ".join(x for x in (job.get("city"), job.get("country")) if x)
            remote = " (remote)" if job.get("remote") and "remote" not in location.casefold() else ""
            rows.append(dict(id=job["id"], title=job["title"], location=location + remote,
                             url=job.get("careers_apply_url") or job["careers_url"], posted=(job.get("published_at") or "").replace(" UTC", "+00:00")))
    elif platform == "bamboohr":
        for job in data["result"]:
            place = job.get("location") or {}
            location = ", ".join(x for x in (place.get("city"), place.get("state")) if x)
            remote = " (remote)" if job.get("isRemote") or job.get("locationType") == "1" else ""
            # The job's page: its "Apply for This Job" button opens the form on the same page.
            rows.append(dict(id=job["id"], title=job["jobOpeningName"], location=location + remote,
                             url=f"https://{company}.bamboohr.com/careers/{job['id']}", posted=""))
    elif platform == "gem":
        for job in data:
            location = (job.get("location") or {}).get("name", "")
            kind = {"remote": " (remote)", "hybrid": " (hybrid)"}.get(job.get("location_type") or "", "")
            rows.append(dict(id=job["id"], title=job["title"], location=location + kind, url=job["absolute_url"],
                             posted=job.get("first_published_at") or job.get("created_at", "")))
    else:
        for job in data["jobs"]:
            if job.get("isListed") is False:
                continue
            location = job.get("location", "") + (" (remote)" if job.get("isRemote") else "")
            rows.append(dict(id=job["id"], title=job["title"], location=location,
                             url=job.get("applyUrl") or job["jobUrl"], posted=iso(job.get("publishedAt"))))
    for row in rows:
        # board: the job's form on its job board. The same as url when the board names no page on the company's own site.
        row.update(key=f"{platform}:{company}:{row['id']}", platform=platform, company=company, board=row.get("board") or row["url"])
    return rows


TT = {"tt": "https://teamtailor.com/locations"}


def feed_postings(platform: str, company: str) -> list[dict]:
    """The boards that publish their jobs as XML: Teamtailor (RSS), Personio (XML feed), Workday (sitemap)."""
    root = ET.fromstring(get(APIS[platform].format(company)))
    rows = []
    if platform == "teamtailor":
        for item in root.iterfind("channel/item"):
            places = [", ".join(x for x in (text(p, "tt:city", TT), text(p, "tt:country", TT)) if x) or text(p, "tt:name", TT)
                      for p in item.iterfind("tt:locations/tt:location", TT)]
            remote = text(item, "remoteStatus")
            link = text(item, "link")
            posted = text(item, "pubDate")
            # The job's page with /applications/new is its application form.
            rows.append(dict(id=link.rstrip("/").rsplit("/", 1)[-1].split("-", 1)[0], title=text(item, "title"),
                             location="; ".join(p for p in places if p) + (f" ({remote})" if remote and remote != "none" else ""),
                             url=link.rstrip("/") + "/applications/new",
                             posted=parsedate_to_datetime(posted).isoformat() if posted else ""))
    elif platform == "personio":
        for job in root.iterfind("position"):
            rows.append(dict(id=text(job, "id"), title=text(job, "name"), location=text(job, "office"),
                             url=f"https://{company}.jobs.personio.de/job/{text(job, 'id')}/apply?display=en", posted=text(job, "createdAt")))
    else:  # Workday's sitemap: each job's address carries its place and title ("/job/Israel-Yokneam/Senior-Engineer_JR123")
        for loc in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
            match = re.search(r"/job/([^/]+)/([^/]+)_([\w-]+)$", loc.text or "")
            if match:
                rows.append(dict(id=match.group(3), title=unquote(match.group(2)).replace("-", " "), location=unquote(match.group(1)).replace("-", " "),
                                 url=loc.text.strip(), posted=""))
    # The name shown for the company: Teamtailor's feed names it; a Workday site is named after its tenant.
    shown = {"teamtailor": text(root, "channel/title"), "workday": company.split(".")[0]}.get(platform) or company
    for row in rows:
        row.update(key=f"{platform}:{company}:{row['id']}", platform=platform, company=shown, board=row["url"])
    return rows


def main(folder: Path) -> None:
    store = folder / "postings.jsonl"
    seen = {json.loads(line)["key"] for line in store.open()} if store.exists() else set()
    fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new = failed = 0
    with store.open("a") as out:
        for line in (folder / "companies.txt").read_text().splitlines():
            company = parse_company(line)
            if company is None:
                continue
            try:
                if company[0] == "site":
                    company = resolve(folder, company[1])
                rows = postings(*company)
            except Exception as error:  # one board failing must not stop the others
                print(f"{company[0]} {company[1]}: failed ({error})", file=sys.stderr)
                failed += 1
                continue
            for row in rows:
                if row["key"] not in seen:
                    seen.add(row["key"])
                    out.write(json.dumps({**row, "fetched": fetched}) + "\n")
                    new += 1
            time.sleep(1)  # be polite to the job boards
    print(f"{new} new posting(s); {failed} board(s) failed")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent)
