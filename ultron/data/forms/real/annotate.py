"""Turn extracted real forms into a labelled decision set with a dev/test split by form.

Each language has one fictional person's document, worded differently from most forms. A text
field's expected action is `fill` with the matching document entry, or `skip` if the document
has nothing for it. Fields about someone else (parent, relative, referrer) are `skip`.
Rules below were checked by reading the printed output. Run with `python -I`.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

VI = re.compile("[ăâđêôơưàáảãạèéẻẽẹìíỉĩịòóỏõọùúủũụỳýỷỹỵ]", re.I)
OTHER_PERSON = re.compile(
    r"phụ huynh|\bbố\b|\bmẹ\b|\bcha\b|người nhà|người thân|người giới thiệu|người nhận|báo tin|responsible adult|on behalf|parent",
    re.I,
)
# Questions and instructions that only happen to contain a matched word.
PROMPT = re.compile(
    r"^(if |please |vui lòng|xin |bạn |theo |\d+\\. theo |câu hỏi|- đối với)|nơi cư trú|ngày cấp|địa chỉ cơ quan|muốn ứng tuyển|middle name|house number",
    re.I,
)
# Checked by hand: the wording is clear to a person, but the rules get it wrong.
OVERRIDES = {"Street name *": "address", "Họ Tên (học viên hoặc phụ huynh)": "full_name"}
UNSCORED = re.compile(r"^(-- / -- / ----|search|δ|website)$", re.I)

DOCUMENTS = {
    "en": {
        "full_name": ("Applicant", "Jordan Avery Reed"),
        "first": ("Given name", "Jordan"),
        "last": ("Family name", "Reed"),
        "dob": ("Born", "02/17/1990"),
        "phone": ("Contact number", "503-555-0147"),
        "email": ("E-mail address", "jordan.reed@example.com"),
        "address": ("Residence", "742 Cedar Lane"),
        "city": ("Municipality", "Portland"),
        "state": ("Province or state", "Oregon"),
        "zip": ("Postcode", "97201"),
    },
    "vi": {
        "full_name": ("Tên đầy đủ", "Phạm Thu Hà"),
        "dob": ("Sinh ngày", "21/06/1995"),
        "id": ("Căn cước", "001195004567"),
        "phone": ("Di động", "0934567890"),
        "email": ("Hòm thư", "ha.pham@example.com"),
        "address": ("Nơi ở", "45 Trần Phú, Ba Đình"),
        "school": ("Nơi học", "Trường THPT Chu Văn An"),
        "company": ("Nơi làm việc", "Công ty TNHH Minh Long"),
    },
}
RULES = {
    "en": [
        ("email", r"e-?mail"),
        ("phone", r"phone|telephone|mobile"),
        ("dob", r"date of birth"),
        ("first", r"first name|forename"),
        ("last", r"last name|surname"),
        ("full_name", r"\bname\b"),
        ("zip", r"\bzip\b|post ?code"),
        ("city", r"\bcity\b|\btown\b"),
        ("state", r"\bstate\b"),
        ("address", r"address1?\b|street"),
    ],
    "vi": [
        ("email", r"e-?mail|thư điện tử"),
        ("phone", r"điện thoại|sđt|\btel\b"),
        ("dob", r"ngày.*sinh|^\W*(\d+\W*)?ngày sinh"),
        ("id", r"cccd|cmnd|chứng minh|căn cước"),
        ("full_name", r"họ.*tên|^tên( khách hàng)?$"),
        ("school", r"trường"),
        ("company", r"công ty|cơ quan|đơn vị"),
        ("address", r"địa chỉ"),
    ],
}
# Text fields that mention a matched word but ask for something else.
NOT_ADDRESS = re.compile(r"nhận sách|tham gia|link|facebook|skype|ip\b", re.I)
SUBMIT = {"en": "Submit", "vi": "Gửi"}


def concept(label, lang):
    for prefix, key in OVERRIDES.items():
        if label.startswith(prefix):
            return key
    if OTHER_PERSON.search(label) or PROMPT.search(label):
        return None
    for key, pattern in RULES[lang]:
        if re.search(pattern, label, re.I):
            if key == "address" and NOT_ADDRESS.search(label):
                return None
            return key
    return None


def main():
    root = Path(sys.argv[1])
    forms = json.loads((root / "extracted.json").read_text())
    out = []
    for form in forms:
        labels = [x["label"] for x in form["fields"] if x["role"] == "text" and x["label"]]
        if any("Comment *" == x for x in labels):  # a blog comment box, not a form
            continue
        lang = "vi" if VI.search(" ".join(labels)) else "en"
        rows = []
        for label in labels:
            if UNSCORED.match(label):
                continue
            rows.append({"role": "Edit", "label": label[:72], "concept": concept(label, lang)})
        for x in form["fields"]:
            if x["role"] == "checkbox" and x["label"] and re.search(r"consent|đồng ý|xác nhận", x["label"], re.I):
                rows.append({"role": "CheckBox", "label": x["label"][:72], "action": "check"})
        submit = form["submit"] if form["submit"] and "sign in" not in form["submit"].lower() else SUBMIT[lang]
        rows.append({"role": "Button", "label": submit, "action": "click"})
        digest = hashlib.sha256(form["url"].encode() + str(labels).encode()).digest()[0]
        out.append({"url": form["url"], "lang": lang, "split": "test" if digest % 2 else "dev", "rows": rows})
    (root / "testset.json").write_text(
        json.dumps({"documents": DOCUMENTS, "forms": out}, ensure_ascii=False, indent=1)
    )
    for lang in ("en", "vi"):
        for split in ("dev", "test"):
            chosen = [f for f in out if f["lang"] == lang and f["split"] == split]
            rows = [r for f in chosen for r in f["rows"]]
            filled = sum(1 for r in rows if r.get("concept"))
            print(f"{lang} {split}: {len(chosen)} forms, {len(rows)} decisions, {filled} fills")
    if "--show" in sys.argv:
        for f in out:
            print(f"\n{f['lang']} {f['split']} {f['url'][8:40]}")
            print("  " + " | ".join(f"{r['label'][:30]}={r.get('concept') or r.get('action') or 'skip'}" for r in f["rows"]))


if __name__ == "__main__":
    main()
