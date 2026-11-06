"""Score the chosen model on the locked final test. Usage: score_final.py CHECKPOINT,CHECKPOINT GATE LLM_DIRECT.jsonl LLM_AGENT.jsonl

Run once, after the model and gate are chosen on tuning data. It refuses to run a second time, so a
result can't be replaced by a better one. Prints other gates too, but the chosen gate is the headline.
"""

import json
import statistics
import sys
import time
from collections import Counter

import torch

torch.set_num_threads(1)

from score_dialogs import ROOT, is_safe, outcome  # noqa: E402
from score_fresh import show  # noqa: E402

from cua_s1.model import ChoiceExample, load_checkpoint  # noqa: E402
from synth_dialogs import ESCALATE, LEAVE, dialog_context  # noqa: E402

RESULT = ROOT / "results/final_result.txt"


def main():
    if RESULT.exists():
        sys.exit(f"{RESULT} exists: the final test has been used")
    models = [load_checkpoint(path, "cpu")[:2] for path in sys.argv[1].split(",")]
    gate = float(sys.argv[2])
    direct = {json.loads(l)["text"]: json.loads(l) for l in open(sys.argv[3])}
    qwen = {json.loads(l)["text"]: json.loads(l) for l in open(sys.argv[4])}
    items = json.loads((ROOT / "data/popups/captures/final_test.json").read_text())
    groups, times, misses = {}, [], []
    for item in items:
        options = [f"click {b}" for b in item["buttons"]] + [LEAVE, ESCALATE]
        good = {a if a in (LEAVE, ESCALATE) else f"click {a}" for a in item["acceptable"]}
        traps = {f"click {b}" for b in item["traps"]}
        start = time.perf_counter()
        example = ChoiceExample(dialog_context(item["text"], options), tuple(options), 0)
        with torch.no_grad():
            conf, pred = torch.stack([m(c([example])).softmax(-1) for m, c in models]).mean(0).max(-1)
        times.append((time.perf_counter() - start) * 1000)
        conf, choice = conf.item(), options[pred.item()]
        rows = {"model@gate": "deferred" if conf < gate else outcome(choice, good, traps), **{f"model@{g}": "deferred" if conf < g else outcome(choice, good, traps) for g in (0.5, 0.7, 0.8, 0.9)}}
        rule = next((o for o in options if is_safe(o)), None)
        rows["rules"] = outcome(rule, good, traps) if rule else "deferred"
        choice_llm = direct[item["text"]]["choice"]
        rows["llm with policy"] = outcome(choice_llm, good, traps) if choice_llm else "deferred"
        if item["split"] == "final" and item["text"] in qwen:
            clicks = qwen[item["text"]]["clicks"]
            rows["qwen agent"] = outcome(f"click {clicks[0]}", good, traps) if clicks else ("right" if LEAVE in good or ESCALATE in good else "deferred")
        tags = [item["split"]]
        if item["split"] == "final":
            tags += [f"final/kind {item['kind']}"] + (["final/with traps"] if item["traps"] else [])
        for tag in tags:
            for name, value in rows.items():
                groups.setdefault(tag, {}).setdefault(name, Counter())[value] += 1
        if conf >= gate and rows["model@gate"] != "right":
            misses.append(f"  [{item['split']}] {item['text'][:58]!r} -> {choice[:28]!r} ({conf:.2f}) want {sorted(good)[:2]}")
    import contextlib
    import io
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        print("checkpoint", sys.argv[1], "gate", gate)
        for tag in sorted(groups):
            print(tag)
            for name, cells in groups[tag].items():
                show(name, cells)
        print("latency ms median", round(statistics.median(times), 1), "p95", round(sorted(times)[int(len(times) * 0.95)], 1))
        print("\n".join(misses))
    RESULT.write_text(buffer.getvalue())
    print(buffer.getvalue())


if __name__ == "__main__":
    main()
