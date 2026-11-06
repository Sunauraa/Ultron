"""Resolve browser pop-ups through Cua Driver with a tiny scorer ensemble.

The model picks a button, ``leave alone`` or ``escalate``. Below the gate it defers to the caller's
LLM. Page text is untrusted data: it only ever reaches the scorer, which has no tools. Ambiguous or
unlabelled targets are never clicked.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import torch

from .driver import BaseDriver, DriverError
from .model import ChoiceExample, load_checkpoint

LEAVE, ESCALATE = "leave alone", "escalate"
DEFAULT_GATE = 0.6
TASK = "TASK clear this pop-up safely\nDIALOG "
DIALOG_ROLES = {"dialog", "alertdialog"}
CLICKABLE_ROLES = {"button", "link"}
UNLABELLED = "(no label)"
Outcome = Literal["click", "leave_alone", "escalate", "defer", "no_popup"]
_LINE = re.compile(r'^(?P<indent>\s*)- (?P<role>[\w-]+)(?: (?P<name>"(?:[^"\\]|\\.)*"))?')


def dialog_context(text: str, options: Sequence[str]) -> str:
    """Model input: the buttons on offer, then the wording.

    Options are scored separately, so this is the only way leave alone and escalate can see them.
    """
    buttons = " | ".join(o.removeprefix("click ")[:24] for o in options if o.startswith("click "))
    return "BUTTONS " + buttons[:180] + "\n" + TASK + text


class Scorer(Protocol):
    def score(self, text: str, buttons: Sequence[str]) -> tuple[str, float, dict[str, float]]:
        """Return the chosen option, its confidence, and every option's probability."""
        ...


class EnsembleScorer:
    """Average the probabilities of several checkpoints, loaded without executing serialized code."""

    def __init__(self, checkpoints: Sequence[str | Path], device: str = "cpu") -> None:
        if not checkpoints:
            raise ValueError("at least one checkpoint is required")
        self.members = [load_checkpoint(path, device)[:2] for path in checkpoints]
        self.device = device

    def score(self, text: str, buttons: Sequence[str]) -> tuple[str, float, dict[str, float]]:
        options = [f"click {b}" for b in buttons] + [LEAVE, ESCALATE]
        example = ChoiceExample(dialog_context(text, options), tuple(options), 0)
        rows = []
        with torch.no_grad():
            for model, collate in self.members:
                batch = {k: v.to(self.device) for k, v in collate([example]).items()}
                rows.append(model(batch).softmax(-1))
        probabilities = torch.stack(rows).mean(0)[0]
        best = int(probabilities.argmax())
        return options[best], float(probabilities[best]), dict(zip(options, map(float, probabilities)))


@dataclass
class Candidate:
    """One top-level group of the page outline that holds text and something clickable."""

    role: str
    text: str
    buttons: list[str]


@dataclass
class DialogDecision:
    outcome: Outcome
    role: str | None = None
    text: str = ""
    choice: str | None = None
    confidence: float = 0.0
    distribution: dict[str, float] = field(default_factory=dict)
    reason: str = ""
    clicked_ref: str | None = None
    dismissed: bool | None = None


def _name(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return str(json.loads(raw))
    except json.JSONDecodeError:
        return raw[1:-1]


def find_candidates(outline: str, include_unlabelled: bool = False) -> list[Candidate]:
    """Read dialogs out of a semantic outline; optionally also unlabelled top-level groups.

    Many real pop-ups are plain fixed-position elements with no dialog role. They appear here only as
    generic groups, indistinguishable from page sections, so the model has to judge those itself.
    """
    nodes = []
    for line in outline.splitlines():
        match = _LINE.match(line)
        if match:
            nodes.append((len(match["indent"]), match["role"], _name(match["name"])))
    found = []
    index = 0
    while index < len(nodes):
        indent, role, _ = nodes[index]
        labelled = role in DIALOG_ROLES
        if not labelled and not (include_unlabelled and indent == 0 and role in {"generic", "region", "group"}):
            index += 1
            continue
        end = index + 1
        while end < len(nodes) and nodes[end][0] > indent:
            end += 1
        inside = nodes[index + 1 : end]
        words = [name for _, _, name in inside if name]
        buttons = list(dict.fromkeys(name or UNLABELLED for _, r, name in inside if r in CLICKABLE_ROLES))
        if words and buttons:
            found.append(Candidate(role, " ".join(words), buttons))
        index = end
    return found


class Browser(Protocol):
    def call(self, tool: str, **args: Any) -> dict[str, Any]: ...


def _checked(tool: str, response: Mapping[str, Any]) -> dict[str, Any]:
    """Driver refusals come back as ordinary results, so they have to be raised here."""
    if response.get("status") != "ok":
        refusal = response.get("refusal")
        code = refusal.get("code") if isinstance(refusal, Mapping) else None
        raise DriverError(str(code or "driver_refused"), f"Cua Driver refused {tool}", tool=tool, details={"response": repr(response)[:1000]})
    return dict(response)


def _snapshot(driver: Browser | BaseDriver, session: str, target_id: str, tab_id: str) -> dict[str, Any]:
    return _checked(
        "get_browser_state",
        driver.call("get_browser_state", target_id=target_id, tab_id=tab_id, session=session, snapshot_format="semantic_v2"),
    )


def bind_window(driver: Browser | BaseDriver, session: str, pid: int, window_id: int) -> tuple[str, str]:
    """Return the session-scoped target and active tab of one exact browser window."""
    bound = _checked("get_browser_state", driver.call("get_browser_state", pid=pid, window_id=window_id, session=session))
    tabs = bound.get("tabs") or []
    active = [tab for tab in tabs if tab.get("active")]
    if len(active) != 1:
        raise DriverError("ambiguous_tab", "Expected exactly one active tab", tool="get_browser_state")
    return str(bound["target_id"]), str(active[0]["tab_id"])


def handle_dialog(
    driver: Browser | BaseDriver,
    scorer: Scorer,
    target_id: str,
    tab_id: str,
    *,
    session: str = "cua-s1",
    gate: float = DEFAULT_GATE,
    execute: bool = True,
    include_unlabelled: bool = False,
    delivery_mode: str = "background",
) -> DialogDecision:
    """Decide on the topmost pop-up of a bound tab and, if allowed, click the chosen button."""
    state = _snapshot(driver, session, target_id, tab_id)
    candidates = find_candidates(str(state.get("outline") or ""), include_unlabelled)
    if not candidates:
        return DialogDecision("no_popup", reason="no candidate in the page outline")
    judged = []
    for candidate in candidates:
        choice, confidence, distribution = scorer.score(candidate.text, candidate.buttons)
        judged.append((candidate, choice, confidence, distribution))
    # A real dialog outranks unlabelled groups; among the rest the model's confident click wins.
    def rank(item: tuple[Candidate, str, float, dict[str, float]]) -> tuple[bool, bool, float]:
        return item[0].role in DIALOG_ROLES, item[1].startswith("click ") and item[2] >= gate, item[2]

    candidate, choice, confidence, distribution = max(judged, key=rank)
    decision = DialogDecision("defer", candidate.role, candidate.text, choice, confidence, distribution)
    if candidate.role not in DIALOG_ROLES and not (choice.startswith("click ") and confidence >= gate):
        decision.outcome, decision.reason = "no_popup", "the model did not treat any unlabelled group as a pop-up"
        return decision
    if confidence < gate:
        decision.reason = f"confidence below gate {gate}"
        return decision
    if choice == LEAVE:
        decision.outcome, decision.reason = "leave_alone", "needs the user or is not a pop-up to clear"
        return decision
    if choice == ESCALATE:
        decision.outcome, decision.reason = "escalate", "destructive or payment decision belongs to a human"
        return decision
    label = choice.removeprefix("click ")
    matches = [r for r in state.get("refs") or [] if r.get("name") == label and r.get("role") in CLICKABLE_ROLES]
    if label == UNLABELLED or len(matches) != 1:
        decision.reason = f"button is not uniquely identifiable ({len(matches)} matches)"
        return decision
    decision.outcome = "click"
    if not execute:
        decision.reason = "dry run"
        return decision
    decision.clicked_ref = str(matches[0]["ref"])
    driver.call("browser_click", target_id=target_id, tab_id=tab_id, session=session, ref=decision.clicked_ref, delivery_mode=delivery_mode)
    after = _snapshot(driver, session, target_id, tab_id)
    remaining = find_candidates(str(after.get("outline") or ""), include_unlabelled)
    decision.dismissed = not any(item.text == candidate.text for item in remaining)
    return decision
