"""Unique pop-up items from captures, without any text in the test sets. Usage: extract_items.py OUT.jsonl CAPTURED.jsonl ...

Text in the final test or the tuning sets is left out, so test scores are on wording never trained on.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def clean(text):
    return re.sub(r"\s+", " ", text)


def main():
    seen = {clean(x["text"]) for x in json.load(open(ROOT / "data/popups/captures/final_test.json"))}
    seen |= {clean(x["text"]) for x in json.load(open(ROOT / "data/popups/captures/testset.json")) if x.get("text")}
    print(len(seen), "test texts held out")
    count = 0
    with open(sys.argv[1], "w") as out:
        for path in sys.argv[2:]:
            for line in open(path):
                record = json.loads(line)
                for hit in record["popups"]:
                    text = clean(hit["text"])
                    buttons = list(dict.fromkeys(clean(b["text"] or b["aria"]).strip() or "(no label)" for b in hit["buttons"]))
                    if text not in seen and buttons:
                        seen.add(text)
                        count += 1
                        out.write(json.dumps({"url": record["url"], "lang": record.get("lang", ""), "signal": hit["signal"], "text": text, "buttons": buttons}, ensure_ascii=False) + "\n")
    print(count, "items")


if __name__ == "__main__":
    main()
