"""Train on real pop-ups with per-button labels, plus the LLM-written and template ones.
Usage: build_real2.py OUT_DIR ROWS NOT_POPUP_SHARE LLM.jsonl LABELS.jsonl ...

The action comes from the classes of the buttons on offer, so taking a button away gives another real
training case: drop the reject button and the close button becomes right, drop that and accept does.
"""

import hashlib
import json
import random
import re
import sys
from pathlib import Path

from build_dialogs import ANSWER, row
from button_policy import ESCALATE, LEAVE, action, agreed
from synth_dialogs import TASK, dialog_context, episode

REAL_SHARE, TEMPLATE_SHARE = 0.6, 0.1
OTHER_KINDS_SHARE = 0.3  # cookie banners would otherwise be nearly every real row
REMOVE_SHARE = 0.35
# Cleans training labels only; the model has no rules. The labeller still calls some banners not pop-ups.
BANNER_WORDS = re.compile(r"cookie|cooki|kakor|eväste|ciastecz|süti|consent|privacy|datenschutz|confidentialit|quyền riêng tư", re.I)


def with_buttons(example):
    example["context"] = dialog_context(example["context"].removeprefix(TASK), example["options"])
    return example


def as_row(rng, item, kind, classes, text, buttons, answers):
    if rng.random() < 0.3:
        text = text[text.find(" ", rng.randint(0, len(text) // 4)) + 1:] or text
    keep = rng.choice(answers)
    buttons = [b for b in buttons if b == keep or rng.random() > 0.1]
    rng.shuffle(buttons)
    options = [f"click {b}" for b in buttons] + [LEAVE, ESCALATE]
    target = keep if keep in (LEAVE, ESCALATE) else f"click {keep}"
    return {"context": TASK + text, "options": options, "label": options.index(target), "meta": {"action": kind}}


def popup_row(rng, entry, tag=""):
    """The pop-up as captured, or with the buttons of the best class removed from both list and text."""
    item, kind, classes, answers = entry
    text, buttons = item["text"], item["buttons"]
    while tag == "" and rng.random() < REMOVE_SHARE and answers[0] in classes and len(buttons) > 1:
        gone = {b for b in answers if b in classes}
        buttons = [b for b in buttons if b not in gone]
        classes = {b: c for b, c in classes.items() if b not in gone}
        for b in gone:
            text = text.replace(b, " ")
        answers = action(kind, classes)
    return as_row(rng, item, tag + kind, classes, text, buttons, answers)


def main():
    out, rows, share, source = Path(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), Path(sys.argv[4])
    rng = random.Random(7)
    cookie, other, negative, held = [], [], [], []
    for path in sys.argv[5:]:
        for line in open(path):
            item = json.loads(line)
            label = agreed(item)
            if label is None:
                continue
            is_popup, kind, classes, answers = label
            if not is_popup and (BANNER_WORDS.search(item["text"]) or {"reject", "accept"} & set(item["votes"][0].get("classes", {}).values())):
                continue
            entry = (item, kind, classes, answers)
            if hashlib.sha256(item["url"].encode()).digest()[1] < 26:
                held.append(entry)
            else:
                (negative if not is_popup else cookie if kind == "cookie" else other).append(entry)
    print(len(cookie), "cookie,", len(other), "other,", len(negative), "not pop-ups,", len(held), "held out")
    llm = {}
    for line in source.open():
        item = json.loads(line)
        needs_safe = item["kind"] not in ANSWER
        if len(item["text"]) >= 10 and item["other"] and item["other"] != item["safe"] and (item["safe"] or not needs_safe):
            llm.setdefault(item["text"], item)
    train_llm = [x for t, x in llm.items() if hashlib.sha256(t.encode()).digest()[0] >= 26]
    validation_llm = [x for t, x in llm.items() if hashlib.sha256(t.encode()).digest()[0] < 26]
    out.mkdir(parents=True, exist_ok=True)
    with (out / "train.jsonl").open("w") as f:
        for _ in range(rows):
            draw = rng.random()
            if draw < REAL_SHARE:
                if rng.random() < share:
                    example = popup_row(rng, rng.choice(negative))
                else:
                    example = popup_row(rng, rng.choice(other if rng.random() < OTHER_KINDS_SHARE else cookie))
            elif draw < REAL_SHARE + TEMPLATE_SHARE:
                example = episode(rng)
            else:
                example = row(rng, rng.choice(train_llm))
            f.write(json.dumps(with_buttons(example), ensure_ascii=False) + "\n")
    with (out / "validation.jsonl").open("w") as f:
        for entry in held:
            f.write(json.dumps(with_buttons(popup_row(rng, entry, "real_")), ensure_ascii=False) + "\n")
        for item in validation_llm:
            f.write(json.dumps(with_buttons(row(rng, item)), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
