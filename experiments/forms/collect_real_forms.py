"""Download public pages with one plain GET each and extract their form fields.

Page scripts are not run and nothing is submitted. Run with `python -I`, since the pages are
untrusted data. Usage: collect_real_forms.py URL_FILE OUT_DIR
"""

import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

SKIP_TYPES = {"hidden", "image", "reset", "file", "search", "password"}
TEXT_TYPES = {"text", "email", "tel", "number", "date", "url", ""}


def clean(text):
    return " ".join((text or "").split())


def field_label(soup, tag):
    if tag.get("id"):
        label = soup.find("label", attrs={"for": tag["id"]})
        if label:
            return clean(label.get_text(" "))
    parent = tag.find_parent("label")
    if parent:
        return clean(parent.get_text(" "))
    for attribute in ("aria-label", "placeholder", "title"):
        if tag.get(attribute):
            return clean(tag[attribute])
    return ""


def extract_google_form(html):
    """Read the question list a Google Forms page embeds as JSON."""
    marker = "FB_PUBLIC_LOAD_DATA_ = "
    start = html.find(marker)
    if start < 0:
        return None
    data, _ = json.JSONDecoder().raw_decode(html[start + len(marker):])
    roles = {0: "text", 1: "text", 2: "radio", 3: "select", 4: "checkbox", 9: "text", 10: "text"}
    fields = []
    for item in data[1][1] or []:
        role = roles.get(item[3])
        if role is None:
            continue
        field = {"role": role, "label": clean(item[1]), "name": str(item[0])}
        if role != "text" and item[4]:
            field["options"] = [clean(o[0]) for o in (item[4][0][1] or [])][:30]
        fields.append(field)
    return [{"fields": fields, "submit": None}]


def extract(html):
    google = extract_google_form(html)
    if google is not None:
        return google
    soup = BeautifulSoup(html, "html.parser")
    forms = []
    for form in soup.find_all("form"):
        fields = []
        submit = None
        for tag in form.find_all(["input", "select", "textarea", "button"]):
            kind = (tag.get("type") or "").lower()
            if tag.name == "button" or kind == "submit":
                if kind in ("submit", "") and submit is None:
                    submit = clean(tag.get_text(" ")) or clean(tag.get("value"))
                continue
            if tag.name == "input" and kind in SKIP_TYPES:
                continue
            role = {"select": "select", "textarea": "text"}.get(tag.name) or (
                "text" if kind in TEXT_TYPES else kind
            )
            field = {"role": role, "label": field_label(soup, tag), "name": tag.get("name")}
            if tag.name == "select":
                field["options"] = [clean(o.get_text()) for o in tag.find_all("option")][:30]
            fields.append(field)
        forms.append({"fields": fields, "submit": submit})
    return forms


def main():
    urls = [u.strip() for u in Path(sys.argv[1]).read_text().splitlines() if u.strip()]
    out = Path(sys.argv[2])
    (out / "raw").mkdir(parents=True, exist_ok=True)
    results = []
    seen = set()
    for i, url in enumerate(urls):
        host = urlparse(url).netloc
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research form survey)"})
            with urllib.request.urlopen(request, timeout=20) as response:
                html = response.read(3_000_000).decode("utf-8", errors="replace")
        except Exception as exc:
            print(f"FAIL {host}: {type(exc).__name__}")
            continue
        (out / "raw" / f"{i:03}.html").write_text(html)
        forms = extract(html)
        usable = [f for f in forms if sum(x["role"] == "text" and bool(x["label"]) for x in f["fields"]) >= 3]
        print(f"{'OK  ' if usable else 'none'} {host}: {len(forms)} forms, {len(usable)} usable")
        for form in usable:
            signature = tuple(x["label"] for x in form["fields"])
            if signature not in seen:
                seen.add(signature)
                results.append({"url": url, **form})
    (out / "extracted.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(f"\n{len(results)} usable forms")


if __name__ == "__main__":
    main()
