"""What a job's own board says about the job and the company, read from the platform's public job-board API
(the same read-only APIs fetch.py uses). Used for cover letters and "why this company" answers.

Only the board's own text is returned: the posting (title, location, description) and, where the board has one,
the company's intro. Nothing is looked up by company name elsewhere, so every fact is about this employer.
Lever, Ashby, BambooHR and Gem boards don't give the company's name. For Lever and Ashby it is read from the page
title only when the title has the exact form those sites use; otherwise it is left out rather than guessed.
Personio gives the hiring legal entity ("F24 AG"); Teamtailor gives its careers site's title.
"""

from __future__ import annotations

import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

MAX_DESCRIPTION = 3500
MAX_ABOUT = 1200
# Greenhouse's placeholder for a board with no intro.
PLACEHOLDER_ABOUT = {"this is the job board description"}


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "ul", "ol"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK:
            self.parts.append("\n- " if tag == "li" else "\n")

    def handle_endtag(self, tag):
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def text_of(markup: str) -> str:
    """Plain text of an HTML fragment (Greenhouse sends it entity-escaped, so it is unescaped first)."""
    if "&lt;" in markup and "<" not in markup:
        markup = html.unescape(markup)
    parser = _Text()
    parser.feed(markup)
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line not in ("", "-"))


def get_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "ultron-autoapply/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def _greenhouse(url, host, parts, page_title):
    query = parse_qs(urlparse(url).query)
    if query.get("for") and query.get("token"):
        board, job_id = query["for"][0], query["token"][0]
    elif len(parts) >= 3 and parts[1] == "jobs":
        board, job_id = parts[0], parts[2]
    else:
        return None
    job = get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}")
    company = job.get("company_name") or board
    about = ""
    try:
        info = get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}")
        company, about = info.get("name") or company, text_of(info.get("content") or "")
    except Exception:
        pass
    if about.strip(" .").casefold() in PLACEHOLDER_ABOUT:
        about = ""
    return dict(company=company, title=job["title"], location=(job.get("location") or {}).get("name", ""),
                description=text_of(job.get("content") or ""), about=about)


def _lever(url, host, parts, page_title):
    if len(parts) < 2:
        return None
    api = "api.eu.lever.co" if host.startswith("jobs.eu.") else "api.lever.co"
    job = get_json(f"https://{api}/v0/postings/{parts[0]}/{parts[1]}")
    sections = [job.get("descriptionPlain") or text_of(job.get("description") or "")]
    for item in job.get("lists") or []:
        sections.append(f"{item.get('text', '')}:\n{text_of(item.get('content') or '')}")
    sections.append(job.get("additionalPlain") or text_of(job.get("additional") or ""))
    categories = job.get("categories") or {}
    suffix = " - " + job["text"].strip()  # Lever's page title: "Company - Job title"
    company = page_title.strip()[:-len(suffix)].strip() if page_title.strip().endswith(suffix) else ""
    return dict(company=company, title=job["text"], location=categories.get("location", ""),
                description="\n".join(s.strip() for s in sections if s and s.strip()), about="")


def _ashby(url, host, parts, page_title):
    if len(parts) < 2:
        return None
    board = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{parts[0]}")
    job = next((j for j in board.get("jobs") or [] if j.get("id") == parts[1]), None)
    if job is None:
        return None
    prefix = job["title"].strip() + " @ "  # Ashby's page title: "Job title @ Company"
    company = page_title.strip()[len(prefix):].strip() if page_title.strip().startswith(prefix) else ""
    return dict(company=company, title=job["title"], location=job.get("location", ""),
                description=job.get("descriptionPlain") or text_of(job.get("descriptionHtml") or ""), about="")


def _workable(url, host, parts, page_title):
    if len(parts) < 3 or parts[1] != "j":
        return None
    account = get_json(f"https://apply.workable.com/api/v1/widget/accounts/{parts[0]}?details=true")
    job = next((j for j in account.get("jobs") or [] if j.get("shortcode") == parts[2]), None)
    if job is None:
        return None
    sections = [text_of(job.get(k) or "") for k in ("description", "requirements", "benefits")]
    location = ", ".join(x for x in (job.get("city"), job.get("country")) if x)
    return dict(company=account.get("name") or parts[0], title=job["title"], location=location,
                description="\n".join(s for s in sections if s), about=text_of(account.get("description") or ""))


def _recruitee(url, host, parts, page_title):
    if len(parts) < 2 or parts[0] != "o":
        return None
    offers = get_json(f"https://{host}/api/offers/")
    job = next((j for j in offers.get("offers") or [] if j.get("slug") == parts[1]), None)
    if job is None:
        return None
    sections = [text_of(job.get(k) or "") for k in ("description", "requirements")]
    return dict(company=job.get("company_name") or "", title=job["title"], location=job.get("location", ""),
                description="\n".join(s for s in sections if s), about="")


def get_xml(url: str) -> ET.Element:
    request = urllib.request.Request(url, headers={"User-Agent": "ultron-autoapply/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return ET.fromstring(response.read())


def _teamtailor(url, host, parts, page_title):
    if len(parts) < 2 or parts[0] != "jobs":
        return None
    channel = get_xml(f"https://{host}/jobs.rss").find("channel")
    link = f"https://{host}/jobs/{parts[1]}"
    job = next((j for j in channel.findall("item") if (j.findtext("link") or "").strip() == link), None)
    if job is None:
        return None
    tt = {"tt": "https://teamtailor.com/locations"}
    places = [p.findtext("tt:name", namespaces=tt) or p.findtext("tt:city", namespaces=tt) or "" for p in job.iterfind(".//tt:location", tt)]
    return dict(company=(channel.findtext("title") or "").strip(), title=job.findtext("title") or "",
                location=", ".join(p for p in places if p), description=text_of(job.findtext("description") or ""), about="")


def _personio(url, host, parts, page_title):
    if len(parts) < 2 or parts[0] != "job":
        return None
    # The feed is in the board's default language unless asked; ask for the language the form is shown in.
    language = (parse_qs(urlparse(url).query).get("display") or ["en"])[0]
    for feed in (f"https://{host}/xml?language={language}", f"https://{host}/xml"):
        job = next((j for j in get_xml(feed).findall("position") if j.findtext("id") == parts[1]), None)
        sections = [f"{d.findtext('name') or ''}:\n{text_of(d.findtext('value') or '')}" for d in (job.iter("jobDescription") if job is not None else [])
                    if (d.findtext("value") or "").strip()]
        if sections:
            break
    if job is None:
        return None
    return dict(company=job.findtext("subcompany") or "", title=job.findtext("name") or "", location=job.findtext("office") or "",
                description="\n".join(sections), about="")


def _bamboohr(url, host, parts, page_title):
    if len(parts) < 2 or parts[0] != "careers" or not parts[1].isdigit():
        return None
    job = get_json(f"https://{host}/careers/{parts[1]}/detail")["result"]["jobOpening"]
    where = job.get("location") or {}
    return dict(company="", title=job.get("jobOpeningName") or "", location=", ".join(v for v in (where.get("city"), where.get("state")) if v),
                description=text_of(job.get("description") or ""), about="")


def _gem(url, host, parts, page_title):
    if len(parts) < 2:
        return None
    job = next((j for j in get_json(f"https://api.gem.com/job_board/v0/{parts[0]}/job_posts/") if j.get("id") == parts[1]), None)
    if job is None:
        return None
    return dict(company="", title=job.get("title") or "", location=(job.get("location") or {}).get("name", ""),
                description=job.get("content_plain") or text_of(job.get("content") or ""), about="")


SITES = [(re.compile(r"(^|\.)greenhouse\.io$"), _greenhouse), (re.compile(r"^jobs\.(eu\.)?lever\.co$"), _lever),
         (re.compile(r"^jobs\.ashbyhq\.com$"), _ashby), (re.compile(r"^apply\.workable\.com$"), _workable),
         (re.compile(r"\.recruitee\.com$"), _recruitee), (re.compile(r"\.teamtailor\.com$"), _teamtailor),
         (re.compile(r"\.jobs\.personio\.(de|com)$"), _personio), (re.compile(r"\.bamboohr\.com$"), _bamboohr),
         (re.compile(r"^jobs\.gem\.com$"), _gem)]


# Boards that can sit on the company's own domain: recognised by jobs.txt's platform instead of the host.
ON_OWN_DOMAIN = {"recruitee": _recruitee, "teamtailor": _teamtailor}


def cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " […cut]"


def about_job(url: str, platform: str = "", page_title: str = "") -> dict | None:
    """{company, title, location, description, about} from the job's board, or None for a site without a public
    job API or a job it doesn't list (closed). url is the page's address after redirects (Workable's has the
    account in it); platform is jobs.txt's, for Recruitee and Teamtailor boards on the company's own domain. Network errors raise."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    parts = [p for p in parsed.path.split("/") if p]
    for pattern, read in SITES:
        if pattern.search(host) or ON_OWN_DOMAIN.get(platform) is read:
            found = read(url, host, parts, page_title)
            if found:
                for key in ("description", "about"):  # one blank line at most, no space-only lines
                    found[key] = re.sub(r"\n{3,}", "\n\n", "\n".join(line.strip() for line in found[key].splitlines())).strip()
                found["description"] = cut(found["description"], MAX_DESCRIPTION)
                found["about"] = cut(found["about"], MAX_ABOUT)
            return found
    return None


def describe(found: dict) -> str:
    lines = [f"Company: {found['company']}" if found["company"] else "Company: (the board doesn't name it; see the description)",
             f"Role: {found['title']}"]
    if found["location"]:
        lines.append(f"Location: {found['location']}")
    if found["about"]:
        lines += ["", "About the company (from its job board):", found["about"]]
    lines += ["", "Job description (from the posting):", found["description"] or "(empty)"]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    result = about_job(sys.argv[1])
    print(describe(result) if result else "No public job data for this URL.")
