"""Does the plugin read real page markup? Serves saved pages locally with scripts and network blocked, then
records the fields it sees. Usage: real_markup_check.py RAW_DIR OUT.json

No site is contacted, and whatever gets typed goes into a local copy. Saved pages are untrusted, so the
Content-Security-Policy stops all of their scripts and outside requests.
"""

import asyncio
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[2]
os.environ.update(
    ANONYMIZED_TELEMETRY="false", BROWSER_USE_CLOUD_SYNC="false", BROWSER_USE_LOGGING_LEVEL="result", SKIP_LLM_API_KEY_VERIFICATION="true",
    XDG_CONFIG_HOME=str(ROOT / ".cache/config"), BROWSER_USE_CONFIG_DIR=str(ROOT / ".cache/config/browseruse"),
)
sys.path[:0] = [str(ROOT), str(ROOT / "experiments/bench"), str(ROOT / "third_party/cua/libs/cua-s1/python/src")]

import torch  # noqa: E402
from browser_use import Agent, BrowserProfile  # noqa: E402
from browser_use.llm.views import ChatInvokeCompletion  # noqa: E402

from ultron import FastPath, install, parse_document  # noqa: E402
from ultron.fastpath import Answers  # noqa: E402

torch.set_num_threads(1)
CHROME = ROOT / ".cache/pw/chromium-1248/chrome-linux64/chrome"
DIALOGS = [ROOT / f"models/ultron-dialogs-0.1/{m}/model.safetensors" for m in "ab"]
FORMS = [str(ROOT / f"models/ultron-forms-0.1/{m}/model.safetensors") for m in "ab"]
DOCUMENT = "Applicant: Jordan Avery Reed\nContact number: 503-555-0147\nE-mail address: jordan.reed@example.com"


class StubLLM:
    model, provider, name, model_name = "stub", "stub", "stub", "stub"

    def __init__(self):
        self.asked = []

    async def ainvoke(self, messages, output_format=None, **kwargs):
        if output_format is Answers:
            self.asked.append(messages[0].content)
            return ChatInvokeCompletion(completion=Answers(answers=[]), usage=None)
        action = output_format.model_fields["action"].annotation.__args__[0](done={"text": "stub", "success": True, "files_to_display": []})
        return ChatInvokeCompletion(completion=output_format(evaluation_previous_goal="", memory="", next_goal="", action=[action]), usage=None)


def serve(root):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = root / Path(self.path).name
            body = path.read_bytes() if path.is_file() else b"not found"
            self.send_response(200 if path.is_file() else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


async def main():
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    port = serve(root)
    results = []
    for path in sorted(root.glob("*.html")):
        llm = StubLLM()
        profile = BrowserProfile(headless=True, executable_path=str(CHROME), chromium_sandbox=False, user_data_dir=None, allowed_domains=["127.0.0.1"])
        agent = Agent(task=f"Go to http://127.0.0.1:{port}/{path.name} and fill in the form.\n\nDocument:\n{DOCUMENT}", llm=llm, browser_profile=profile, use_vision=False, use_judge=False, max_failures=2)
        fast = FastPath(parse_document(DOCUMENT), FORMS, DIALOGS, form_gate=0.6)
        seen = []
        score = fast._score

        def spy(elements, score=score, seen=seen):
            seen.append([(e.role, e.label) for e, _ in elements])
            return score(elements)

        fast._score = spy
        install(agent, fast)
        try:
            await asyncio.wait_for(agent.run(max_steps=3), 60)
        except Exception as error:
            print(path.name, "failed", repr(error)[:100], flush=True)
        fields = seen[0] if seen else []
        results.append({"file": path.name, "fields": fields, "steps": [s.kind for s in fast.steps], "asked": len(llm.asked)})
        print(path.name, len(fields), "fields,", sum(not label for _, label in fields), "unnamed", [label[:24] for _, label in fields][:5], flush=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
