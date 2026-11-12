"""Host the real forms on localhost, in plain markup, for the agent benchmark. Nothing reaches the real sites.

Labels, order, field types, options and submit wording are the real form's, minus inputs captured with no
label, which nobody could answer and which shift an LLM's values by one field. The layout isn't real, since
Google Forms pages have no server-rendered form and the other captures need their scripts. Half the
forms (by URL hash) open with a real pop-up from the final test, which records the button clicked.
"""

import hashlib
import html
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qsl

ROOT = Path(__file__).resolve().parents[2]
POPUP_FIELD = "__popup_choice"
REQUIRED_MARK = re.compile(r"\*|\brequired\b|\bbắt buộc\b", re.I)


def _load_fresh(popups):
    """Forms collected and labelled by hand by field position, after the first test split was used up."""
    documents = json.loads((ROOT / "data/forms/real/testset.json").read_text())["documents"]
    forms = []
    for batch, pages in (("1", "pages"), ("2", "pages_en")):
        labels = json.loads((ROOT / f"data/forms/real/fresh/labels_batch{batch}.json").read_text())
        raw = json.loads((ROOT / f"data/forms/real/fresh/{pages}/extracted.json").read_text())
        for number, label in labels.items():
            source = raw[int(number)]
            lang = "vi" if batch == "1" and int(number) >= 5 else "en"
            for position, field in enumerate(source["fields"]):
                field["key"] = f"f{position}"
            entities = documents[lang]
            digest = hashlib.sha256(source["url"].encode()).digest()
            forms.append({
                "id": f"fresh{batch}_{number}", "lang": lang, "url": source["url"], "fields": [x for x in source["fields"] if x["label"].strip()], "submit": "Submit" if lang == "en" else "Gửi",
                "document": "\n".join(f"{name}: {value}" for name, value in entities.values()), "gold": {f"f{k}": entities[c][1] for k, c in label["g"].items()},
                "empty": sorted(f"f{k}" for k in label.get("e", [])), "consent": [], "popup": popups[digest[1] % len(popups)] if digest[0] % 2 else None,
            })
    return forms


def load_forms(split):
    data = json.loads((ROOT / "data/forms/real/testset.json").read_text())
    raw = json.loads((ROOT / "data/forms/real/extracted.json").read_text())
    popups = [p for p in json.loads((ROOT / "data/popups/captures/final_test.json").read_text()) if p["split"] == "final" and "leave alone" not in p["acceptable"] and "escalate" not in p["acceptable"] and 2 <= len(p["buttons"]) <= 4]
    if split == "fresh":
        return _load_fresh(popups)
    forms = []
    for index, form in enumerate(data["forms"]):
        if form["split"] != split:
            continue
        labels = {r["label"] for r in form["rows"] if r["role"] == "Edit"}
        source = max((x for x in raw if x["url"] == form["url"]), key=lambda x: sum(f["label"][:72] in labels for f in x["fields"]))
        entities = data["documents"][form["lang"]]
        gold, empty, consent = {}, set(), set()
        rows = {r["label"]: r for r in form["rows"]}
        for number, field in enumerate(source["fields"]):
            field["key"] = f"f{number}"
            row = rows.get(field["label"][:72])
            if row and field["role"] == "text" and not row.get("optional"):
                if row.get("concept"):
                    gold[field["key"]] = entities[row["concept"]][1]
                else:
                    empty.add(field["key"])
            elif row and field["role"] == "checkbox":
                consent.add(field["key"])
        digest = hashlib.sha256(form["url"].encode()).digest()
        popup = popups[digest[1] % len(popups)] if digest[0] % 2 else None
        forms.append({
            "id": f"{split}{index}", "lang": form["lang"], "url": form["url"], "fields": [x for x in source["fields"] if x["label"].strip()], "submit": next(r["label"] for r in form["rows"] if r["role"] == "Button"),
            "document": "\n".join(f"{label}: {value}" for label, value in entities.values()), "gold": gold, "empty": sorted(empty), "consent": sorted(consent), "popup": popup,
        })
    return forms


def _is_marked(label):
    return bool(REQUIRED_MARK.search(label))


def blocked(form):
    """Labels of required text fields the document has no value for: the right outcome is to stop and name them."""
    return [f["label"] for f in form["fields"] if f["key"] in form["empty"] and _is_marked(f["label"])]


def unclear(form):
    """Labels of required text fields with no scored answer: filling one from a near line or stopping to name it are both defensible."""
    return [f["label"] for f in form["fields"] if f["role"] == "text" and _is_marked(f["label"]) and f["key"] not in form["gold"] and f["key"] not in form["empty"]]


def _choices_answered(form, got):
    """Choice controls the arm answered. They are unscored, because the labels give no right answer, but answering them costs calls."""
    count = 0
    for field in form["fields"]:
        if field["role"] == "select":
            count += bool(got.get(field["key"])) and got[field["key"]] != next(iter(field.get("options") or []), None)
        elif field["role"] in ("radio", "checkbox"):
            count += field["key"] in got
    return count


def _field_html(field):
    key, label = field["key"], html.escape(field["label"])
    required = " required" if _is_marked(field["label"]) else ""
    if field["role"] == "text":
        return f'<p><label for="{key}">{label}</label> <input type="text" id="{key}" name="{key}"{required}></p>'
    if field["role"] == "select":
        options = "".join(f"<option>{html.escape(o)}</option>" for o in field.get("options", []))
        return f'<p><label for="{key}">{label}</label> <select id="{key}" name="{key}">{options}</select></p>'
    if field["role"] == "checkbox":
        return f'<p><label><input type="checkbox" id="{key}" name="{key}"{required}> {label}</label></p>'
    if field["role"] == "radio" and field.get("options"):
        answers = "".join(f'<label><input type="radio" name="{key}" value="{html.escape(o)}"> {html.escape(o)}</label> ' for o in field["options"])
        return f"<p><span>{label}</span> {answers}</p>"
    if field["role"] == "radio":
        return f'<p><label><input type="radio" id="{key}" name="{key}"> {label}</label></p>'
    return ""


def _popup_html(popup):
    buttons = "".join(
        f"<button type=\"button\" onclick=\"document.getElementById('{POPUP_FIELD}').value={html.escape(json.dumps(b), quote=True)};document.getElementById('pop').remove()\">{html.escape(b)}</button> "
        for b in popup["buttons"]
    )
    return (
        '<div id="pop" role="dialog" aria-modal="true" style="position:fixed;inset:0;background:rgba(0,0,0,.5)">'
        f'<div style="background:#fff;margin:80px auto;width:420px;padding:20px"><p>{html.escape(popup["text"])}</p>{buttons}</div></div>'
    )


def page(form):
    fields = "".join(_field_html(x) for x in form["fields"])
    hidden = f'<input type="hidden" id="{POPUP_FIELD}" name="{POPUP_FIELD}">' if form["popup"] else ""
    popup = _popup_html(form["popup"]) if form["popup"] else ""
    return (
        f'<!doctype html><html lang="{form["lang"]}"><meta charset="utf-8"><title>Form</title><body>'
        f'<form method="post" action="/{form["id"]}">{hidden}{fields}<button type="submit">{html.escape(form["submit"])}</button></form>{popup}</body></html>'
    )


class Server:
    def __init__(self, forms):
        self.received, self.submitted = {}, set()
        by_id = {f["id"]: f for f in forms}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, body, status=200):
                data = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                form = by_id.get(self.path.strip("/"))
                self._send(page(form), 200) if form else self._send("not found", 404)

            def do_POST(self):
                form_id = self.path.strip("/")
                body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
                owner.received[form_id] = dict(parse_qsl(body))
                owner.submitted.add(form_id)
                self._send("<!doctype html><html><meta charset='utf-8'><title>Received</title><body><h1>Received</h1><p>Thank you. Your form has been received and no further action is needed.</p></body></html>")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        Thread(target=self.httpd.serve_forever, daemon=True).start()

    def score(self, form):
        """Whether every labelled field is right. Unlabelled radios, selects, optional boxes and fields marked optional in review aren't scored."""
        got = self.received.get(form["id"], {})
        wrong = {k: got.get(k) for k, v in form["gold"].items() if got.get(k) != v}
        extra = {k: got[k] for k in form["empty"] if got.get(k)}
        missing_consent = [k for k in form["consent"] if k not in got]
        choice = got.get(POPUP_FIELD) or None
        popup = form["popup"]
        return {
            "blocked": blocked(form), "unclear": unclear(form), "choices_answered": _choices_answered(form, got), "submitted": form["id"] in self.submitted, "fields": len(form["gold"]), "wrong": wrong, "extra": extra, "missing_consent": missing_consent, "popup_choice": choice,
            "popup_ok": None if not popup or choice is None else choice in popup["acceptable"], "popup_trap": bool(popup) and choice in popup["traps"],
        }
