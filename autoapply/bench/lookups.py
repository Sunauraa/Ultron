"""Fetch the live answers to the persona's search-as-you-type queries (city, school, degree) for each recorded
page, so the replay can answer them offline. Writes pages/NAME/lookups.json.

Only searches are sent (GET, or Ashby's read-only GraphQL search POST that the page itself sends on load), and
only for the persona's own values: nothing is typed into or submitted on the real site.
A query the agent types that matches no recorded one (neither starts it nor extends it) gets the endpoint's
real "no results" answer, so the agent must type something close to the persona's value, as on the real site.

Usage: python bench/lookups.py   (rewrites every page's lookups.json)
"""

import base64
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

PAGES = Path(__file__).resolve().parent / "pages"
NO_MATCH = "zzqxv"  # a query with no results, for the endpoint's empty answer
CITY = ["San Francisco, CA", "San Francisco", "United States"]
# The persona's value, then the shorter searches an agent (or a person) tries when that finds nothing.
SCHOOL = ["University of California, Berkeley", "University of California - Berkeley", "University of California Berkeley",
          "University of California", "University", "UC Berkeley", "Berkeley", "UC"]
DEGREE = ["", "Bachelor's Degree", "Bachelor of Science", "Bachelor", "Bachelors", "BS", "B.S."]
# Plain files the page loads only after a click (a flag sprite, a font), fetched as they are.
STATIC = re.compile(r"https://job-boards\.cdn\.greenhouse\.io/(assets/flags-[\w-]+\.webp|fonts/[\w-]+\.woff2?)|https://cdn\.lever\.co/fonts/[\w/.-]+\.woff2?")


def fetch(url: str, body: bytes | None = None, referer: str = "") -> dict:
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36",
               "Accept": "*/*", "Referer": referer}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, kind, data = response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as error:
        status, kind, data = error.code, error.headers.get("Content-Type", ""), error.read()
    return {"status": status, "content_type": kind.split(";")[0] or "application/octet-stream", "body_b64": base64.b64encode(data).decode()}


def ashby_search_template() -> dict:
    """The search request as an Ashby page sends it (taken from any recording that has one)."""
    for har in sorted(PAGES.glob("ashby_*/page.har")):
        for e in json.loads(har.read_text())["log"]["entries"]:
            if "ApiAutocompleteGeoLocation" in e["request"]["url"]:
                return json.loads(e["request"]["postData"]["text"])
    raise RuntimeError("no Ashby recording has a location search")


def endpoints(folder: Path) -> list[dict]:
    """The lookup endpoints this page uses, found in its recording."""
    har = (folder / "page.har").read_text()
    page_url = json.loads((folder / "meta.json").read_text())["url"]
    found = []
    key = re.search(r"LOCATION_CONTROL_API_KEY\W+(ge-[0-9a-f]{16})", har)  # the page's own public key, in its config
    if "greenhouse" in folder.name and key:
        api_key = key.group(1)
        endpoint = "https://api-geocode-earth-proxy.greenhouse.io/v1/autocomplete"
        found.append({"endpoint": endpoint, "method": "GET", "param": "text", "queries": CITY,
                      "url": lambda q, e=endpoint, k=api_key: f"{e}?api_key={k}&layers=locality&lang=en&text={urllib.parse.quote(q)}"})
    if folder.name.startswith("greenhouse_"):
        board = re.search(r"for=([\w-]+)", page_url).group(1)
        for kind, queries in (("schools", SCHOOL), ("degrees", DEGREE)):
            endpoint = f"https://boards.greenhouse.io/v1/boards/{board}/education/{kind}"
            found.append({"endpoint": endpoint, "method": "GET", "param": "term", "queries": [q for q in queries if q] + [""],
                          "url": lambda q, e=endpoint: f"{e}?term={urllib.parse.quote(q)}&page=1" if q else f"{e}?page=1"})
    if folder.name.startswith("lever_"):
        endpoint = "https://jobs.lever.co/searchLocations"
        found.append({"endpoint": endpoint, "method": "GET", "param": "text", "queries": CITY,
                      "url": lambda q, e=endpoint: f"{e}?text={urllib.parse.quote(q)}"})
    if folder.name.startswith("ashby_") and "ApiAutocompleteGeoLocation" in har:
        endpoint = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiAutocompleteGeoLocation"
        template = ashby_search_template()
        found.append({"endpoint": endpoint, "method": "POST", "json_path": ["variables", "text"], "queries": CITY,
                      "body": lambda q, t=template: json.dumps({**t, "variables": {**t["variables"], "text": q}}).encode()})
    return found


def main() -> None:
    for folder in sorted(PAGES.iterdir()):
        if not (folder / "page.har").exists():
            continue
        page_url = json.loads((folder / "meta.json").read_text())["url"]
        out = []
        for e in endpoints(folder):
            def get(q):
                return fetch(e["url"](q), referer=page_url) if "url" in e else fetch(e["endpoint"], e["body"](q), referer=page_url)
            answers = {q: get(q) for q in e["queries"]}
            entry = {k: v for k, v in e.items() if k in ("endpoint", "method", "param", "json_path")}
            out.append({**entry, "answers": answers, "none": get(NO_MATCH)})
        static = sorted(set(m.group(0) for m in STATIC.finditer((folder / "page.har").read_text())))
        for url in static:
            out.append({"endpoint": url, "method": "GET", "param": "", "answers": {"": fetch(url, referer=page_url)}, "none": None})
        (folder / "lookups.json").write_text(json.dumps(out))
        print(folder.name, [(o["endpoint"].split("/")[-1][:40], {q: a["status"] for q, a in o["answers"].items()}) for o in out])


if __name__ == "__main__":
    main()
