"""Check a served model answers usefully on already used pop-ups, before it touches the final test."""

import json
import random
from pathlib import Path

from label_popups_llm import ask

ROOT = Path(__file__).resolve().parents[2]
items = [x for x in json.loads((ROOT / "data/popups/captures/testset.json").read_text()) if x["set"] == "fresh"]
random.Random(0).shuffle(items)
valid = 0
for item in items[:15]:
    try:
        answer = ask(item["text"], item["buttons"], 1)
    except Exception as e:
        answer = {"error": type(e).__name__, "action": None}
    valid += bool(answer.get("action")) or answer.get("is_popup") is False
    print(item["buttons"][:3], "->", str(answer)[:110])
print("usable answers", valid, "of 15")
