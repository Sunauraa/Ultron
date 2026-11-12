"""Mix LLM-written pop-ups with template ones. Usage: build_dialogs.py LLM.jsonl OUT_DIR ROWS

Validation pop-ups are held out by text, so its score covers wording the model didn't train on.
Link-like distractor buttons are added, because the first model kept clicking policy links.
"""

import hashlib
import json
import random
import sys
from pathlib import Path

from synth_dialogs import ESCALATE, LEAVE, TASK, episode

LINKS = ["Privacy Policy", "Cookie Policy", "Terms of Use", "Terms and Conditions", "Learn more", "Click here", "here", "partners", "Imprint", "Help",
         "Chính sách bảo mật", "Điều khoản", "Tìm hiểu thêm", "Datenschutz", "Impressum", "Mentions légales", "Informativa", "Más información"]
ANSWER = {"wall": LEAVE, "danger": ESCALATE, "trap_closed": ESCALATE}
TEMPLATE_SHARE = 0.25


def row(rng, item):
    answer = ANSWER.get(item["kind"]) or f"click {item['safe']}"
    buttons = [b for b in (item["other"], item["safe"]) if b]
    if rng.random() < 0.5:
        buttons += rng.sample(LINKS, rng.randint(1, 4))
    buttons = list(dict.fromkeys(buttons))
    rng.shuffle(buttons)
    options = [f"click {b}" for b in buttons] + [LEAVE, ESCALATE]
    return {"context": TASK + item["text"], "options": options, "label": options.index(answer), "meta": {"action": item["kind"]}}


def main():
    source, out, rows = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
    rng = random.Random(7)
    items = {}
    for line in source.open():
        item = json.loads(line)
        needs_safe = item["kind"] not in ANSWER
        if len(item["text"]) >= 10 and item["other"] and item["other"] != item["safe"] and (item["safe"] or not needs_safe):
            items.setdefault(item["text"], item)
    train, validation = [], []
    for text, item in items.items():
        (validation if hashlib.sha256(text.encode()).digest()[0] < 26 else train).append(item)
    print(len(items), "unique pop-ups,", len(train), "train,", len(validation), "held out")
    out.mkdir(parents=True, exist_ok=True)
    with (out / "train.jsonl").open("w") as f:
        for _ in range(rows):
            example = episode(rng) if rng.random() < TEMPLATE_SHARE else row(rng, rng.choice(train))
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
    with (out / "validation.jsonl").open("w") as f:
        for item in validation:
            for _ in range(3):
                f.write(json.dumps(row(rng, item), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
