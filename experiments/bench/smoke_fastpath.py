"""Run the fast path in a real browser with a stub LLM that only says done. Usage: smoke_fastpath.py FORMS_CKPT [form_id ...]

Not an evaluation. It shows how far the fast path gets alone, and that it never needs the LLM's help
to stay on the rails: anything it leaves undone shows up as a wrong or unsubmitted field.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.update(
    ANONYMIZED_TELEMETRY="false", BROWSER_USE_CLOUD_SYNC="false", BROWSER_USE_LOGGING_LEVEL="result", SKIP_LLM_API_KEY_VERIFICATION="true",
    XDG_CONFIG_HOME=str(ROOT / ".cache/config"), BROWSER_USE_CONFIG_DIR=str(ROOT / ".cache/config/browseruse"),
)
sys.path[:0] = [str(ROOT), str(ROOT / "experiments/bench"), str(ROOT / "third_party/cua/libs/cua-s1/python/src")]

import torch  # noqa: E402

torch.set_num_threads(1)

from browser_use import Agent, BrowserProfile  # noqa: E402
from browser_use.llm.views import ChatInvokeCompletion  # noqa: E402
from forms import FORMS, Server, document  # noqa: E402

from ultron import FastPath, install, parse_document  # noqa: E402

CHROME = ROOT / ".cache/pw/chromium-1248/chrome-linux64/chrome"
DIALOGS = [ROOT / f"models/ultron-dialogs-0.1/{m}/model.safetensors" for m in "ab"]


class StubLLM:
    model, provider, name, model_name = "stub", "stub", "stub", "stub"

    def __init__(self):
        self.calls = 0

    async def ainvoke(self, messages, output_format=None, **kwargs):
        self.calls += 1
        action = output_format.model_fields["action"].annotation.__args__[0](done={"text": "stub", "success": True, "files_to_display": []})
        return ChatInvokeCompletion(completion=output_format(evaluation_previous_goal="", memory="", next_goal="", action=[action]), usage=None)


async def main():
    forms_checkpoint, wanted = sys.argv[1], set(sys.argv[2:])
    server = Server()
    for f in FORMS:
        if wanted and f["id"] not in wanted:
            continue
        llm = StubLLM()
        profile = BrowserProfile(headless=True, executable_path=str(CHROME), chromium_sandbox=False, allowed_domains=["127.0.0.1"], user_data_dir=None)
        url = f"http://127.0.0.1:{server.port}/{f['id']}"
        agent = Agent(task=f"Go to {url}, fill in the form using the document below, and submit it.\n\nDocument:\n{document(f)}", llm=llm, browser_profile=profile, use_vision=False, use_judge=False, max_failures=2)
        fast = install(agent, FastPath(parse_document(document(f)), [forms_checkpoint], DIALOGS))
        start = time.perf_counter()
        await agent.run(max_steps=12)
        score = server.score(f)
        kinds = [s.kind for s in fast.steps]
        print(f"{f['id']:12} submitted={score['submitted']} wrong={score['wrong']} extra={score['extra']} steps={kinds} {time.perf_counter() - start:.1f}s", flush=True)
        for s in fast.steps:
            print(f"   {s.kind:6} {s.milliseconds:7.1f} ms {s.goal}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
