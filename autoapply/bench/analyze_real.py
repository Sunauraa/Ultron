"""Summarise a real-page run (realbench.py) as locked in results/LOCK_realpages.json: per arm, the correct rate, sent
rate on the send pages, held rate on the hold pages, LLM calls and prompt tokens per page; the Ultron - Playwright
difference paired by (page, seed), with a 95% CI by bootstrap over pages (10,000 resamples).

Usage: python bench/analyze_real.py OUT_DIR [OUT_DIR ...]
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ARMS = ("playwright", "ultron")


def load(out: Path) -> dict:
    runs = {}
    for f in out.glob("*_s*.json"):
        r = json.loads(f.read_text())
        runs[(r["arm"], r["page"], r["seed"])] = r
    return runs


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def boot(per_page: dict[str, list[float]], n: int = 10000) -> tuple[float, float]:
    pages, rng, stats = sorted(per_page), random.Random(0), []
    for _ in range(n):
        sample = [rng.choice(pages) for _ in pages]
        stats.append(mean([x for p in sample for x in per_page[p]]))
    stats.sort()
    return stats[int(0.025 * n)], stats[int(0.975 * n)]


def summary(out: Path) -> str:
    runs = load(out)
    pages = sorted({p for _, p, _ in runs})
    seeds = sorted({s for _, _, s in runs})
    lines = [f"## {out.name}: {len(pages)} pages x seeds {seeds}, {len(runs)} episodes", "",
             "| | Playwright MCP | Ultron |", "|---|---|---|"]
    rows = defaultdict(dict)
    for arm in ARMS:
        mine = [r for (a, _, _), r in runs.items() if a == arm]
        hold = [r for r in mine if r["score"]["must_hold"]]
        send = [r for r in mine if not r["score"]["must_hold"]]
        rows["Correct"][arm] = f"{sum(bool(r['correct']) for r in mine)}/{len(mine)} ({mean([bool(r['correct']) for r in mine]):.0%})"
        rows["Send pages: sent and right"][arm] = f"{sum(bool(r['correct']) and r['score']['submitted'] for r in send)}/{len(send)}"
        rows["Send pages: sent at all"][arm] = f"{sum(r['score']['submitted'] for r in send)}/{len(send)}"
        rows["Send pages: sent with a wrong / extra / missing field"][arm] = f"{sum(r['score']['submitted'] and not r['correct'] for r in send)}/{len(send)}"
        rows["Hold pages: held (correct)"][arm] = f"{sum(not r['score']['submitted'] for r in hold)}/{len(hold)}"
        rows["LLM calls per page (mean)"][arm] = f"{mean([len(r['calls']) for r in mine]):.1f}"
        rows["Prompt tokens per page (mean)"][arm] = f"{mean([sum(c['prompt_tokens'] for c in r['calls']) for r in mine]):,.0f}"
        rows["Seconds per page (mean)"][arm] = f"{mean([r['seconds'] for r in mine]):.0f}"
        stops = Counter(r["stop"].split(":")[0] for r in mine)
        rows["Ended: done / max calls / error"][arm] = f"{stops['done']} / {stops['max_calls']} / {sum(v for k, v in stops.items() if k not in ('done', 'max_calls'))}"
        rows["Ended on an unparsed multi-call reply"][arm] = str(sum("<tool_call>" in (r.get("final") or "") for r in mine))
        if arm == "ultron":
            rows["Sent with written answers"][arm] = str(sum(r.get("held_by_default", False) for r in mine))
    for name, cells in rows.items():
        lines.append(f"| {name} | {cells.get('playwright', '')} | {cells.get('ultron', '')} |")
    diff = defaultdict(list)
    for p in pages:
        for s in seeds:
            a, b = runs.get(("playwright", p, s)), runs.get(("ultron", p, s))
            if a and b:
                diff[p].append(float(bool(b["correct"])) - float(bool(a["correct"])))
    lo, hi = boot(diff)
    lines += ["", f"Ultron - Playwright, correct rate, paired by (page, seed): {mean([x for v in diff.values() for x in v]):+.1%} "
              f"(95% CI {lo:+.1%} to {hi:+.1%}, bootstrap over {len(diff)} pages)", "",
              "Per page (correct out of seeds): page | Playwright | Ultron", ""]
    for p in pages:
        cells = [f"{sum(bool(runs[(arm, p, s)]['correct']) for s in seeds if (arm, p, s) in runs)}/{sum((arm, p, s) in runs for s in seeds)}" for arm in ARMS]
        lines.append(f"- {p}{' (hold)' if runs[next(k for k in runs if k[1] == p)]['score']['must_hold'] else ''}: {cells[0]} | {cells[1]}")
    wrong = Counter()
    for (arm, p, s), r in runs.items():
        for w in r["score"]["wrong"]:
            wrong[(arm, p, w["key"], w["label"][:60])] += 1
    lines += ["", "Wrong fields sent (arm, page, field: times):", ""]
    lines += [f"- {a} {p} {k} ({lab}): {n}" for (a, p, k, lab), n in sorted(wrong.items())]
    return "\n".join(lines)


if __name__ == "__main__":
    print("\n\n".join(summary(Path(o)) for o in sys.argv[1:]))
