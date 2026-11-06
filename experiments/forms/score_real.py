"""Score a checkpoint on the real-form set. Usage: score_real.py CHECKPOINT[,CHECKPOINT...] dev|test [--misses]

Several checkpoints are scored as an ensemble with averaged probabilities, as the plugin does it.

A `skip` where a fill or click was expected is a deferral to the LLM. Anything else wrong is a
wrong action that would reach the page. `saved` is how many of the batched LLM calls (5 actions
per step, as Browser Use allows) the model removes per form at each gate.
"""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "third_party/cua/libs/cua-s1/python/src"))

from cua_s1.model import ChoiceExample, load_checkpoint  # noqa: E402
from cua_s1.schema import Element, Entity, render_context, render_options  # noqa: E402

GATES = (0.5, 0.6, 0.7, 0.8, 0.9, 0.99)
BATCH = 5


def main():
    checkpoint, split = sys.argv[1], sys.argv[2]
    show = "--misses" in sys.argv
    data = json.loads((ROOT / "data/forms/real/testset.json").read_text())
    models = [load_checkpoint(path, "cpu")[:2] for path in checkpoint.split(",")]
    stats = defaultdict(lambda: defaultdict(int))
    for form in data["forms"]:
        if form["split"] != split:
            continue
        lang = form["lang"]
        document = data["documents"][lang]
        keys = list(document)
        entities = [Entity(*document[k]) for k in keys]
        n = len(entities)
        check, click, skip = n, n + 1, n + 2
        options = tuple(render_options(entities))
        examples, gold, labels = [], [], []
        for row in form["rows"]:
            if row["role"] == "Edit":
                g = keys.index(row["concept"]) if row.get("concept") else skip
                element = Element("Edit", row["label"])
            elif row["role"] == "CheckBox":
                g, element = check, Element("CheckBox", row["label"], checked=False)
            else:
                g, element = click, Element("Button", row["label"])
            examples.append(ChoiceExample(render_context("Form", element), options, g))
            gold.append(g)
            labels.append(row["label"])
        with torch.no_grad():
            conf, pred = torch.stack([m(c(examples)).softmax(-1) for m, c in models]).mean(0).max(-1)
        s = stats[lang]
        s["forms"] += 1
        s["n"] += len(gold)
        needed = sum(1 for g in gold if g != skip)
        s["calls"] += math.ceil(needed / BATCH) + 2  # the page's actions, plus navigate and done
        for gate in GATES:
            handled = 0
            for g, p, c in zip(gold, pred.tolist(), conf.tolist()):
                if c < gate:
                    s[f"{gate}_low"] += 1
                elif p == g:
                    s[f"{gate}_{'skip' if p == skip else 'act'}"] += 1
                    handled += p != skip
                elif p == skip:
                    s[f"{gate}_deferred"] += 1
                else:
                    s[f"{gate}_wrong"] += 1
            s[f"{gate}_saved"] += math.ceil(needed / BATCH) - math.ceil((needed - handled) / BATCH)
        if show:
            for g, p, c, label in zip(gold, pred.tolist(), conf.tolist(), labels):
                if p != g:
                    print(f"  {lang} {label[:40]!r}: want {options[g][:40]!r}, got {options[p][:40]!r} ({c:.2f})")
    for lang, s in stats.items():
        print(f"{lang} {split}: {s['forms']} forms, {s['n']} decisions, {s['calls']} batched calls")
        for gate in GATES:
            print(
                f"  gate {gate}: right actions={s[f'{gate}_act']} right skips={s[f'{gate}_skip']} "
                f"deferred={s[f'{gate}_deferred']} low confidence={s[f'{gate}_low']} "
                f"WRONG={s[f'{gate}_wrong']} calls saved={s[f'{gate}_saved']} ({s[f'{gate}_saved'] / s['calls']:.0%})"
            )


if __name__ == "__main__":
    main()
