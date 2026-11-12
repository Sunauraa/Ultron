"""How well the tiny models' confidence matches how often they are right, and whether temperature scaling helps.
Usage: calibration.py [cpu|cuda]

Data is only what has already been scored: the 343 tuning pop-ups and the 78 real forms (dev, test, and the 42 of the
final run, reported apart). Labels come from the same LLM-assisted process as the benchmarks, not from people.
Temperature (Guo et al., ICML 2017) is one number shared by both ensemble members, fitted on NLL with 5-fold
cross-validation by pop-up or by form, so every reported number is on a unit the fit never saw. "Normalised" is
(p - 1/n) / (1 - 1/n) over the n options, which rescales the gate but can't change the ranking within one n.
"""

import json
import random
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "experiments/bench"), str(ROOT / "experiments/popups"), str(ROOT / "third_party/cua/libs/cua-s1/python/src")]
torch.set_num_threads(4)

from cua_s1.model import ChoiceExample, load_checkpoint  # noqa: E402
from cua_s1.schema import Element, render_context, render_options  # noqa: E402
from real_bench import load_forms  # noqa: E402
from synth_dialogs import ESCALATE, LEAVE, dialog_context  # noqa: E402

from ultron import parse_document  # noqa: E402

DEVICE = sys.argv[1] if len(sys.argv) > 1 else "cpu"
TEMPS = [round(0.25 * 1.05 ** i, 3) for i in range(91)]  # 0.25 to about 21


def logits(models, examples):
    with torch.no_grad():
        return torch.stack([m(c(examples)).float().cpu() for m, c in models])  # members x examples x options


def popups():
    models = [load_checkpoint(ROOT / f"models/ultron-dialogs-0.1/{m}/model.safetensors", DEVICE)[:2] for m in "ab"]
    rows = []
    for item in json.loads((ROOT / "data/popups/captures/testset.json").read_text()):
        options = [f"click {b}" for b in item["buttons"]] + [LEAVE, ESCALATE]
        good = {a if a in (LEAVE, ESCALATE) else f"click {a}" for a in item["acceptable"]}
        z = logits(models, [ChoiceExample(dialog_context(item["text"], options), tuple(options), 0)])[:, 0]
        rows.append({"unit": item["text"], "group": "pop-ups", "z": z, "right": [o in good for o in options], "fills": [o not in (LEAVE, ESCALATE) for o in options]})
    return rows, 0.6


def forms():
    models = [load_checkpoint(ROOT / f"models/ultron-forms-0.1/{m}/model.safetensors", DEVICE)[:2] for m in "ab"]
    rows = []
    for split in ("dev", "test", "fresh"):
        for form in load_forms(split):
            document = parse_document(form["document"])
            options = tuple(render_options(document))
            n = len(document)
            for f in form["fields"]:
                if f["role"] != "text" or (f["key"] not in form["gold"] and f["key"] not in form["empty"]):
                    continue
                z = logits(models, [ChoiceExample(render_context("Form", Element("Edit", f["label"], ""), ""), options, 0)])[:, 0]
                gold = form["gold"].get(f["key"])
                right = [document[i].value == gold if i < n else gold is None and options[i] == "skip" for i in range(len(options))]
                rows.append({"unit": form["id"], "group": "final 42 forms" if split == "fresh" else "dev+test forms", "z": z, "right": right, "fills": [i < n for i in range(len(options))]})
    return rows, 0.9


def probs(row, t):
    return (row["z"] / t).softmax(-1).mean(0)


def nll(rows, t):
    return -sum(probs(r, t)[[i for i, ok in enumerate(r["right"]) if ok]].sum().clamp_min(1e-12).log().item() for r in rows) / len(rows)


def fit(rows):
    return min(TEMPS, key=lambda t: nll(rows, t))


def summary(points, gate):
    """points: (confidence, right, fills). ECE uses 10 equal-width bins."""
    n = len(points)
    bins = [[p for p in points if min(int(p[0] * 10), 9) == b] for b in range(10)]
    ece = sum(len(b) / n * abs(sum(c for c, _, _ in b) / len(b) - sum(r for _, r, _ in b) / len(b)) for b in bins if b)
    acted = [r for c, r, f in points if c >= gate and f]
    pos = [c for c, r, _ in points if r]
    neg = [c for c, r, _ in points if not r]
    auroc = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg)) if pos and neg else float("nan")
    fill = [(c, r) for c, r, f in points if f]
    fill_ece = sum(len(b) / len(fill) * abs(sum(c for c, _ in b) / len(b) - sum(r for _, r in b) / len(b)) for b in ([q for q in fill if min(int(q[0] * 10), 9) == k] for k in range(10)) if b) if fill else None
    return {"n": n, "accuracy": round(sum(r for _, r, _ in points) / n, 3), "mean_conf": round(sum(c for c, _, _ in points) / n, 3), "ECE": round(ece, 3), "AUROC": round(auroc, 3),
            "fills": len(fill), "fill accuracy": round(sum(r for _, r in fill) / len(fill), 3) if fill else None, "fill mean_conf": round(sum(c for c, _ in fill) / len(fill), 3) if fill else None, "fill ECE": round(fill_ece, 3) if fill else None,
            f"acts at gate {gate}": len(acted), "right when acting": round(sum(acted) / len(acted), 3) if acted else None,
            "bins": [(f"{b / 10:.1f}", len(x), round(sum(r for _, r, _ in x) / len(x), 2)) for b, x in enumerate(bins) if x]}


def point(row, t, normalise=False):
    p = probs(row, t)
    c, i = p.max(-1)
    c = c.item()
    if normalise:
        k = len(row["right"])
        c = (c - 1 / k) / (1 - 1 / k)
    return c, row["right"][i.item()], row["fills"][i.item()]


def main():
    for rows, gate in (popups(), forms()):
        units = sorted({r["unit"] for r in rows})
        random.Random(0).shuffle(units)
        fold = {u: i % 5 for i, u in enumerate(units)}
        temps = {}
        for k in range(5):
            temps[k] = fit([r for r in rows if fold[r["unit"]] != k])
        report = {}
        for group in sorted({r["group"] for r in rows}):
            mine = [r for r in rows if r["group"] == group]
            report[group] = {
                "raw": summary([point(r, 1.0) for r in mine], gate),
                "temperature (cross-validated)": summary([point(r, temps[fold[r["unit"]]]) for r in mine], gate),
                "normalised": summary([point(r, 1.0, True) for r in mine], gate),
            }
        print(json.dumps({"fold temperatures": temps, "temperature on all": fit(rows), **report}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
