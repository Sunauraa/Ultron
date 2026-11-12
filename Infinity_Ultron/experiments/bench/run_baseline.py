"""Run plain Browser Use on the local forms with a local LLM, logging every LLM call.

Usage: run_baseline.py RUN_NAME [form_id ...]
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.update(
    ANONYMIZED_TELEMETRY="false",
    BROWSER_USE_CLOUD_SYNC="false",
    BROWSER_USE_LOGGING_LEVEL="result",
    SKIP_LLM_API_KEY_VERIFICATION="true",
    XDG_CONFIG_HOME=str(ROOT / ".cache/config"),
    BROWSER_USE_CONFIG_DIR=str(ROOT / ".cache/config/browseruse"),
)
sys.path.insert(0, str(ROOT / "experiments/bench"))

from browser_use import Agent, BrowserProfile, ChatGoogle, ChatOpenAI  # noqa: E402
from forms import FORMS, Server, document  # noqa: E402

CHROME = ROOT / ".cache/pw/chromium-1248/chrome-linux64/chrome"
MAX_STEPS = 20
GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_MAX_REQUESTS = 18  # hard budget across the whole run; free tier is about 20 a day


gemini_requests = 0


class LoggedLLM:
    """Pass-through LLM that records each call's duration and tokens."""

    def __init__(self, llm):
        self.__dict__["_llm"] = llm
        self.__dict__["calls"] = []

    def __getattr__(self, name):
        return getattr(self._llm, name)

    def __setattr__(self, name, value):
        setattr(self._llm, name, value)

    async def ainvoke(self, messages, output_format=None, **kwargs):
        if isinstance(self._llm, ChatGoogle):
            global gemini_requests
            if gemini_requests >= GEMINI_MAX_REQUESTS:
                raise RuntimeError("Gemini request budget used up")
            gemini_requests += 1
        start = time.perf_counter()
        response = await self._llm.ainvoke(messages, output_format, **kwargs)
        usage = response.usage
        self.calls.append({
            "seconds": round(time.perf_counter() - start, 2),
            "format": getattr(output_format, "__name__", None),
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
        })
        return response


def step_records(history):
    """One record per agent step: each action and the element it targeted."""
    steps = []
    for item in history.history:
        if item.model_output is None:
            steps.append({"actions": [], "error": [r.error for r in item.result if r.error]})
            continue
        elements = item.state.interacted_element or []
        actions = []
        for i, action in enumerate(item.model_output.action):
            dumped = action.model_dump(exclude_none=True)
            name = next(iter(dumped), None)
            element = elements[i] if i < len(elements) else None
            actions.append({
                "name": name,
                "params": dumped.get(name),
                "tag": element.node_name.lower() if element else None,
                "input_type": (element.attributes or {}).get("type") if element else None,
            })
        steps.append({
            "actions": actions,
            "error": [r.error for r in item.result if r.error],
            "url": item.state.url,
            "title": item.state.title,
            "evaluation": item.model_output.evaluation_previous_goal,
            "next_goal": item.model_output.next_goal,
        })
    return steps


async def run_one(f, server, out_dir):
    url = f"http://127.0.0.1:{server.port}/{f['id']}"
    task = (
        f"Go to {url}, fill in the form using the document below, and submit it. "
        "Leave fields empty if the document has no value for them. "
        "If the form has several pages, complete all of them. Finish once the page confirms receipt.\n\n"
        f"Document:\n{document(f)}"
    )
    gemini = os.environ.get("RUN_LLM") == "gemini"
    if gemini:
        # No retries: a failed request ends the run rather than spending more quota.
        base = ChatGoogle(
            model=GEMINI_MODEL, api_key=Path.home().joinpath(".gemini_key").read_text().strip(),
            temperature=0.0, max_retries=1, retryable_status_codes=[],
        )
    else:
        base = ChatOpenAI(
            model="local", base_url="http://127.0.0.1:8007/v1", api_key="local", temperature=0.0,
            seed=int(os.environ.get("RUN_SEED", 0)),
        )
    llm = LoggedLLM(base)
    profile = BrowserProfile(
        headless=True, executable_path=str(CHROME), chromium_sandbox=False,
        user_data_dir=str(out_dir / f"profile_{f['id']}"), allowed_domains=["127.0.0.1"],
    )
    # Vision off for a text-only model; the judge off so its calls don't inflate the counts.
    agent = Agent(task=task, llm=llm, browser_profile=profile, use_vision=False, use_judge=False, max_failures=1 if gemini else 5)
    start = time.perf_counter()
    history = await agent.run(max_steps=8 if gemini else MAX_STEPS)
    record = {
        "form": f["id"], "lang": f["lang"], "pages": len(f["pages"]),
        "seconds": round(time.perf_counter() - start, 1),
        "score": server.score(f), "calls": llm.calls, "steps": step_records(history),
        "is_done": history.is_done(),
    }
    (out_dir / f"{f['id']}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1))
    score = record["score"]
    print(
        f"{f['id']:12} submitted={score['submitted']} wrong={len(score['wrong'])}/{score['fields']} "
        f"extra={len(score['extra'])} llm_calls={len(llm.calls)} steps={len(record['steps'])} {record['seconds']}s",
        flush=True,
    )


async def main():
    name, wanted = sys.argv[1], set(sys.argv[2:])
    out_dir = ROOT / "results" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    server = Server()
    for f in FORMS:
        if not wanted or f["id"] in wanted:
            await run_one(f, server, out_dir)


if __name__ == "__main__":
    asyncio.run(main())
