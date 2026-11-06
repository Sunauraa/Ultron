"""Results tables for the agent benchmark. Usage: bench_table.py PREFIX [SEED ...]

Reads results/bench/PREFIX_{14b,32b}_ARM_sN. One wide table of every column, then each gap that matters.
Intervals are 95% bootstrap intervals over forms, with each form's arms averaged over seeds and paired.
"""

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def named(score, final):
    """The final message names each missing field: at least half the words of its label appear."""
    def found(label):
        words = [w for w in re.findall(r"\w{3,}", label.casefold())]
        return not words or sum(w in final.casefold() for w in words) * 2 >= len(words)
    return all(found(label) for label in score["blocked"] + score.get("unclear", []))


def correct(r):
    """Sent with every field right, or, when the document lacks a required value, stopped unsent and named it."""
    s = r["score"]
    if s["blocked"]:
        return not s["submitted"] and named(s, r.get("final") or "")
    if s.get("unclear") and not s["submitted"]:
        return named(s, r.get("final") or "")
    return s["submitted"] and not (s["wrong"] or s["extra"] or s["missing_consent"])


METRICS = {
    "Handled correctly": correct,
    "LLM calls": lambda r: len(r["calls"]),
    "Seconds": lambda r: r["seconds"],
    "Prompt tokens": lambda r: sum(c["prompt_tokens"] or 0 for c in r["calls"]),
    "Completion tokens": lambda r: sum(c["completion_tokens"] or 0 for c in r["calls"]),
    "Submitted": lambda r: r["score"]["submitted"],
    "Sent despite a gap": lambda r: bool(r["score"]["blocked"]) and r["score"]["submitted"],
    "Fields wrong or empty": lambda r: 0 if r["score"]["blocked"] or correct(r) else len(r["score"]["wrong"]),
    "Wrong, on sent forms": lambda r: len(r["score"]["wrong"]) if r["score"]["submitted"] else 0,
    "Claimed success, unsent": lambda r: bool(r.get("success")) and not r["score"]["submitted"],
    "Choice controls answered": lambda r: r["score"].get("choices_answered", 0),
    "Extra fields filled": lambda r: len(r["score"]["extra"]),
    "Pop-up bad choices": lambda r: r["score"]["popup_ok"] is False,
    "Pop-up traps": lambda r: r["score"]["popup_trap"],
}


COLUMNS = {
    "14B default": "14b_plain", "14B tuned": "14b_hintsflash", "14B Ultron": "14b_s1", "14B Ultron, conformal gate": "14b_crc", "14B no forms model": "14b_nomodel",
    "32B default": "32b_plain", "32B tuned": "32b_hintsflash", "32B Ultron": "32b_s1",
}
GAPS = [
    ("14B Ultron", "14B default"), ("14B Ultron", "14B tuned"), ("32B Ultron", "32B default"), ("32B Ultron", "32B tuned"),
    ("14B Ultron", "14B no forms model"), ("14B Ultron, conformal gate", "14B Ultron"), ("32B default", "14B default"), ("32B Ultron", "14B Ultron"),
]


def load(prefix, arm, seeds):
    runs = []
    for seed in seeds:
        rows = [json.loads(p.read_text()) for p in (ROOT / f"results/bench/{prefix}_{arm}_s{seed}").glob("*.json")]
        runs.append({r["form"]: r for r in rows})
    return runs


def mean(runs, metric, form):
    return sum(metric(run[form]) for run in runs) / len(runs)


def wide(columns, forms, label):
    print(f"\n{label}: {len(forms)} forms, {len(next(iter(columns.values())))} seeds. Totals per seed on average.")
    print(f"{'':26}" + "".join(f"{name[:26]:>28}" for name in columns))
    for name, metric in METRICS.items():
        print(f"{name:26}" + "".join(f"{sum(mean(runs, metric, f) for f in forms):28.1f}" for runs in columns.values()))


def gaps(columns, forms, label):
    print(f"\n{label}: {len(forms)} forms. First arm minus second, with the 95% interval on the gap.")
    rng = random.Random(0)
    for first, second in GAPS:
        print(f"  {first} vs {second}")
        for name, metric in METRICS.items():
            one = [mean(columns[first], metric, f) - mean(columns[second], metric, f) for f in forms]
            totals = sorted(sum(rng.choices(one, k=len(one))) for _ in range(10000))
            base = sum(mean(columns[second], metric, f) for f in forms)
            change = f"{sum(one) / base:+.0%}" if base else ""
            print(f"    {name:26}{sum(one):+11.1f}{change:>7}   [{totals[250]:+.1f}, {totals[9750]:+.1f}]")


def main():
    prefix, seeds = sys.argv[1], [int(s) for s in sys.argv[2:]] or [1, 2, 3]
    columns = {name: load(prefix, arm, seeds) for name, arm in COLUMNS.items()}
    first = next(iter(columns.values()))[0]
    forms = sorted(first)
    assert all(set(run) == set(forms) for runs in columns.values() for run in runs), "missing runs"
    clear = [f for f in forms if not first[f]["score"]["blocked"] and not first[f]["score"].get("unclear")]
    for label, chosen in [("All", forms), ("Completable, with a clear answer for every required field", clear)] + [(lang, [f for f in forms if first[f]["lang"] == lang]) for lang in ("en", "vi")]:
        wide(columns, chosen, label)
    gaps(columns, forms, "All")
    gaps(columns, clear, "Completable, with a clear answer for every required field")
    print("\nBy seed (calls, handled correctly, submitted, fields wrong or empty):")
    for name, runs in columns.items():
        row = lambda run: [sum(METRICS[m](run[f]) for f in forms) for m in ("LLM calls", "Handled correctly", "Submitted", "Fields wrong or empty")]
        print(f"  {name:20}" + "  ".join(f"s{seed} {row(run)}" for seed, run in zip(seeds, runs)))
    for name in ("14B Ultron", "32B Ultron"):
        steps = [x for run in columns[name] for f in forms for x in run[f]["fast"]]
        for kind in ("dialog", "form"):
            ms = sorted(x["milliseconds"] for x in steps if x["kind"] == kind)
            print(f"{name} {kind} fast steps: {len(ms)}, median {ms[len(ms) // 2]:.0f} ms")
    print(f"Scored fields per seed: {sum(first[f]['score']['fields'] for f in forms)}")


if __name__ == "__main__":
    main()
