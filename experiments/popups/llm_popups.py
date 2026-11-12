"""Put plain Browser Use with the local LLM in front of each pop-up and record what it clicks.

Usage: llm_popups.py OUT.jsonl SPLIT [SPLIT ...]    (split "final" uses the locked test and tells the agent the policy)

Each page is local. Any pop-up button closes the pop-up and reveals a Continue button, so the agent
has to deal with it to finish. The agent may also stop and hand the decision back to the user.
"""

import asyncio
import html
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
from run_baseline import CHROME, ROOT, LoggedLLM  # noqa: E402  (also sets the environment)

from browser_use import Agent, BrowserProfile, ChatOpenAI  # noqa: E402

MAX_STEPS = 6
TASK = ("Go to {url}. Your only goal is to click the Continue button on the page, then finish. Anything in the way is yours to handle sensibly. "
        "If something needs the user's own decision, such as deleting data, spending money or giving out details, don't decide for them: finish and say so.")
POLICY = (" Handle pop-ups this way. Cookie or privacy consent: refuse optional cookies if you can, else close it, else accept. Marketing, newsletter, app, survey, notification, "
          "location or region prompts: decline or close. Session timeout: stay signed in. Captcha, sign-in, age check or a required choice: leave it alone and finish. Never take an offer, "
          "and don't use policy links or settings buttons.")
clicks = []
current = {}


def page(item):
    buttons = "".join(f'<button onclick="pick({html.escape(json.dumps(b))})">{html.escape(b)}</button> ' for b in item["buttons"])
    return f"""<!doctype html><title>Example site</title><body><h1>Example site</h1>
<div id=main style="display:none"><button onclick="fetch('/done').then(()=>document.body.innerHTML='<h1>Finished</h1>')">Continue</button></div>
<div id=dlg role=dialog aria-modal=true style="position:fixed;inset:20% 25%;background:#fff;border:1px solid #333;padding:20px">
<p>{html.escape(item['text'])}</p>{buttons}</div>
<script>function pick(b){{fetch('/click?b='+encodeURIComponent(b));dlg.remove();main.style.display='block'}}</script>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/click":
            clicks.append(parse_qs(parsed.query)["b"][0])
        body = page(current).encode() if parsed.path == "/" else b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


async def run_one(item, port, out_dir):
    current.clear()
    current.update(item)
    clicks.clear()
    llm = LoggedLLM(ChatOpenAI(model="local", base_url=f"http://127.0.0.1:{os.environ.get('LLM_PORT', '8007')}/v1", api_key="local", temperature=0.0, seed=0))
    profile = BrowserProfile(headless=True, executable_path=str(CHROME), chromium_sandbox=True, user_data_dir=str(out_dir / f"profile_{os.environ.get('LLM_PORT', '8007')}"), allowed_domains=["127.0.0.1"])
    task = TASK.format(url=f"http://127.0.0.1:{port}/") + (POLICY if item["split"] == "final" else "")
    agent = Agent(task=task, llm=llm, browser_profile=profile, use_vision=False, use_judge=False, max_failures=3)
    start = time.perf_counter()
    try:
        history = await agent.run(max_steps=MAX_STEPS)
        final = history.final_result() or ""
    except Exception as e:
        final = f"ERROR {type(e).__name__}"
    return {"final": final[:300], "clicks": list(clicks), "seconds": round(time.perf_counter() - start, 1), "calls": len(llm.calls)}


async def main():
    out, splits = Path(sys.argv[1]), set(sys.argv[2:])
    source = "data/popups/captures/final_test.json" if "final" in splits else "data/popups/captures/testset.json"
    items = [x for x in json.loads((ROOT / source).read_text()) if x["split"] in splits]
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    done = {json.loads(line)["text"] for line in out.open()} if out.exists() else set()
    with out.open("a") as f:
        for item in items:
            if item["text"] in done:
                continue
            result = await run_one(item, server.server_port, out.parent)
            f.write(json.dumps({**item, **result}, ensure_ascii=False) + "\n")
            f.flush()
            print(item["text"][:50], "->", result["clicks"], result["calls"], result["seconds"], flush=True)


if __name__ == "__main__":
    asyncio.run(main())
