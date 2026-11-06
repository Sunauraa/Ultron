"""Compare labeller output with hand labels. Usage: check_labels.py LABELS.jsonl"""

import collections
import json
import sys

from button_policy import agreed

hand = {x["text"]: x for x in json.load(open("../popups/testset.json")) if x["set"] == "fresh"}
c, bad = collections.Counter(), []
for line in open(sys.argv[1]):
    item = json.loads(line)
    h, label = hand[item["text"]], agreed(item)
    side = "np" if h["split"] == "fresh_np" else "pop"
    if label is None:
        c[side, "no label"] += 1
    elif not label[0]:
        c[side, "called not pop-up"] += 1
    elif side == "np":
        c[side, "called pop-up"] += 1
    else:
        want = {a.removeprefix("click ") for a in h["acceptable"]}
        ok = all(a in want for a in label[3])
        c[side, "right" if ok else "wrong"] += 1
        if not ok:
            bad.append((item["text"][:50], label[1], [x[:25] for x in label[3][:3]], [x[:25] for x in sorted(want)[:3]]))
for k in sorted(c):
    print(k, c[k])
for b in bad:
    print(str(b).encode("ascii", "replace").decode())
