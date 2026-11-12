"""Summarise a bench.py run: per arm, correct rate and cost, with paired 95% bootstrap CIs over forms.

Usage: python bench/analyze.py bench/results/run
"""

import json
import random
import sys
from collections import defaultdict
from pathlib import Path


def bootstrap(per_form: dict[str, float], resamples: int = 10_000) -> tuple[float, float]:
    """95% CI of the mean of per-form values, resampling forms."""
    values, rng = list(per_form.values()), random.Random(0)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(resamples))
    return means[int(0.025 * resamples)], means[int(0.975 * resamples)]


def main(folder: Path) -> None:
    runs = [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))]
    by = defaultdict(lambda: defaultdict(list))  # metric -> arm -> [(form, value)]
    for r in runs:
        calls = r["calls"]
        metrics = {
            "correct": float(r["correct"]),
            "correct_unblocked": float(r["correct"]) if not r["blocked"] else None,
            "correct_blocked": float(r["correct"]) if r["blocked"] else None,
            "llm_calls": len(calls),
            "prompt_tokens": sum(c["prompt_tokens"] for c in calls),
            "completion_tokens": sum(c["completion_tokens"] for c in calls),
            "seconds": r["seconds"],
            "sent": float(r["score"]["submitted"]),
            "wrong_fields": len(r["score"]["wrong"]) if r["score"]["submitted"] else None,
            "filled_no_fact_field": len(r["score"]["extra"]) if r["score"]["submitted"] else None,
            "context_overflow": float("max_tokens" in r["stop"] or "context" in r["stop"]),
            "hit_call_cap": float(r["stop"] == "max_calls"),
            "harness_error": float(r["stop"].startswith("harness_error")),
        }
        if r["arm"] == "ultron":
            metrics["held_by_default"] = float(r.get("held_by_default", False))
        for name, value in metrics.items():
            if value is not None:
                by[name][r["arm"]].append((r["form"], value))

    arms = sorted({r["arm"] for r in runs})
    print(f"{len(runs)} episodes: " + ", ".join(f"{a} {sum(1 for r in runs if r['arm'] == a)}" for a in arms))
    print(f"{'metric':22}" + "".join(f"{a:>32}" for a in arms) + f"{'ultron - playwright (95% CI)':>34}")
    for name, per_arm in by.items():
        row, form_means = f"{name:22}", {}
        for arm in arms:
            pairs = per_arm.get(arm, [])
            if not pairs:
                row += f"{'-':>32}"
                continue
            grouped = defaultdict(list)
            for form, value in pairs:
                grouped[form].append(value)
            form_means[arm] = {f: sum(v) / len(v) for f, v in grouped.items()}
            mean = sum(v for _, v in pairs) / len(pairs)
            low, high = bootstrap(form_means[arm])
            row += f"{mean:>14.3f} [{low:>7.3f}, {high:>7.3f}] n={len(pairs):<3}"
        shared = form_means["ultron"].keys() & form_means["playwright"].keys() if len(form_means) == 2 else set()
        if shared:
            diff = {f: form_means["ultron"][f] - form_means["playwright"][f] for f in shared}
            low, high = bootstrap(diff)
            row += f"{sum(diff.values()) / len(diff):>14.3f} [{low:>7.3f}, {high:>7.3f}]"
        print(row)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
