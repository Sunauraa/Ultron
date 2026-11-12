"""Score one real-page episode on what the page sent: decode the application request per platform into
{field key: value}, then compare with the gold (gold.py).

Decoded value: a string, a list of strings (multi-select), "" (empty), or UNVERIFIED (filled, but the request
carries only an id this offline copy can't name, e.g. a school picked from a search; counted as filled, never wrong).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import gold

HERE = Path(__file__).resolve().parent
UNVERIFIED = "<unverified id>"


def fields_of(name: str) -> dict:
    return {f["key"]: f for f in json.loads((HERE / "pages" / name / "fields.json").read_text())}


def label_of(field: dict | None, value) -> str:
    """An option's text from what the platform sends for it (an id), or the value itself."""
    value = "" if value is None else str(value)
    if field and value in field.get("values", []):
        return field["options"][field["values"].index(value)]
    return value


def multipart(sent: dict) -> list[tuple[str, str]]:
    """(name, value) pairs of a multipart body; a file part's value is its file name."""
    boundary = re.search(r"boundary=(\S+)", sent["headers"].get("content-type", ""))
    if not boundary:
        return []
    pairs = []
    for part in sent["body"].split("--" + boundary.group(1)):
        head, _, body = part.partition("\r\n\r\n")
        name = re.search(r'name="([^"]*)"', head)
        if not name:
            continue
        filename = re.search(r'filename="([^"]*)"', head)
        pairs.append((name.group(1), filename.group(1) if filename else body.rstrip("\r\n")))
    return pairs


def is_application(platform: str, sent: dict) -> bool:
    url = sent["url"]
    return {"greenhouse": re.search(r"boards\.greenhouse\.io/embed/[^/]+/jobs/\d+", url) and sent["method"] == "POST",
            "lever": url.endswith("/apply") and sent["method"] == "POST",
            "ashby": "op=ApiSubmitSingleApplicationFormAction" in url,
            "workable": re.search(r"/api/v1/jobs/[^/]+/apply$", url),
            "recruitee": url.rstrip("/").endswith("/candidates")}[platform]


def greenhouse(fields: dict, sent: list[dict]) -> dict:
    app = json.loads(sent[0]["body"])["job_application"]
    out = {k: app.get(k) or "" for k in ("first_name", "last_name", "email", "phone", "preferred_name")}
    out["candidate_location"] = app.get("location") or ""
    out["resume"] = app.get("resume_url_filename") or ""
    out["resume_text"] = app.get("resume_text") or ""
    out["cover_letter"] = app.get("cover_letter_url_filename") or ""
    out["cover_letter_text"] = app.get("cover_letter_text") or ""
    for qid, answer in (app.get("answers_attributes") or {}).items():
        key = next((k for k in (f"question_{qid}", f"question_{qid}[]") if k in fields), f"question_{qid}")
        field = fields.get(key)
        if answer.get("text_value") is not None:
            out[key] = answer["text_value"]
        elif answer.get("boolean_value") is not None:
            out[key] = label_of(field, int(answer["boolean_value"]))
        elif answer.get("answer_selected_options_attributes"):
            labels = [label_of(field, o["question_option_id"]) for o in answer["answer_selected_options_attributes"].values()]
            out[key] = labels if key.endswith("[]") else labels[0]
        else:
            out[key] = ""
    for key in ("gender", "race", "veteran_status", "disability_status", "hispanic_ethnicity"):
        if key in fields:
            out[key] = label_of(fields[key], app.get(key)) if app.get(key) not in (None, "") else ""
    education = (app.get("educations") or [{}])[0]
    out["education.school_name"] = UNVERIFIED if education.get("school_name_id") else ""
    out["education.degree"] = UNVERIFIED if education.get("degree_id") else ""
    return out


def lever(fields: dict, sent: list[dict]) -> dict:
    values: dict[str, list[str]] = {}
    for name, value in multipart(sent[0]):
        values.setdefault(name, []).append(value)
    out = {}
    for key, field in fields.items():
        given = [v for v in values.get(key, []) if v.strip()]
        multi = field["type"] in ("checkbox", "multiple-select")
        if field["type"] == "checkbox" and field["options"]:  # an unticked box can send a hidden "0" under the same name
            given = [v for v in given if v in field["options"] or key == "pronouns"]
        out[key] = given if multi else (given[0] if given else "")
    return out


def ashby(fields: dict, sent: list[dict], submits: list[dict]) -> dict:
    """Ashby keeps the form on its server: each field is sent when set (setFormValue); submit only names the form."""
    first = min(i for i, s in enumerate(sent) if s in submits)
    out = {}
    for request in sent[:first + 1]:
        try:
            body = json.loads(request["body"])
        except ValueError:
            continue
        variables = body.get("variables") or {} if isinstance(body, dict) else {}
        if "op=ApiSetFormValueToFile" in request["url"]:
            out[variables.get("path", "")] = "resume.pdf"
        elif "op=ApiSetFormValue" in request["url"]:
            path, value = variables.get("path", ""), variables.get("value")
            field = fields.get(path)
            if isinstance(value, bool):
                value = "Yes" if value else "No"
            elif isinstance(value, list):
                value = [label_of(field, v) for v in value]
            elif isinstance(value, dict):  # a location picked from search
                value = ", ".join(str(v) for v in value.values() if isinstance(v, str))
            else:
                value = label_of(field, value)
            out[path] = value
    return out


def workable(fields: dict, sent: list[dict]) -> dict:
    out = {}
    for item in json.loads(sent[0]["body"]).get("candidate", []):
        key, value, field = item.get("name"), item.get("value"), fields.get(item.get("name"))
        if isinstance(value, bool):
            value = "Yes" if value else "No"
        elif isinstance(value, dict):
            value = value.get("name") or json.dumps(value)
        elif isinstance(value, list):
            value = [label_of(field, v if not isinstance(v, dict) else v.get("name")) for v in value] if field and field["values"] else (UNVERIFIED if value else "")
        else:
            value = label_of(field, value)
        out[key] = value
    return out


def recruitee(fields: dict, sent: list[dict]) -> dict:
    pairs = multipart(sent[0])
    flat = {}
    for name, value in pairs:
        flat.setdefault(name, []).append(value)
    one = lambda k: next((v for v in flat.get(k, []) if v.strip()), "")
    out = {"name": one("candidate[name]"), "email": one("candidate[email]"), "phone": one("candidate[phone]"),
           "cv": one("candidate[cv]"), "coverLetter": one("candidate[coverLetter]") or one("candidate[coverLetterFile]")}
    answers: dict[str, dict] = {}
    for name, value in pairs:
        m = re.match(r"candidate\[openQuestionAnswers\]\[(\d+)\]\[(\w+)\]", name)
        if m and value.strip():
            answers.setdefault(m.group(1), {}).setdefault(m.group(2), []).append(value)
    for parts in answers.values():  # seen sent: [content] for text and single choice, [flag] true/false for yes/no
        qid = (parts.pop("openQuestionId", None) or [""])[0]
        given = [{"true": "Yes", "false": "No"}[v] if k == "flag" else v for k, vs in parts.items() for v in vs]
        out[f"open_question_{qid}"] = given if len(given) > 1 else (given[0] if given else "")
    agreements: dict[str, dict] = {}  # seen sent: [agreements][N][consent] = true, [agreements][N][agreementId] = 328
    for name, value in pairs:
        m = re.match(r"candidate\[agreements\]\[(\d+)\]\[(\w+)\]", name)
        if m:
            agreements.setdefault(m.group(1), {})[m.group(2)] = value
    for parts in agreements.values():
        if parts.get("agreementId"):
            out[f"agreement_{parts['agreementId']}"] = "Yes" if parts.get("consent") == "true" else ""
    out["_raw_keys"] = sorted({n for n, _ in pairs})
    return out


def norm(value) -> str:
    return " ".join(str(value).replace("’", "'").replace("“", '"').replace("”", '"').split()).casefold().rstrip(".")


def filled(value) -> bool:
    return value == UNVERIFIED or (bool([v for v in value if str(v).strip()]) if isinstance(value, list) else bool(str(value or "").strip()))


def matches(rule: dict, value) -> bool:
    if value == UNVERIFIED:
        return True
    values = value if isinstance(value, list) else [value]
    if "is" in rule or "debate" in rule:
        accepted = {norm(a) for a in rule.get("is", rule.get("debate"))}
        accepted |= {norm(p) for a in accepted for p in a.split(", ")}
        return all(norm(v) in accepted for v in values if str(v).strip()) or norm(", ".join(map(str, values))) in accepted
    if "contains" in rule:
        return any(norm(p) in norm(" ".join(map(str, values))) for p in rule["contains"])
    if "phone" in rule:
        return re.sub(r"\D", "", " ".join(map(str, values))).endswith(rule["phone"])
    if "none" in rule:
        return all(norm(v) in {"no", "none", "n/a", "na", "-", "not applicable"} for v in values)
    return True  # write, any, file, need: any filled value


def score(name: str, sent: list[dict]) -> dict:
    platform = name.split("_")[0]
    rules, fields = gold.resolve(name), fields_of(name)
    applications = [s for s in sent if is_application(platform, s)]
    hold = gold.must_hold(name)
    debatable = any("debate" in r for r in rules.values())
    # Scored on the first application: the one the employer gets (a later resend is a duplicate at best).
    result = {"submitted": bool(applications), "applications": len(applications), "must_hold": hold, "debatable": debatable,
              "wrong": [], "extra": [], "missing": [], "missed_optional": [], "unscored_keys": []}
    if applications:
        if platform == "ashby":
            decoded = ashby(fields, sent, applications)
        else:
            decoded = {"greenhouse": greenhouse, "lever": lever, "workable": workable, "recruitee": recruitee}[platform](fields, applications)
        raw_keys = decoded.pop("_raw_keys", None)
        result["decoded"] = decoded
        result["unscored_keys"] = sorted(k for k in decoded if k not in rules and filled(decoded[k]))
        if raw_keys is not None:
            result["raw_keys"] = raw_keys
        for key, rule in rules.items():
            value, required = decoded.get(key, ""), fields[key]["required"]
            if not filled(value):
                if required and not ({"empty", "none", "any", "need"} & set(rule)) and "debate" not in rule:
                    result["missing"].append(key)
                elif {"is", "contains", "phone", "file"} & set(rule):
                    result["missed_optional"].append(key)
            elif "empty" in rule:
                result["extra"].append(key)
            elif not matches(rule, value):
                result["wrong"].append({"key": key, "label": fields[key]["label"][:80], "sent": value})
    if hold:
        result["correct"] = not result["submitted"]
    elif not result["submitted"]:
        result["correct"] = debatable
    else:
        result["correct"] = not (result["wrong"] or result["extra"] or result["missing"])
    return result
