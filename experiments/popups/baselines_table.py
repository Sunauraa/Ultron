"""Added LLM baselines against the locked pop-up model on the final test. Reads, never re-selects. Usage: baselines_table.py

The baselines were added after the final result was known, with prompts unchanged, and every model that passed
its sanity check is listed. Agent runs give the first click; one-call runs may decline.
"""

import json
import sys
from pathlib import Path
from statistics import median

import torch

torch.set_num_threads(4)

from score_dialogs import ROOT, outcome  # noqa: E402
from stats_final import mcnemar  # noqa: E402
from synth_dialogs import ESCALATE, LEAVE, dialog_context  # noqa: E402

from cua_s1.model import ChoiceExample, load_checkpoint  # noqa: E402

MODELS = {"q7": "Qwen2.5-7B", "q3_14": "Qwen3-14B", "gptoss20": "gpt-oss-20b", "phi4": "Phi-4", "q32awq": "Qwen2.5-32B AWQ"}
CHECKPOINTS = [ROOT / f"models/ultron-dialogs-0.1/{m}/model.safetensors" for m in "ab"]
GATE = 0.6


def line(name, values, seconds=None, base=None):
    count = lambda *kinds: sum(v in kinds for v in values)
    note = f"{median(seconds):8.2f} s" if seconds else ""
    print(f"{name:32}{count('right'):6}{count('deferred'):9}{count('WRONG'):7}{count('TRAP'):6} {note}", end="")
    if base:
        for test in (lambda v: v == "right", lambda v: v in ("WRONG", "TRAP")):
            a, b = sum(test(x) and not test(y) for x, y in zip(base, values)), sum(test(y) and not test(x) for x, y in zip(base, values))
            print(f"  p={mcnemar(a, b):.2g}", end="")
    print()


def main():
    models = [load_checkpoint(path, "cpu")[:2] for path in CHECKPOINTS]
    items = [i for i in json.loads((ROOT / "data/popups/captures/final_test.json").read_text()) if i["split"] == "final"]
    locked = []
    for item in items:
        options = [f"click {b}" for b in item["buttons"]] + [LEAVE, ESCALATE]
        good = {a if a in (LEAVE, ESCALATE) else f"click {a}" for a in item["acceptable"]}
        traps = {f"click {b}" for b in item["traps"]}
        example = ChoiceExample(dialog_context(item["text"], options), tuple(options), 0)
        with torch.no_grad():
            conf, pred = torch.stack([m(c([example])).softmax(-1) for m, c in models]).mean(0).max(-1)
        locked.append("deferred" if conf.item() < GATE else outcome(options[pred.item()], good, traps))
    print(f"{'n=' + str(len(items)):32}{'right':>6}{'deferred':>9}{'wrong':>7}{'trap':>6}    median   p(right) p(wrong+trap) vs locked")
    line("Locked model, gate 0.6", locked)
    more = ROOT / "results/popups_llm/more"
    for mode in ("agent", "policy"):
        print(f"-- {mode}")
        for short, name in MODELS.items():
            rows = {r["text"]: r for r in map(json.loads, open(more / f"{short}_{mode}_final.jsonl"))}
            values, seconds = [], []
            for item in items:
                row = rows[item["text"]]
                good = {a if a in (LEAVE, ESCALATE) else f"click {a}" for a in item["acceptable"]}
                traps = {f"click {b}" for b in item["traps"]}
                if mode == "agent":
                    clicks = row["clicks"]
                    values.append(outcome(f"click {clicks[0]}", good, traps) if clicks else ("right" if LEAVE in good or ESCALATE in good else "deferred"))
                else:
                    values.append(outcome(row["choice"], good, traps) if row["choice"] else "deferred")
                seconds.append(row["seconds"] if mode == "agent" else row["ms"] / 1000)
            line(name, values, seconds, locked)


if __name__ == "__main__":
    main()
