"""Smoke test of cua-s1-forms on one hand-written form, English vs Vietnamese.

Not an evaluation: one form, labels written by hand, no real pages.
"""

import random
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party/cua/libs/cua-s1/python/src"))

from cua_s1.model import ChoiceExample, load_checkpoint  # noqa: E402
from cua_s1.schema import Element, Entity, render_context, render_options  # noqa: E402

# (english label, vietnamese label, value)
FIELDS = [
    ("Full name", "Họ và tên", "Nguyen Van An"),
    ("Date of birth", "Ngày sinh", "14/03/1991"),
    ("Email address", "Thư điện tử", "an.nguyen@example.com"),
    ("Phone number", "Số điện thoại", "0912345678"),
    ("Home address", "Địa chỉ thường trú", "12 Le Loi, Quan 1"),
    ("City", "Thành phố", "Ho Chi Minh"),
    ("Postal code", "Mã bưu chính", "700000"),
    ("Company name", "Tên công ty", "An Phat Co"),
    ("Job title", "Chức danh", "Accountant"),
    ("National ID number", "Số căn cước công dân", "079091000123"),
    ("Tax code", "Mã số thuế", "0312345678"),
    ("Bank account number", "Số tài khoản ngân hàng", "190333444555"),
    ("Nationality", "Quốc tịch", "Vietnamese"),
    ("Gender", "Giới tính", "Male"),
]
NOT_IN_DOC = [("Fax number", "Số fax"), ("Referral code", "Mã giới thiệu")]
CHECKBOX = ("I agree to the terms", "Tôi đồng ý với các điều khoản")
BUTTON = ("Submit", "Gửi")
TITLE = ("Employee registration", "Đăng ký nhân viên")


def build(form_lang: int, doc_lang: int):
    entities = [Entity(f[doc_lang], f[2]) for f in FIELDS]
    random.Random(0).shuffle(entities)
    values = [e.value for e in entities]
    rows = []
    for field in FIELDS:
        rows.append((Element("Edit", field[form_lang]), values.index(field[2])))
    skip, check, click = (len(entities) + i for i in (2, 0, 1))
    rows += [(Element("Edit", n[form_lang]), skip) for n in NOT_IN_DOC]
    # Already holds the document's value, so the expected action is a no-op.
    rows.append((Element("Edit", FIELDS[0][form_lang], value=FIELDS[0][2]), skip))
    rows.append((Element("CheckBox", CHECKBOX[form_lang], checked=False), check))
    rows.append((Element("Button", BUTTON[form_lang]), click))
    return entities, rows


def main() -> None:
    model, collate, config = load_checkpoint(ROOT / "third_party/models/cua-s1-forms/cua-s1-forms.safetensors", "cpu")
    for name, form_lang, doc_lang in [
        ("EN form, EN doc", 0, 0),
        ("VI form, VI doc", 1, 1),
        ("VI form, EN doc", 1, 0),
    ]:
        entities, rows = build(form_lang, doc_lang)
        options = tuple(render_options(entities))
        title = TITLE[form_lang]
        examples = [ChoiceExample(render_context(title, e), options, gold) for e, gold in rows]
        with torch.no_grad():
            scores = model(collate(examples))
        probs = scores.softmax(-1)
        conf, pred = probs.max(-1)
        gold = torch.tensor([r[1] for r in rows])
        right = pred == gold
        print(f"\n{name}: {right.sum().item()}/{len(rows)} correct, mean confidence {conf.mean():.3f}")
        print(f"  wrong at confidence >= 0.9: {((~right) & (conf >= 0.9)).sum().item()}")
        print(f"  option bytes: max {max(len(o.encode()) for o in options)} (limit {config['option_tokens']})")
        print(f"  context bytes: max {max(len(x.context.encode()) for x in examples)} (limit {config['context_tokens']})")
        for (element, g), p, c in zip(rows, pred.tolist(), conf.tolist()):
            if g != p:
                print(f"  MISS {element.label!r} value={element.value!r}: want {options[g]!r}, got {options[p]!r} ({c:.2f})")


if __name__ == "__main__":
    main()
