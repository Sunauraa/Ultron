"""The fields of each recorded application form, read from the platform's own form definition inside the recording
(not from what either agent sees), so the real-page benchmark's gold answers cover every field the employer asks for.

Each field: key (the name the platform submits it under), label, type, required, options (the visible choices).
Writes pages/NAME/fields.json.

Usage: python -I bench/fields.py   (every page in bench/pages)
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def entries(folder: Path) -> list[dict]:
    return json.loads((folder / "page.har").read_text())["log"]["entries"]


def text(entry: dict) -> str:
    return entry["response"]["content"].get("text") or ""


def field(key, label, kind, required, options=None, section="", values=None) -> dict:
    """values: what the platform sends for each option (an id), where that differs from the option's text."""
    return {"key": str(key), "label": " ".join(str(label or "").split()), "type": kind, "required": bool(required),
            "options": options or [], "section": section, "values": [str(v) for v in values or []]}


def greenhouse(folder: Path) -> list[dict]:
    page = next(text(e) for e in entries(folder) if "job_app" in e["request"]["url"] and "html" in e["response"]["content"].get("mimeType", ""))
    start = page.find("window.__remixContext")
    data = page[start:page.find("</script>", start)]
    post = json.loads(data[data.find("{"):data.rfind("}") + 1])["state"]["loaderData"]["routes/embed.job_app"]["jobPost"]
    fields = []
    for q in post["questions"]:
        for f in q["fields"]:
            fields.append(field(f["name"], q["label"], f["type"], q["required"] and not f["name"].endswith("_text"),
                                [v["label"] for v in f.get("values", [])], "questions", [v["value"] for v in f.get("values", [])]))
    education = post.get("education_config") or {}
    for name in ("school_name", "degree", "discipline", "start_date", "end_date"):
        setting = education.get(name)
        if setting in ("required", "optional"):
            fields.append(field(f"education.{name}", name.replace("_", " "), "education", setting == "required", section="education"))
    for section in post.get("eeoc_sections") or []:
        for q in section["questions"]:
            for f in q["fields"]:
                fields.append(field(f["name"], q["label"], f["type"], q.get("required"), [v["label"] for v in f.get("values", [])], "eeoc",
                                    [v["value"] for v in f.get("values", [])]))
    return fields


# Lever's standard fields carry their label outside the field's box; these are the labels its form shows.
LEVER_LABELS = {"name": "Full name", "email": "Email", "phone": "Phone", "location": "Current location", "org": "Current company",
                "resume": "Resume/CV", "pronouns": "Pronouns", "opportunityLocationId": "Location of this opening",
                "comments": "Additional information", "eeo[gender]": "Gender", "eeo[race]": "Race", "eeo[veteran]": "Veteran status",
                "eeo[disability]": "Disability status"}


def lever(folder: Path) -> list[dict]:
    from bs4 import BeautifulSoup
    page = next(text(e) for e in entries(folder) if e["request"]["url"].endswith("/apply"))
    form = BeautifulSoup(page, "html.parser").find("form")
    fields, seen = [], set()
    for card in form.select('input[type=hidden][name^="cards["][name$="[baseTemplate]"]'):
        cid = re.match(r"cards\[([^\]]+)\]", card["name"]).group(1)
        for n, f in enumerate(json.loads(card["value"])["fields"]):
            fields.append(field(f"cards[{cid}][field{n}]", f["text"], f["type"], f.get("required"),
                                [o["text"] for o in f.get("options", [])], "card"))
            seen.add(f"cards[{cid}][field{n}]")
    for control in form.find_all(["input", "select", "textarea"]):
        name = control.get("name")
        if not name or name in seen or control.get("type") == "hidden" or name.startswith("cards["):
            continue
        seen.add(name)
        box = control.find_parent(class_=re.compile("application-question|application-field|eeo-question")) or control.parent
        label = box.find(class_=re.compile("application-label|eeo-label")) or box
        options = [o.get_text(" ", strip=True) for o in control.find_all("option") if o.get("value")] if control.name == "select" else \
            [i.get("value") for i in form.find_all("input", attrs={"name": name}) if i.get("type") in ("checkbox", "radio")]
        label = LEVER_LABELS.get(name) or label.get_text(" ", strip=True)[:200]
        fields.append(field(name, label, control.get("type") or control.name, control.has_attr("required"), options, "form"))
    return fields


def ashby(folder: Path) -> list[dict]:
    data = json.loads(next(text(e) for e in entries(folder) if "op=ApiJobPosting" in e["request"]["url"]))
    post = data["data"]["jobPosting"]
    if not post:
        return []
    fields = []
    for kind, form in [("application", post["applicationForm"])] + [("survey", s) for s in post.get("surveyForms") or []]:
        for section in form["sections"]:
            for entry in section["fieldEntries"]:
                f = entry["field"]
                options = [v["label"] for v in f.get("selectableValues") or []]
                fields.append(field(f["path"], f["title"], f["type"], entry["isRequired"], options, kind,
                                    [v["value"] for v in f.get("selectableValues") or []]))
    return fields


def workable(folder: Path) -> list[dict]:
    form = json.loads(next(text(e) for e in entries(folder) if re.search(r"/api/v1/jobs/[^/]+/form$", e["request"]["url"])))
    fields = []
    for section in form:
        for f in section["fields"]:
            choices = f.get("choices") or f.get("options") or []
            options = [" ".join(str(c.get("value") or c.get("body") or c.get("name")).split()) for c in choices]
            fields.append(field(f["id"], f["label"], f["type"], f.get("required"), options, section.get("name") or "",
                                [c.get("name") or c.get("id") or "" for c in choices]))
    return fields


def recruitee(folder: Path) -> list[dict]:
    page = next(text(e) for e in entries(folder) if "/c/new" in e["request"]["url"])
    config = next(json.loads(html.unescape(m.group(1)))["appConfig"] for m in re.finditer(r'data-props="([^"]*)"', page)
                  if "appConfig" in html.unescape(m.group(1))[:20])
    offer = config["offer"]  # the posting this page applies to (config["offers"] lists the site's other postings)
    fields = [field("name", "Full name", "text", True), field("email", "Email", "email", True)]
    for name, setting in offer["fields"].items():
        if setting != "off":
            fields.append(field(name, name, "standard", setting == "required"))
    for q in offer["openQuestions"]:
        language = next(iter(q["translations"]))
        t = q["translations"][language]
        fields.append(field(f"open_question_{q['id']}", t["body"], q["kind"], q["required"], [o if isinstance(o, str) else o.get("body") for o in t.get("options") or []], "questions"))
    for a in config.get("agreements") or []:
        language = next(iter(a["translations"]))
        body = " ".join(c.get("text", "") for p in a["translations"][language]["body"] for c in p.get("children", []))
        fields.append(field(f"agreement_{a['id']}", body, "agreement", True, section="agreements"))
    return fields


READERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "workable": workable, "recruitee": recruitee}

if __name__ == "__main__":
    for folder in sorted((HERE / "pages").iterdir()):
        try:
            fields = READERS[folder.name.split("_")[0]](folder)
        except Exception as error:
            print(f"{folder.name}: FAILED {type(error).__name__}: {error}")
            continue
        (folder / "fields.json").write_text(json.dumps(fields, ensure_ascii=False, indent=1))
        print(f"{folder.name}: {len(fields)} fields, {sum(f['required'] for f in fields)} required")
