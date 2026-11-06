"""Score cua-s1-forms on the ten local forms, per decision, at several confidence gates.

Text inputs, checkboxes and the submit button only, which is what the model was trained on.
Dropdowns and radio buttons are left out. Expected action for a text field with no document
value is skip. A skip on a field that should be filled is counted as a harmless deferral to
the LLM; any other mistake is a wrong action that would reach the page.
"""

import sys
from collections import defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "third_party/cua/libs/cua-s1/python/src"))
sys.path.insert(0, str(ROOT / "experiments/bench"))

from cua_s1.model import ChoiceExample, load_checkpoint  # noqa: E402
from cua_s1.schema import Element, Entity, render_context, render_options  # noqa: E402
from forms import FORMS, SUBMIT  # noqa: E402

GATES = (0.5, 0.9, 0.99)


def decisions(f):
    """Yield (element, expected option index) for each scorable element, plus the options."""
    entities = [
        Entity(x["label"], x["value"])
        for page in f["pages"] for x in page
        if x["type"] in ("text", "select", "radio") and x["value"] is not None
    ]
    n = len(entities)
    check, click, skip = n, n + 1, n + 2
    rows = []
    for index, page in enumerate(f["pages"]):
        for x in page:
            if x["type"] == "text":
                gold = skip if x["value"] is None else next(
                    i for i, e in enumerate(entities) if e.label == x["label"] and e.value == x["value"]
                )
                rows.append((Element("Edit", x["label"]), gold))
            elif x["type"] == "checkbox":
                rows.append((Element("CheckBox", x["label"], checked=False), check))
        label = SUBMIT[f["lang"]][0 if index == len(f["pages"]) - 1 else 1]
        rows.append((Element("Button", label), click))
    return entities, rows


def main():
    model, collate, _ = load_checkpoint(ROOT / "third_party/models/cua-s1-forms/cua-s1-forms.safetensors", "cpu")
    stats = defaultdict(lambda: defaultdict(int))
    for f in FORMS:
        entities, rows = decisions(f)
        options = tuple(render_options(entities))
        skip = len(entities) + 2
        examples = [ChoiceExample(render_context(f["title"], e), options, g) for e, g in rows]
        with torch.no_grad():
            probs = model(collate(examples)).softmax(-1)
        conf, pred = probs.max(-1)
        right = 0
        for (element, g), p, c in zip(rows, pred.tolist(), conf.tolist()):
            ok = p == g
            right += ok
            s = stats[f["lang"]]
            s["n"] += 1
            s["right"] += ok
            for gate in GATES:
                if c < gate:
                    continue
                if ok and p != skip:
                    s[f"act_right_{gate}"] += 1
                elif ok:
                    s[f"skip_right_{gate}"] += 1
                elif p == skip:
                    s[f"deferred_{gate}"] += 1
                else:
                    s[f"act_wrong_{gate}"] += 1
            if not ok:
                print(f"  {f['id']:12} {element.label!r}: want {options[g]!r}, got {options[p]!r} ({c:.2f})")
        print(f"{f['id']:12} {f['lang']} {right}/{len(rows)} correct")
    print()
    for lang, s in stats.items():
        print(f"{lang}: {s['right']}/{s['n']} correct")
        for gate in GATES:
            print(
                f"  gate {gate}: right actions={s[f'act_right_{gate}']} right skips={s[f'skip_right_{gate}']} "
                f"deferred skips={s[f'deferred_{gate}']} WRONG ACTIONS={s[f'act_wrong_{gate}']}"
            )


if __name__ == "__main__":
    main()
