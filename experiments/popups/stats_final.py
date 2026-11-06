"""Paired significance on the final test, for the locked model at its locked gate. Reads, never re-selects.
Usage: stats_final.py CHECKPOINT,CHECKPOINT GATE LLM_DIRECT.jsonl LLM_AGENT.jsonl
"""

import json
import sys
from math import comb

import torch

torch.set_num_threads(4)

from score_dialogs import ROOT, outcome  # noqa: E402

from cua_s1.model import ChoiceExample, load_checkpoint  # noqa: E402
from synth_dialogs import ESCALATE, LEAVE, dialog_context  # noqa: E402


def mcnemar(a, b):
    """Exact two-sided test on the items where only one of the two systems failed."""
    low, n = min(a, b), a + b
    return min(1.0, 2 * sum(comb(n, k) for k in range(low + 1)) / 2 ** n) if n else 1.0


def main():
    models = [load_checkpoint(path, "cpu")[:2] for path in sys.argv[1].split(",")]
    gate = float(sys.argv[2])
    direct = {json.loads(l)["text"]: json.loads(l) for l in open(sys.argv[3])}
    agent = {json.loads(l)["text"]: json.loads(l) for l in open(sys.argv[4])}
    rows = []
    for item in json.loads((ROOT / "data/popups/captures/final_test.json").read_text()):
        if item["split"] != "final":
            continue
        options = [f"click {b}" for b in item["buttons"]] + [LEAVE, ESCALATE]
        good = {a if a in (LEAVE, ESCALATE) else f"click {a}" for a in item["acceptable"]}
        traps = {f"click {b}" for b in item["traps"]}
        example = ChoiceExample(dialog_context(item["text"], options), tuple(options), 0)
        with torch.no_grad():
            conf, pred = torch.stack([m(c([example])).softmax(-1) for m, c in models]).mean(0).max(-1)
        clicks = agent[item["text"]]["clicks"]
        rows.append({
            "model": "deferred" if conf.item() < gate else outcome(options[pred.item()], good, traps),
            "agent": outcome(f"click {clicks[0]}", good, traps) if clicks else ("right" if LEAVE in good or ESCALATE in good else "deferred"),
            "direct": outcome(direct[item["text"]]["choice"], good, traps) if direct[item["text"]]["choice"] else "deferred",
        })
    for other in ("agent", "direct"):
        for name, test in (("right", lambda v: v == "right"), ("wrong or trap", lambda v: v in ("WRONG", "TRAP")), ("trap", lambda v: v == "TRAP")):
            only_model = sum(test(r["model"]) and not test(r[other]) for r in rows)
            only_other = sum(test(r[other]) and not test(r["model"]) for r in rows)
            print(f"model vs {other:7} {name:14} only model {only_model:3} only {other} {only_other:3} p={mcnemar(only_model, only_other):.2g}")


if __name__ == "__main__":
    main()
