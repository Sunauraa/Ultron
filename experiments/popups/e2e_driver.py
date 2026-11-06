"""Run the pop-up model through the real Cua Driver against local test pages. Usage: e2e_driver.py BINARY MODEL,MODEL

Pages live on localhost and name no real site. Each page's title records the button that was actually
clicked, so the result comes from the browser and not from what the model believes it did.
"""

import statistics
import sys
import time

from cua_s1.dialogs import EnsembleScorer, bind_window, handle_dialog
from cua_s1.driver import CuaDriver

BASE = "http://127.0.0.1:8931/"
SESSION = "dlg"
# page, expected outcome and button with unlabelled groups off, the same with them on
CASES = [
    ("cookie", "click", "Reject all", "click", "Reject all"),
    ("cookie_vi", "click", "Từ chối", "click", "Từ chối"),
    ("promo_trap", "click", "No thanks", "click", "No thanks"),
    ("delete_only", "escalate", None, "escalate", None),
    ("login_wall", "leave_alone", None, "leave_alone", None),
    ("cookie_fixed", "no_popup", None, "click", "Only necessary"),
    ("notify_fixed", "no_popup", None, "click", "Not now"),
    ("no_popup", "no_popup", None, "no_popup", None),
    ("shop_sections", "no_popup", None, "no_popup", None),
    ("chat_widget", "no_popup", None, "no_popup", None),
    ("two_sections_and_dialog", "click", "Reject all", "click", "Reject all"),
]


def main():
    driver = CuaDriver(SESSION, transport="cli", binary=sys.argv[1])
    scorer = EnsembleScorer(sys.argv[2].split(","))
    window = driver.call("list_windows")["windows"][0]
    target, tab = bind_window(driver, SESSION, window["pid"], window["window_id"])
    passed, total, seconds = 0, 0, []
    for unlabelled in (False, True):
        print("unlabelled groups", "on" if unlabelled else "off")
        for page, *expected in CASES:
            want_outcome, want_button = expected[2:] if unlabelled else expected[:2]
            driver.call("browser_navigate", target_id=target, tab_id=tab, session=SESSION, url=f"{BASE}{page}.html")
            time.sleep(0.5)
            start = time.perf_counter()
            decision = handle_dialog(driver, scorer, target, tab, session=SESSION, include_unlabelled=unlabelled, delivery_mode="foreground")
            seconds.append(time.perf_counter() - start)
            time.sleep(0.2)
            title = driver.call("get_browser_state", target_id=target, tab_id=tab, session=SESSION, snapshot_format="semantic_v2")["page"]["title"]
            clicked = title.removeprefix("clicked: ") if title.startswith("clicked: ") else None
            ok = decision.outcome == want_outcome and clicked == want_button and (want_button is None or decision.dismissed is True)
            passed, total = passed + ok, total + 1
            print(f"  {'PASS' if ok else 'FAIL'} {page:13} {decision.outcome:12} conf {decision.confidence:.2f} choice {decision.choice!r} browser clicked {clicked!r} dismissed {decision.dismissed} want {want_outcome}/{want_button}")
    print(f"{passed}/{total} passed; handle_dialog median {statistics.median(seconds):.2f} s, includes driver CLI calls")


if __name__ == "__main__":
    main()
