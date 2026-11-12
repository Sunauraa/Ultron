"""Score on the hand-labelled large-capture sets (fresh is now tuning data). Usage: score_fresh.py CHECKPOINT GATE"""

import json
import math
import re
import statistics
import sys
import time
from collections import Counter

import torch

torch.set_num_threads(1)

from score_dialogs import ROOT, is_safe, outcome  # noqa: E402

from cua_s1.model import ChoiceExample, load_checkpoint  # noqa: E402
from synth_dialogs import ESCALATE, LEAVE, dialog_context  # noqa: E402


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return f"{k}/{n} = {100 * p:.1f}% [{100 * (c - m) / d:.1f}, {100 * (c + m) / d:.1f}]"


def show(name, cells):
    n = sum(cells.values())
    print(f"  {name:24} n={n} right={cells['right']} deferred={cells['deferred']} WRONG={cells['WRONG']} TRAP={cells['TRAP']} | right {wilson(cells['right'], n)}")


def main():
    model, collate, _ = load_checkpoint(sys.argv[1], "cpu")
    gate = float(sys.argv[2])
    items = [x for x in json.loads((ROOT / "data/popups/captures/testset.json").read_text()) if x["set"] == "fresh"]
    trained = {json.loads(l)["text"] for l in (ROOT / "data/popups/captures/big/all_labels.jsonl").open()}
    qwen = {json.loads(l)["text"]: json.loads(l) for l in (ROOT / "results/popups_llm/qwen_fresh.jsonl").open()}
    groups, times, misses = {}, [], []
    for item in items:
        options = [f"click {b}" for b in item["buttons"]] + [LEAVE, ESCALATE]
        good = {a if a in (LEAVE, ESCALATE) else f"click {a}" for a in item["acceptable"]}
        traps = {f"click {b}" for b in item["traps"]}
        start = time.perf_counter()
        batch = collate([ChoiceExample(dialog_context(item["text"], options), tuple(options), 0)])
        with torch.no_grad():
            conf, pred = model(batch).softmax(-1).max(-1)
        times.append((time.perf_counter() - start) * 1000)
        conf, choice = conf.item(), options[pred.item()]
        rows = {"model@gate": "deferred" if conf < gate else outcome(choice, good, traps), "model@0.5": "deferred" if conf < 0.5 else outcome(choice, good, traps)}
        rule = next((o for o in options if is_safe(o)), None)
        rows["rules"] = outcome(rule, good, traps) if rule else "deferred"
        if item["split"] == "fresh" and item["text"] in qwen:
            clicks = qwen[item["text"]]["clicks"]
            rows["qwen agent"] = outcome(f"click {clicks[0]}", good, traps) if clicks else ("right" if LEAVE in good or ESCALATE in good else "deferred")
        tags = [item["split"]]
        if item["split"] == "fresh":
            tags += [f"fresh/lang {item['lang']}", f"fresh/kind {item['kind']}"] + (["fresh/text not in training"] if item["text"] not in trained else [])
        for tag in tags:
            for name, value in rows.items():
                groups.setdefault(tag, {}).setdefault(name, Counter())[value] += 1
        if conf >= gate and rows["model@gate"] != "right":
            misses.append(f"  [{item['split']}] {item['text'][:58]!r} -> {choice[:28]!r} ({conf:.2f}) want {sorted(good)[:2]}")
    for tag in sorted(groups):
        print(tag)
        for name, cells in groups[tag].items():
            show(name, cells)
    print("latency ms median", round(statistics.median(times), 1), "p95", round(sorted(times)[int(len(times) * 0.95)], 1))
    print("\n".join(misses))


if __name__ == "__main__":
    main()
