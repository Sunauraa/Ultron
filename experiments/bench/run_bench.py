"""Run Browser Use alone or with the fast path over the real forms. Usage: run_bench.py plain|hints|hintsflash|s1 NAME SPLIT SEED [FORMS_CKPT,... [FORM_GATE]]

The local LLM at port 8007 (or ULTRON_LLM_PORT) is the LLM in every arm; each record names the model served. Vision and judge are off, as in the baseline.
Each run writes one JSON file, and a finished run isn't repeated.
"""

import asyncio
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.update(
    ANONYMIZED_TELEMETRY="false", BROWSER_USE_CLOUD_SYNC="false", BROWSER_USE_LOGGING_LEVEL="result", SKIP_LLM_API_KEY_VERIFICATION="true",
    XDG_CONFIG_HOME=str(ROOT / ".cache/config"), BROWSER_USE_CONFIG_DIR=str(ROOT / ".cache/config/browseruse"),
)
sys.path[:0] = [str(ROOT), str(ROOT / "experiments/bench"), str(ROOT / "third_party/cua/libs/cua-s1/python/src")]

import torch  # noqa: E402

torch.set_num_threads(1)

from browser_use import Agent, BrowserProfile, ChatOpenAI  # noqa: E402
from real_bench import Server, load_forms  # noqa: E402
from run_baseline import LoggedLLM  # noqa: E402

from ultron import FastPath, install, parse_document  # noqa: E402

CHROME = ROOT / ".cache/pw/chromium-1248/chrome-linux64/chrome"
DIALOGS = [ROOT / f"models/ultron-dialogs-0.1/{m}/model.safetensors" for m in "ab"]
MAX_STEPS = 25
LLM = f"http://127.0.0.1:{os.environ.get('ULTRON_LLM_PORT', '8007')}"  # one server per GPU when runs go in parallel
HINTS = (
    " Work efficiently: fill every field you have a value for in one step using several input actions, matching each value to its field by the field's label. "
    "Type a value only where the label asks for exactly that value, and never retype a field that already holds a value. Press the submit button once, right after filling. "
    "As soon as the page confirms receipt, finish."
)
BASELINES = {"plain": ("", {}), "hints": (HINTS, {}), "hintsflash": (HINTS, {"flash_mode": True})}  # LLM alone: default, and tuned on the used-up forms


async def run_one(form, server, arm, seed, out_dir, checkpoints, gate):
    url = f"http://127.0.0.1:{server.port}/{form['id']}"
    task = (
        f"Go to {url}, fill in the form using the document below, and submit it. "
        "Leave fields empty if the document has no value for them, and tick a consent box only if it is required. "
        "If a required field has no value in the document, do not invent one and do not submit: finish with success false and name the missing field. "
        "If a pop-up appears, clear it safely: refuse cookies if you can, otherwise close it. Finish once the page confirms receipt.\n\n"
        f"Document:\n{form['document']}"
    ).replace("\n\nDocument:", BASELINES.get(arm, ("", {}))[0] + "\n\nDocument:")
    llm = LoggedLLM(ChatOpenAI(model="local", base_url=f"{LLM}/v1", api_key="local", temperature=0.0, seed=seed))
    profile = BrowserProfile(headless=True, executable_path=str(CHROME), chromium_sandbox=False, user_data_dir=None, allowed_domains=["127.0.0.1"])
    agent = Agent(task=task, llm=llm, browser_profile=profile, use_vision=False, use_judge=False, max_failures=5, **BASELINES.get(arm, ("", {}))[1])
    fast = install(agent, FastPath(parse_document(form["document"]), checkpoints, DIALOGS, form_gate=gate, finish=True)) if arm == "s1" else None
    start = time.perf_counter()
    history = await agent.run(max_steps=MAX_STEPS)
    served = json.load(urllib.request.urlopen(f"{LLM}/v1/models", timeout=10))["data"][0]["root"]  # a dead server must not leave a result behind
    record = {
        "form": form["id"], "lang": form["lang"], "arm": arm, "seed": seed, "model": served, "seconds": round(time.perf_counter() - start, 1), "score": server.score(form), "calls": llm.calls, "steps": len(history.history),
        "is_done": history.is_done(), "success": history.is_successful(), "final": history.final_result(), "fast": [vars(s) for s in fast.steps] if fast else [],
    }
    (out_dir / f"{form['id']}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1))
    score = record["score"]
    fast_steps = sum(s["kind"] != "llm" for s in record["fast"])
    print(f"{form['id']:8} {form['lang']} sub={score['submitted']} wrong={len(score['wrong'])}/{score['fields']} extra={len(score['extra'])} pop={score['popup_ok']} calls={len(llm.calls)} fast={fast_steps} {record['seconds']}s", flush=True)


async def main():
    arm, name, split, seed = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    checkpoints = [c for c in sys.argv[5].split(",") if c] if len(sys.argv) > 5 else []
    gate = float(sys.argv[6]) if len(sys.argv) > 6 else 0.9
    out_dir = ROOT / "results/bench" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    urllib.request.urlopen(f"{LLM}/v1/models", timeout=10)
    forms = load_forms(split)
    server = Server(forms)
    for form in forms:
        if not (out_dir / f"{form['id']}.json").exists():
            await run_one(form, server, arm, seed, out_dir, checkpoints, gate)


if __name__ == "__main__":
    asyncio.run(main())
