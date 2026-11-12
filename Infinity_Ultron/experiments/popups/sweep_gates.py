"""Right/deferred/wrong at many gates, for one model or the average of several, on tuning sets only.
Usage: sweep_gates.py CHECKPOINT [CHECKPOINT ...]
"""

import json
import sys
from collections import Counter

import torch

torch.set_num_threads(4)

from score_dialogs import ROOT, outcome  # noqa: E402

from cua_s1.model import ChoiceExample, load_checkpoint  # noqa: E402
from synth_dialogs import ESCALATE, LEAVE, dialog_context  # noqa: E402

GATES = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
GROUPS = {"fresh": lambda x: x["split"] == "fresh", "fresh_np": lambda x: x["split"] == "fresh_np", "older real": lambda x: x["split"] in ("dev", "test"), "hard": lambda x: x["set"] == "hard", "susbench": lambda x: x["set"] == "susbench"}


def main():
    models = [load_checkpoint(path, "cpu")[:2] for path in sys.argv[1:]]
    items = json.loads((ROOT / "data/popups/captures/testset.json").read_text())
    for name, chosen in GROUPS.items():
        cells = {g: Counter() for g in GATES}
        for item in filter(chosen, items):
            options = [f"click {b}" for b in item["buttons"]] + [LEAVE, ESCALATE]
            good = {a if a in (LEAVE, ESCALATE) else f"click {a}" for a in item["acceptable"]}
            traps = {f"click {b}" for b in item["traps"]}
            example = ChoiceExample(dialog_context(item["text"], options), tuple(options), 0)
            with torch.no_grad():
                conf, pred = torch.stack([m(c([example])).softmax(-1) for m, c in models]).mean(0).max(-1)
            result = outcome(options[pred.item()], good, traps)
            for g in GATES:
                cells[g]["deferred" if conf.item() < g else result] += 1
        print(name, sum(cells[0.5].values()))
        for g in GATES:
            c = cells[g]
            print(f"  gate {g:<5} right={c['right']:<4} deferred={c['deferred']:<4} WRONG={c['WRONG']:<3} TRAP={c['TRAP']}")


if __name__ == "__main__":
    main()
