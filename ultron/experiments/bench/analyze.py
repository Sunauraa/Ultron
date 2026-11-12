"""Share of LLM calls a form model could replace, per form and overall.

strict: every action in the step is a text input, a checkbox click or a form button click,
which are the element types cua-s1-forms was trained on.
loose: also dropdowns and radio buttons.
batched: arithmetic estimate for an LLM that always batches up to MAX_ACTIONS per step.
These are upper bounds: they assume the form model gets every replaced decision right.
"""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from forms import BY_ID  # noqa: E402

MAX_ACTIONS = 5
RESULTS = Path(__file__).parent / "results"


def classify(step, form, seen_input):
    actions = step["actions"]
    if not actions:
        return "other"
    kinds = set()
    for a in actions:
        name, tag, kind = a["name"], a["tag"], a["input_type"]
        if name == "input":
            kinds.add("strict")
        elif name == "click" and tag == "button" and form["popup"] and not seen_input:
            kinds.add("dialog")
        elif name == "click" and (tag == "button" or kind == "checkbox"):
            kinds.add("strict")
        elif name == "click" and kind == "radio":
            kinds.add("loose")
        elif name in ("select_dropdown", "dropdown_options"):
            kinds.add("loose")
        else:
            kinds.add("other")
    for bad in ("other", "dialog", "loose"):
        if bad in kinds:
            return bad
    return "strict"


def batched_estimate(form):
    """(total calls, replaceable calls) if the LLM always batches to the limit."""
    replaceable = 0
    for page in form["pages"]:
        actions = 1 + sum(1 for x in page if x["value"] is not None)  # fields plus the submit click
        replaceable += math.ceil(actions / MAX_ACTIONS)
    extra = 2 + (1 if form["popup"] else 0)  # navigate, done, optional popup
    return replaceable + extra, replaceable


def main():
    runs = sys.argv[1:]
    totals = defaultdict(lambda: defaultdict(int))
    per_form = defaultdict(list)
    for run in runs:
        for path in sorted((RESULTS / run).glob("*.json")):
            r = json.loads(path.read_text())
            form = BY_ID[r["form"]]
            counts = defaultdict(int)
            seen_input = False
            for step in r["steps"]:
                counts[classify(step, form, seen_input)] += 1
                seen_input = seen_input or any(a["name"] == "input" for a in step["actions"])
            calls = len(r["calls"])
            ok = r["score"]["submitted"] and not r["score"]["wrong"] and not r["score"]["extra"]
            per_form[r["form"]].append((calls, counts["strict"], counts["loose"], counts["dialog"], ok, r["seconds"]))
            for group in ("all", r["lang"]):
                t = totals[group]
                t["calls"] += calls
                t["strict"] += counts["strict"]
                t["loose"] += counts["loose"]
                t["dialog"] += counts["dialog"]
                t["runs"] += 1
                t["ok"] += ok
                t["seconds"] += r["seconds"]
                t["prompt"] += sum(c["prompt_tokens"] or 0 for c in r["calls"])

    print(f"{'form':12} {'calls':>12} {'strict':>12} {'loose':>12} {'ok':>4} {'batched total/replaceable':>27}")
    for name, rows in per_form.items():
        fmt = lambda i: "/".join(str(row[i]) for row in rows)
        bt, br = batched_estimate(BY_ID[name])
        print(f"{name:12} {fmt(0):>12} {fmt(1):>12} {fmt(2):>12} {sum(r[4] for r in rows):>2}/{len(rows)} {bt:>13}/{br}")
    print()
    for group, t in totals.items():
        c = t["calls"]
        print(
            f"{group}: runs={t['runs']} correct={t['ok']} calls={c} "
            f"strict={t['strict']} ({t['strict'] / c:.0%}) "
            f"strict+loose={t['strict'] + t['loose']} ({(t['strict'] + t['loose']) / c:.0%}) "
            f"dialog={t['dialog']} seconds/run={t['seconds'] / t['runs']:.0f} prompt_tokens/call={t['prompt'] / c:.0f}"
        )
    bt = sum(batched_estimate(f)[0] for f in BY_ID.values())
    br = sum(batched_estimate(f)[1] for f in BY_ID.values())
    print(f"\nbatched estimate over all forms: {br}/{bt} calls replaceable ({br / bt:.0%})")


if __name__ == "__main__":
    main()
