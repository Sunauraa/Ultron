"""The fair LLM baseline: same question and same written policy as the model, one call per pop-up, no browser.
Usage: baseline_llm.py fresh|final OUT.jsonl

Calls run one at a time so the latency is real. Needs the local LLM server.
"""

import json
import sys
import time
from pathlib import Path

from label_popups_llm import LEAVE, ask

ROOT = Path(__file__).resolve().parents[2]


def main():
    if sys.argv[1] == "final":
        items = json.loads((ROOT / "data/popups/captures/final_test.json").read_text())
    else:
        items = [x for x in json.loads((ROOT / "data/popups/captures/testset.json").read_text()) if x["set"] == "fresh"]
    with open(sys.argv[2], "w") as out:
        for item in items:
            start = time.perf_counter()
            try:
                answer = ask(item["text"], item["buttons"], 1)
            except Exception as e:
                answer = {"error": type(e).__name__, "action": None}
            action = LEAVE if answer.get("is_popup") is False else answer.get("action")
            choice = action if action in (LEAVE, "escalate", None) else f"click {action}"
            out.write(json.dumps({"text": item["text"], "split": item["split"], "choice": choice, "ms": (time.perf_counter() - start) * 1000, **answer}, ensure_ascii=False) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
