"""Pack the ensemble's weights for the browser, unchanged, plus reference outputs to check the JS against.
Usage: export_demo.py OUT_DIR CHECKPOINT [CHECKPOINT ...]
"""

import base64
import json
import sys
from pathlib import Path

import numpy as np
import torch

from cua_s1.model import ChoiceExample, load_checkpoint
from synth_dialogs import ESCALATE, LEAVE, dialog_context

SAMPLES = [
    ("We use cookies to improve your experience. You can accept all or reject the optional ones.", ["Accept all", "Reject all", "Cookie settings", "Privacy policy"]),
    ("Chúng tôi sử dụng cookie để cải thiện trải nghiệm của bạn.", ["Chấp nhận", "Từ chối"]),
    ("Are you sure you want to permanently delete your account? This cannot be undone.", ["Delete account"]),
    ("Get 20% off your first order! Join our newsletter today.", ["Claim my discount", "No thanks", "×"]),
]


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    meta, blob, offset = [], bytearray(), 0
    systems = [load_checkpoint(path, "cpu")[:3] for path in sys.argv[2:]]
    for model, _, config in systems:
        tensors = {}
        for name, value in model.state_dict().items():
            array = value.numpy().astype(np.float32)
            data = array.tobytes()
            tensors[name] = {"shape": list(array.shape), "offset": offset}
            blob += data
            offset += len(data)
        meta.append({"config": config, "tensors": tensors})
    (out / "weights.json").write_text(json.dumps({"members": meta, "data": base64.b64encode(bytes(blob)).decode()}))
    refs = []
    for text, buttons in SAMPLES:
        options = [f"click {b}" for b in buttons] + [LEAVE, ESCALATE]
        example = ChoiceExample(dialog_context(text, options), tuple(options), 0)
        per_model = []
        with torch.no_grad():
            for model, collate, _ in systems:
                per_model.append(model(collate([example])).softmax(-1)[0].tolist())
        refs.append({"text": text, "buttons": buttons, "options": options, "context": example.context, "probs": per_model})
    (out / "reference.json").write_text(json.dumps(refs, ensure_ascii=False, indent=0))
    print(len(blob) / 1e6, "MB;", sum(len(m["tensors"]) for m in meta), "tensors")
    print(sorted(meta[0]["tensors"])[:30], meta[0]["config"])


if __name__ == "__main__":
    main()
