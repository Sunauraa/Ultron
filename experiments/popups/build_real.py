"""Train on real pop-ups labelled by the LLM, plus the LLM-written and template ones.
Usage: build_real.py LABELS.jsonl LLM.jsonl OUT_DIR ROWS [REAL_SHARE] [NOT_POPUP_SHARE]

A real pop-up's label counts only if both LLM passes agree. Elements both passes called not a pop-up
become leave alone, so the model sees menus and video players. Sites are held out whole.
"""

import hashlib
import json
import random
import re
import sys
from pathlib import Path

from build_dialogs import ANSWER, TEMPLATE_SHARE, row
from synth_dialogs import ESCALATE, LEAVE, TASK, dialog_context, episode

# The labeller sometimes takes the offer. This cleans training labels only; the model has no rules.
OFFER = re.compile(r"claim|offer|buy|subscribe|abonn|sign up|join|nhận (thưởng|ngay|quà|ưu đãi)|mua|đăng ký", re.I)


# Half the real rows were not pop-ups, which taught the model to leave real banners alone.
NOT_POPUP_SHARE = float(sys.argv[6]) if len(sys.argv) > 6 else 0.15


def with_buttons(example):
    example["context"] = dialog_context(example["context"].removeprefix(TASK), example["options"])
    return example


def real_label(item):
    a, b = item["votes"]
    if a.get("is_popup") is False and b.get("is_popup") is False:
        return LEAVE, "not_popup"
    if a.get("is_popup") is True and b.get("is_popup") is True and a.get("action") and a["action"] == b.get("action"):
        if not OFFER.search(a["action"]):
            return a["action"], str(a.get("kind"))
    return None, None


def real_row(rng, item, answer, kind):
    """Same pop-up with its buttons reordered, sometimes with leading text or spare buttons gone."""
    text = item["text"]
    if rng.random() < 0.3:
        text = text[text.find(" ", rng.randint(0, len(text) // 4)) + 1:] or text
    buttons = [b for b in item["buttons"] if b == answer or rng.random() > 0.1]
    rng.shuffle(buttons)
    options = [f"click {b}" for b in buttons] + [LEAVE, ESCALATE]
    target = answer if answer in (LEAVE, ESCALATE) else f"click {answer}"
    return {"context": TASK + text, "options": options, "label": options.index(target), "meta": {"action": kind}}


def main():
    labels, source, out, rows = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4])
    real_share = float(sys.argv[5]) if len(sys.argv) > 5 else 0.4
    rng = random.Random(7)
    train_real, validation_real = [], []
    for line in labels.open():
        item = json.loads(line)
        answer, kind = real_label(item)
        if answer and (answer in (LEAVE, ESCALATE) or answer in item["buttons"]):
            held_out = hashlib.sha256(item["url"].encode()).digest()[1] < 26
            (validation_real if held_out else train_real).append((item, answer, kind))
    llm = {}
    for line in source.open():
        item = json.loads(line)
        needs_safe = item["kind"] not in ANSWER
        if len(item["text"]) >= 10 and item["other"] and item["other"] != item["safe"] and (item["safe"] or not needs_safe):
            llm.setdefault(item["text"], item)
    train_llm = [x for t, x in llm.items() if hashlib.sha256(t.encode()).digest()[0] >= 26]
    validation_llm = [x for t, x in llm.items() if hashlib.sha256(t.encode()).digest()[0] < 26]
    print(len(train_real), "real train,", len(validation_real), "real held out,", len(train_llm), "written train,", len(validation_llm), "written held out")
    popups = [x for x in train_real if x[2] != "not_popup"]
    negatives = [x for x in train_real if x[2] == "not_popup"]
    print(len(popups), "pop-ups,", len(negatives), "not pop-ups")
    out.mkdir(parents=True, exist_ok=True)
    with (out / "train.jsonl").open("w") as f:
        for _ in range(rows):
            draw = rng.random()
            if draw < real_share:
                example = real_row(rng, *rng.choice(negatives if rng.random() < NOT_POPUP_SHARE else popups))
            elif draw < real_share + TEMPLATE_SHARE:
                example = episode(rng)
            else:
                example = row(rng, rng.choice(train_llm))
            f.write(json.dumps(with_buttons(example), ensure_ascii=False) + "\n")
    with (out / "validation.jsonl").open("w") as f:
        for item, answer, kind in validation_real:
            f.write(json.dumps(with_buttons(real_row(rng, item, answer, "real_" + kind)), ensure_ascii=False) + "\n")
        for item in validation_llm:
            f.write(json.dumps(with_buttons(row(rng, item)), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
