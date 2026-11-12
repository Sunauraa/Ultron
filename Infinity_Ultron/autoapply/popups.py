"""Ultron's pop-up model: picks the safe button on a pop-up, or says to leave it alone, or to hand it to a person.

This is the original Ultron model (ultron-dialogs-0.1: a byte-level transformer of under 1M parameters, two
ensemble members), run with numpy so Ultron needs no deep-learning library. On 281 held-out pop-ups it answered
252 at the 0.6 gate and was right on 94.4% of those (README of the main project). tests/test_popups.py checks
that this numpy version gives the same probabilities as the PyTorch original.

Page text only reaches this model, which has no tools and can only pick one of the options it is given.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

MODELS = Path(__file__).resolve().parent / "models" / "popups"
LEAVE, ESCALATE = "leave alone", "escalate"
GATE = 0.6
TASK = "TASK clear this pop-up safely\nDIALOG "


def load_safetensors(path: Path) -> dict[str, np.ndarray]:
    """Read a safetensors file (float32 tensors) without executing anything."""
    data = path.read_bytes()
    size = struct.unpack("<Q", data[:8])[0]
    header = json.loads(data[8:8 + size])
    tensors = {}
    for name, info in header.items():
        if name == "__metadata__":
            continue
        if info["dtype"] != "F32":
            raise ValueError(f"{name}: unsupported dtype {info['dtype']}")
        start, end = info["data_offsets"]
        tensors[name] = np.frombuffer(data[8 + size + start:8 + size + end], dtype="<f4").reshape(info["shape"])
    return tensors


def byte_ids(text: str, length: int) -> list[int]:
    return [b + 1 for b in text.encode("utf-8", errors="replace")[:length]]


def layer_norm(x: np.ndarray, weight: np.ndarray, bias: np.ndarray) -> np.ndarray:
    mean = x.mean(-1, keepdims=True)
    var = ((x - mean) ** 2).mean(-1, keepdims=True)
    return (x - mean) / np.sqrt(var + 1e-5) * weight + bias


def softmax(x: np.ndarray) -> np.ndarray:
    x = x - x.max(-1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(-1, keepdims=True)


class Member:
    """One checkpoint of the ensemble (PyTorch's TransformerEncoderLayer, pre-norm, ReLU, eval mode)."""

    def __init__(self, folder: Path) -> None:
        config = json.loads((folder / "config.json").read_text())["config"]
        if config.get("encoder") != "tinyx":
            raise ValueError("only the tinyx encoder is supported")
        self.w = load_safetensors(folder / "model.safetensors")
        self.heads, self.rank = int(config.get("heads", 4)), int(config["rank"])
        self.layers = int(config.get("layers", 2))
        self.context_tokens, self.option_tokens = int(config["context_tokens"]), int(config["option_tokens"])

    def encoder_layer(self, prefix: str, x: np.ndarray, keep: np.ndarray) -> np.ndarray:
        """x: (n, L, W); keep: (n, L) which positions can be attended to."""
        w = self.w
        n, length, width = x.shape
        head_width = width // self.heads
        h = layer_norm(x, w[prefix + "norm1.weight"], w[prefix + "norm1.bias"])
        qkv = h @ w[prefix + "self_attn.in_proj_weight"].T + w[prefix + "self_attn.in_proj_bias"]
        q, k, v = (qkv[..., i * width:(i + 1) * width].reshape(n, length, self.heads, head_width).transpose(0, 2, 1, 3) for i in range(3))
        scores = q @ k.transpose(0, 1, 3, 2) / np.sqrt(head_width)
        scores = np.where(keep[:, None, None, :], scores, -np.inf)
        attended = (softmax(scores) @ v).transpose(0, 2, 1, 3).reshape(n, length, width)
        x = x + attended @ w[prefix + "self_attn.out_proj.weight"].T + w[prefix + "self_attn.out_proj.bias"]
        h = layer_norm(x, w[prefix + "norm2.weight"], w[prefix + "norm2.bias"])
        h = np.maximum(h @ w[prefix + "linear1.weight"].T + w[prefix + "linear1.bias"], 0)
        return x + h @ w[prefix + "linear2.weight"].T + w[prefix + "linear2.bias"]

    def embed(self, ids: np.ndarray) -> np.ndarray:
        return self.w["embedding.weight"][ids] + self.w["position.weight"][np.arange(ids.shape[-1])]

    def probabilities(self, context: str, options: list[str]) -> np.ndarray:
        w = self.w
        context_ids = np.array([byte_ids(context, self.context_tokens) or [0]])
        context_mask = context_ids != 0
        safe = context_mask.copy()
        safe[:, 0] = True
        hidden = self.embed(context_ids)
        for i in range(self.layers):
            hidden = self.encoder_layer(f"encoder.layers.{i}.", hidden, safe)
        rows = [byte_ids(o, self.option_tokens) for o in options]
        width = max(1, max(map(len, rows)))
        option_ids = np.array([r + [0] * (width - len(r)) for r in rows])
        option_mask = option_ids != 0
        safe = option_mask.copy()
        safe[:, 0] = True
        encoded = self.encoder_layer("option_encoder.layers.0.", self.embed(option_ids), safe)
        weights = option_mask[..., None].astype(np.float32)
        pooled = (encoded * weights).sum(1) / np.maximum(weights.sum(1), 1)
        c = layer_norm(hidden[0], w["head.context_norm.weight"], w["head.context_norm.bias"])
        o = layer_norm(pooled, w["head.option_norm.weight"], w["head.option_norm.bias"])
        query, key, value = o @ w["head.query.weight"].T, c @ w["head.key.weight"].T, c @ w["head.value.weight"].T
        scores = np.where(context_mask[0][None, :], query @ key.T / np.sqrt(self.rank), -np.inf)
        attended = softmax(scores) @ value
        logits = (query * attended).sum(-1) / np.sqrt(self.rank)
        return softmax(logits)


def context_of(text: str, options: list[str]) -> str:
    """The model's input: the buttons on offer, then the wording (as the model was trained)."""
    buttons = " | ".join(o.removeprefix("click ")[:24] for o in options if o.startswith("click "))
    return "BUTTONS " + buttons[:180] + "\n" + TASK + text


class PopupModel:
    def __init__(self, folder: Path = MODELS) -> None:
        self.members = [Member(f) for f in sorted(folder.iterdir()) if (f / "model.safetensors").exists()]
        if not self.members:
            raise FileNotFoundError(f"no pop-up model in {folder}")

    def score(self, text: str, buttons: list[str]) -> tuple[str, float, dict[str, float]]:
        """The chosen option ("click <button>", leave alone or escalate), its probability, and every option's."""
        options = [f"click {b}" for b in buttons] + [LEAVE, ESCALATE]
        context = context_of(text, options)
        p = np.mean([m.probabilities(context, options) for m in self.members], axis=0)
        best = int(p.argmax())
        return options[best], float(p[best]), dict(zip(options, map(float, p)))
