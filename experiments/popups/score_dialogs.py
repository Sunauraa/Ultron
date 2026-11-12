"""Score a dialog checkpoint. Usage: score_dialogs.py CHECKPOINT dev|test|hard|susbench [--misses]

Below the gate the pop-up goes to the LLM, so it counts as deferred. `leave alone` is also a
deferral to the LLM unless it was the expected answer. Anything else unexpected reaches the page.
Three policies are compared: the model alone, the model limited to safe buttons, and safe-button
rules with no model at all. If the rules match the model, the model isn't adding anything.
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "third_party/cua/libs/cua-s1/python/src"))
sys.path.insert(0, str(ROOT / "experiments/popups"))

from cua_s1.model import ChoiceExample, load_checkpoint  # noqa: E402
from synth_dialogs import ESCALATE, LEAVE, dialog_context  # noqa: E402

GATES = (0.5, 0.9, 0.99)
# Whole-label matches only, so "No, delete it" or "Close my account" never qualify.
SAFE = re.compile(
    r"x|×|close|close dialog|dismiss|no|no thanks|no thank you|not now|later|maybe later|remind me later|skip|ignore|stay here|"
    r"reject|reject all|reject all cookies|decline|decline all|only essential|only necessary|necessary only|essential only|accept only essential( cookies)?|"
    r"đóng|từ chối|từ chối tất cả|để sau|không|không cảm ơn|bỏ qua|không đồng ý|chỉ cookie cần thiết|"
    r"schließen|ablehnen|alle ablehnen|nein danke|nur notwendige|sluit|sluiten|weigeren|alles weigeren|nee bedankt|"
    r"fermer|refuser|tout refuser|non merci|plus tard|chiudi|rifiuta|rifiuta tutti|no grazie|cerrar|rechazar|rechazar todo|no gracias"
)


def is_safe(option):
    label = re.sub(r"[.,!]", "", option.removeprefix("click ")).strip().lower()
    return option.startswith("click ") and SAFE.fullmatch(label) is not None


def outcome(choice, good, traps):
    if choice in good:
        return "right"
    if choice in traps:
        return "TRAP"
    return "deferred" if choice == LEAVE else "WRONG"


def main():
    checkpoint, split = sys.argv[1], sys.argv[2]
    items = [x for x in json.loads((ROOT / "data/popups/captures/testset.json").read_text()) if x["split"] == split]
    model, collate, _ = load_checkpoint(checkpoint, "cpu")
    stats = defaultdict(lambda: defaultdict(int))
    for item in items:
        options = [f"click {b}" for b in item["buttons"]] + [LEAVE, ESCALATE]
        good = {a if a in (LEAVE, ESCALATE) else f"click {a}" for a in item["acceptable"]}
        traps = {f"click {b}" for b in item["traps"]}
        batch = collate([ChoiceExample(dialog_context(item["text"], options), tuple(options), 0)])
        with torch.no_grad():
            conf, pred = model(batch).softmax(-1).max(-1)
        conf, choice = conf.item(), options[pred.item()]
        group = stats[f"{item['kind']}/{item['lang']}"]
        group["n"] += 1
        for gate in GATES:
            group[f"model {gate} " + ("deferred" if conf < gate else outcome(choice, good, traps))] += 1
            filtered = conf >= gate and (is_safe(choice) or choice in (ESCALATE,))
            group[f"filter {gate} " + (outcome(choice, good, traps) if filtered else "deferred")] += 1
        rule = next((o for o in options if is_safe(o)), None)
        group["rules - " + (outcome(rule, good, traps) if rule else "deferred")] += 1
        if "--misses" in sys.argv and choice not in good:
            print(f"  {item['text'][:60]!r} -> {choice[:30]!r} ({conf:.2f}, safe={is_safe(choice)}), want {sorted(good)[:2]}")
    total = defaultdict(int)
    for name in sorted(stats):
        for key, value in stats[name].items():
            total[key] += value
    for name, s in [*sorted(stats.items()), ("ALL", total)]:
        print(f"{name} n={s['n']}")
        rows = [(f"model {g}", f"model {g} ") for g in GATES] + [(f"filter {g}", f"filter {g} ") for g in GATES] + [("rules", "rules - ")]
        for label, key in rows:
            print(f"  {label:11} right={s[key + 'right']} deferred={s[key + 'deferred']} WRONG={s[key + 'WRONG']} TRAP={s[key + 'TRAP']}")


if __name__ == "__main__":
    main()
