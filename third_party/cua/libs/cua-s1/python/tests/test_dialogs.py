from __future__ import annotations

import pytest

from cua_s1.dialogs import ESCALATE, LEAVE, dialog_context, find_candidates, handle_dialog
from cua_s1.driver import DriverError
from cua_s1.server import RuntimeService

DIALOG = """- heading "Shop"
- dialog "Cookies"
  - paragraph
    - statictext "We use cookies."
  - button "Accept all" [focusable=true]
  - button "Reject all" [focusable=true]
  - link "Privacy \\"policy\\"" [focusable=true]"""
REFS = [
    {"ref": "p1:1", "role": "button", "name": "Accept all"},
    {"ref": "p1:2", "role": "button", "name": "Reject all"},
]
BANNER = """- heading "Shop"
- generic
  - statictext "We use cookies."
  - button "OK" [focusable=true]"""


class FixedScorer:
    def __init__(self, choice, confidence):
        self.result = (choice, confidence, {choice: confidence})
        self.seen = []

    def score(self, text, buttons):
        self.seen.append((text, list(buttons)))
        return self.result


class FakeDriver:
    def __init__(self, outline=DIALOG, refs=REFS, after="- heading \"Shop\""):
        self.outlines = [outline, after]
        self.refs = refs
        self.clicks = []

    def call(self, tool, **args):
        if tool == "get_browser_state":
            outline = self.outlines[0] if not self.clicks else self.outlines[1]
            return {"status": "ok", "outline": outline, "refs": self.refs}
        if tool == "browser_click":
            self.clicks.append(args["ref"])
            return {"status": "ok"}
        raise AssertionError(tool)


def decide(driver, choice, confidence=0.9, **options):
    return handle_dialog(driver, FixedScorer(choice, confidence), "target", "tab", **options)


def test_context_lists_buttons_before_text():
    options = ["click Accept", "click No", LEAVE, ESCALATE]
    assert dialog_context("Hello", options) == "BUTTONS Accept | No\nTASK clear this pop-up safely\nDIALOG Hello"


def test_outline_reads_text_and_buttons_of_a_dialog_only():
    found = find_candidates(DIALOG)
    assert len(found) == 1
    assert found[0].role == "dialog"
    assert found[0].text == 'We use cookies. Accept all Reject all Privacy "policy"'
    assert found[0].buttons == ["Accept all", "Reject all", 'Privacy "policy"']


def test_unlabelled_groups_are_opt_in():
    assert find_candidates(BANNER) == []
    assert find_candidates(BANNER, include_unlabelled=True)[0].buttons == ["OK"]


def test_confident_choice_clicks_the_named_button_and_checks_it_went_away():
    driver = FakeDriver()
    decision = decide(driver, "click Reject all")
    assert decision.outcome == "click"
    assert driver.clicks == ["p1:2"]
    assert decision.dismissed is True


def test_still_visible_dialog_is_reported_as_not_dismissed():
    driver = FakeDriver(after=DIALOG)
    assert decide(driver, "click Reject all").dismissed is False


@pytest.mark.parametrize(
    "choice, confidence, outcome",
    [("click Reject all", 0.5, "defer"), (LEAVE, 0.9, "leave_alone"), (ESCALATE, 0.9, "escalate")],
)
def test_only_a_confident_click_touches_the_page(choice, confidence, outcome):
    driver = FakeDriver()
    assert decide(driver, choice, confidence).outcome == outcome
    assert driver.clicks == []


def test_dry_run_never_clicks():
    driver = FakeDriver()
    decision = decide(driver, "click Reject all", execute=False)
    assert decision.outcome == "click"
    assert driver.clicks == []


def test_duplicate_or_missing_targets_defer_instead_of_guessing():
    twice = FakeDriver(refs=REFS + [{"ref": "p1:9", "role": "button", "name": "Reject all"}])
    assert decide(twice, "click Reject all").outcome == "defer"
    assert twice.clicks == []
    assert decide(FakeDriver(refs=[]), "click Reject all").outcome == "defer"


def test_page_without_candidates_is_not_scored():
    scorer = FixedScorer("click Reject all", 1.0)
    decision = handle_dialog(FakeDriver(outline='- heading "Shop"'), scorer, "target", "tab")
    assert decision.outcome == "no_popup"
    assert scorer.seen == []


def test_unlabelled_group_needs_a_confident_click_to_count_as_a_pop_up():
    refs = [{"ref": "p1:1", "role": "button", "name": "OK"}]
    assert decide(FakeDriver(BANNER, refs), LEAVE, include_unlabelled=True).outcome == "no_popup"
    assert decide(FakeDriver(BANNER, refs), "click OK", 0.5, include_unlabelled=True).outcome == "no_popup"
    assert decide(FakeDriver(BANNER, refs), "click OK", 0.9, include_unlabelled=True).outcome == "click"


def test_driver_refusal_is_raised():
    class Refusing:
        def call(self, tool, **args):
            return {"status": "refused", "refusal": {"code": "browser_consent_required"}}

    with pytest.raises(DriverError) as refused:
        decide(Refusing(), "click OK")
    assert refused.value.code == "browser_consent_required"


def test_mcp_tool_plans_by_default_and_clicks_only_when_asked(tmp_path):
    class BoundDriver(FakeDriver):
        session = "test"

        def call(self, tool, **args):
            if tool == "get_browser_state" and "pid" in args:
                return {"status": "ok", "target_id": "target", "tabs": [{"tab_id": "tab", "active": True}]}
            return super().call(tool, **args)

    driver = BoundDriver()
    service = RuntimeService(None, driver, allowed_pdf_roots=[tmp_path], dialog_scorer=FixedScorer("click Reject all", 0.9))
    planned = service.handle_dialog(1, 2)
    assert planned["decision"]["outcome"] == "click"
    assert driver.clicks == []
    assert service.handle_dialog(1, 2, execute=True)["decision"]["clicked_ref"] == "p1:2"
    assert driver.clicks == ["p1:2"]


def test_mcp_tool_reports_a_missing_model(tmp_path):
    service = RuntimeService(None, FakeDriver(), allowed_pdf_roots=[tmp_path])
    assert service.handle_dialog(1, 2)["error"]["code"] == "no_dialog_model"
