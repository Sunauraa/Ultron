"""Turn per-button classes into the action the policy asks for. Used only to make training labels."""

LEAVE, ESCALATE = "leave alone", "escalate"
WALL = {"wall"}
DANGER = {"danger", "scam"}


def agreed(item):
    """The label both passes support: (is_popup, kind, classes, actions), or None if they conflict."""
    a, b = item["votes"]
    if "error" in a or "error" in b or a.get("is_popup") != b.get("is_popup"):
        return None
    if a["is_popup"] is False:
        return False, "not_popup", {}, [LEAVE]
    both = [x for x in action(a["kind"], a["classes"]) if x in action(b["kind"], b["classes"])]
    if not both or action(a["kind"], a["classes"]) != action(b["kind"], b["classes"]) and set(both) == {LEAVE}:
        return None
    return True, a["kind"], a["classes"], both


def action(kind, classes):
    """The right action for a pop-up offering these buttons. Several may be equally good."""
    has = lambda name: [b for b, c in classes.items() if c == name]
    if kind in WALL:
        return [LEAVE]
    if kind == "session" and has("stay"):
        return has("stay")
    refuse = has("reject") or has("close")
    if refuse:
        return refuse
    if kind in DANGER:
        return [ESCALATE]
    return has("accept") or [LEAVE]
