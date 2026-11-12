"""The pop-up baselines on equal terms: how often each setup answers, and how often it is right when it does. Usage: baselines_fair.py

Counts come from results/popups_llm/more/baselines_table.txt and results/final_result.txt, nothing is rescored. Deferring isn't free,
so bad clicks alone favour whoever answers least. Intervals are 95% Wilson. The model's other gates were not chosen
on this data: they show the trade-off and are not a result to quote as the model's score.
"""

import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def wilson(k, n):
    z, p = 1.96, k / n
    centre, half = (p + z * z / (2 * n)) / (1 + z * z / n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def row(name, right, deferred, wrong, trap):
    answered, bad = right + wrong + trap, wrong + trap
    low, high = wilson(right, answered)
    print(f"{name:34}{answered:9}{deferred:9}{right:7}{bad:6}{right / answered:9.1%}  [{low:.1%}, {high:.1%}]")


def main():
    print(f"{'n=281':34}{'answered':>9}{'deferred':>9}{'right':>7}{'bad':>6}{'precision':>9}  95% interval")
    final = (ROOT / "results/final_result.txt").read_text().split("final/kind")[0]
    found = {m[0]: tuple(map(int, m[1:])) for m in re.findall(r"^  (.+?)\s+n=281 right=(\d+) deferred=(\d+) WRONG=(\d+) TRAP=(\d+)", final, re.M)}
    print("Locked model")
    row("  gate 0.6 (locked)", *found["model@gate"])
    print("Same model at other gates, for the trade-off only")
    for gate in ("0.5", "0.7", "0.8", "0.9"):
        row(f"  gate {gate}", *found[f"model@{gate}"])
    print("Original baselines")
    row("  rules", *found["rules"])
    row("  Qwen2.5-14B one call", *found["llm with policy"])
    row("  Qwen2.5-14B agent", *found["qwen agent"])
    mode = None
    for line in (ROOT / "results/popups_llm/more/baselines_table.txt").read_text().splitlines()[2:]:
        if line.startswith("--"):
            mode = line[3:].strip()
            print({"agent": "Added baselines, agent (must click, finds the pop-up itself)", "policy": "Added baselines, one call"}[mode])
        elif match := re.match(r"(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s", line):
            row("  " + match[1], *map(int, match.groups()[1:]))


if __name__ == "__main__":
    main()
