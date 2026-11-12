"""Pick the forms gate with conformal risk control (Angelopoulos et al., ICLR 2024). Usage: calibrate_gate.py [ALPHA]

Loss on one form: fields the model would fill wrongly, as a share of its scored fields. It can only fall as the
gate rises and is at most 1, so the smallest gate with n/(n+1) * mean loss + 1/(n+1) <= alpha keeps the expected
loss on a new form from the same source at or below alpha. The form is the unit, since fields on a form aren't
exchangeable. Calibration uses the 23 forms already used for tuning, never the unseen ones.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "experiments/bench"), str(ROOT / "third_party/cua/libs/cua-s1/python/src")]

from cua_s1.schema import Element  # noqa: E402
from real_bench import load_forms  # noqa: E402

from ultron import FastPath, parse_document  # noqa: E402

CHECKPOINTS = [ROOT / f"models/ultron-forms-0.1/{m}/model.safetensors" for m in "ab"]


def main():
    alpha = float(sys.argv[1]) if len(sys.argv) > 1 else 0.05
    fills = []  # per form: (confidence, wrong) for each scored field the model would fill, and the scored field count
    for form in load_forms("test"):
        fast = FastPath(parse_document(form["document"]), CHECKPOINTS)
        scored = [f for f in form["fields"] if f["role"] == "text" and (f["key"] in form["gold"] or f["key"] in form["empty"])]
        if not scored:
            continue
        results = fast._score([(Element("Edit", f["label"], ""), "") for f in scored])
        fills.append(([(confidence, fast.document[choice].value != form["gold"].get(f["key"])) for f, (choice, confidence) in zip(scored, results) if choice < fast._n], len(scored)))
    n = len(fills)
    gates = sorted({0.0, 1.01, *(confidence for rows, _ in fills for confidence, _ in rows)})
    def risk(gate):
        return sum(sum(wrong for confidence, wrong in rows if confidence >= gate) / size for rows, size in fills) / n
    gate = next(g for g in gates if n / (n + 1) * risk(g) + 1 / (n + 1) <= alpha)
    filled = sum(confidence >= gate for rows, _ in fills for confidence, _ in rows)
    total = sum(size for _, size in fills)
    print(json.dumps({"forms": n, "alpha": alpha, "gate": round(gate, 6), "calibration_loss": round(risk(gate), 4), "model_fills": filled, "scored_fields": total}))
    for g in (0.6, 0.8, 0.9, 0.95, 0.99):
        print(f"gate {g}: mean wrong share {risk(g):.4f}, model fills {sum(c >= g for rows, _ in fills for c, _ in rows)} of {total}, wrong {sum(w for rows, _ in fills for c, w in rows if c >= g)}")


if __name__ == "__main__":
    main()
