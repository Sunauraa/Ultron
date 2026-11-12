"""The numpy pop-up model must match the PyTorch original (ultron-dialogs-0.1) on every held-out pop-up.

Needs PyTorch and the cua_s1 package (third_party/cua), which Ultron itself doesn't.
Usage: python tests/test_popups.py   (exit code 0 when every pop-up matches)
"""

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent / "research"  # the original model, its test pop-ups and its library
sys.path[:0] = [str(HERE.parent), str(ROOT / "third_party/cua/libs/cua-s1/python/src")]
from cua_s1.dialogs import EnsembleScorer  # noqa: E402

import popups  # noqa: E402

items = json.loads((ROOT / "data/popups/captures/final_test.json").read_text())
torch_model = EnsembleScorer([ROOT / "models/ultron-dialogs-0.1/a", ROOT / "models/ultron-dialogs-0.1/b"])
numpy_model = popups.PopupModel()
worst, different, took = 0.0, [], 0.0
for item in items:
    choice_t, _, dist_t = torch_model.score(item["text"], item["buttons"])
    start = time.perf_counter()
    choice_n, _, dist_n = numpy_model.score(item["text"], item["buttons"])
    took += time.perf_counter() - start
    worst = max(worst, max(abs(dist_t[k] - dist_n[k]) for k in dist_t))
    if choice_t != choice_n:
        different.append((item["url"], choice_t, choice_n))
print(f"{len(items)} pop-ups: largest probability difference {worst:.2e}, {len(different)} different choices, "
      f"{1000 * took / len(items):.1f} ms per pop-up (numpy)")
for row in different:
    print("  differs:", row)
sys.exit(1 if different or worst > 1e-4 else 0)
