"""Real-page benchmark: the same local model applies on the 21 recorded real application pages (bench/pages, replayed
offline by replay.py: real HTML and scripts, nothing reaches the real site) through Playwright MCP or through Ultron MCP.
Both arms drive the same replay browser over CDP, as they drive the user's Chrome in real use.

Scored on what the page actually sends (the request the employer would receive), decoded per platform (score.py) and
compared with the gold answers (gold.py, written from the persona and the platforms' own form definitions).

Usage: python bench/realbench.py OUT_DIR SEEDS [NAME ...]    LLM_URL as in bench.py
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bench  # noqa: E402
import score  # noqa: E402
from mcp.client.stdio import StdioServerParameters  # noqa: E402
from replay import Replay  # noqa: E402

PERSONA = HERE / "persona"
WORKERS = 4
PAGES = sorted(p.name for p in (HERE / "pages").iterdir() if p.name != "ashby_cursor")  # cursor's hosted page is gone (404)


def document() -> str:
    """The persona's facts as the Playwright arm gets them: answers.md, the resume's text and where the resume file is."""
    from pypdf import PdfReader
    resume = " ".join(" ".join(p.extract_text() or "" for p in PdfReader(PERSONA / "resume.pdf").pages).split())
    return ((PERSONA / "answers.md").read_text().strip() + "\n\nMy resume (text):\n" + resume
            + "\n\nMy resume file, to upload where the form asks for a resume or CV: resume.pdf (in the current folder: {resume})")


def prepare(arm: str, work: Path) -> None:
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    shutil.copy(PERSONA / "resume.pdf", work / "resume.pdf")
    if arm == "ultron":
        shutil.copy(PERSONA / "answers.md", work / "answers.md")
        (work / "config.toml").write_text(
            '[apply]\nauto_submit = true\nauto_submit_written_answers = true\nresume = "resume.pdf"\n'
            'answers = "answers.md"\nbrowser_profile = "profile"\nheadless = true\nblocked_sites = []\n')


def params(arm: str, work: Path, port: int) -> StdioServerParameters:
    env = {"PATH": os.environ["PATH"], "HOME": str(work), "PLAYWRIGHT_BROWSERS_PATH": str(bench.PW)}
    if arm == "playwright":
        return StdioServerParameters(command=str(bench.NODE), env=env, cwd=str(work), args=[
            str(bench.PW_MCP), "--cdp-endpoint", f"http://127.0.0.1:{port}", "--output-dir", str(work / "out")])
    env["ULTRON_CDP"] = f"http://127.0.0.1:{port}"
    return StdioServerParameters(command=sys.executable, env=env, cwd=str(work), args=[str(bench.CODE / "ultron_mcp.py"), str(work)])


async def run_one(llm, arm: str, name: str, seed: int, work: Path, port: int) -> dict:
    folder = HERE / "pages" / name
    meta = json.loads((folder / "meta.json").read_text())
    async with Replay(folder, port, work.parent / f"{work.name}_browser" / "profile") as replay:
        prepare(arm, work)
        if arm == "playwright":
            prompt = bench.PLAYWRIGHT_PROMPT.format(document=document().format(resume=work / "resume.pdf"), url=replay.url)
        else:
            prompt = (bench.CODE / "prompt.md").read_text() + f"\n\nJob: {meta.get('title', '')} at {meta.get('company', '')}\nURL: {replay.url}"
        result = await episode(llm, arm, prompt, seed, work, port)
        await asyncio.sleep(2)  # let a submission still in flight reach the router
        sent = list(replay.sent)
    result.update(page=name, arm=arm, seed=seed, sent=sent, score=score.score(name, sent))
    result["correct"] = result["score"]["correct"]
    result["held_by_default"] = arm == "ultron" and result["score"]["submitted"] and any("written by you" in a["output"] for a in result["actions"])
    return result


async def episode(llm, arm: str, prompt: str, seed: int, work: Path, port: int) -> dict:
    """bench.episode's loop (same model settings, one tool call per message), with this harness's prompt and server."""
    calls, actions, stop, final = [], [], "max_calls", ""
    start = time.perf_counter()
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client
    async with stdio_client(params(arm, work, port)) as (read, write), ClientSession(read, write) as mcp:
        await mcp.initialize()
        tools = [{"type": "function", "function": {"name": t.name, "description": t.description or "", "parameters": t.input_schema}}
                 for t in (await mcp.list_tools()).tools]
        messages = [{"role": "user", "content": prompt}]
        for _ in range(bench.MAX_CALLS):
            try:
                reply = await llm.chat.completions.create(model="local", messages=messages, tools=tools, temperature=bench.TEMPERATURE,
                                                          max_tokens=bench.MAX_TOKENS, seed=seed * 1000 + len(calls))
            except Exception as error:
                stop = f"llm_error: {str(error)[:300]}"
                break
            calls.append({"prompt_tokens": reply.usage.prompt_tokens, "completion_tokens": reply.usage.completion_tokens})
            message = reply.choices[0].message
            messages.append(message.model_dump(exclude_none=True))
            if not message.tool_calls:
                final, stop = message.content or "", "done"
                break
            for number, call in enumerate(message.tool_calls):
                if number:
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": "Not run: one tool call at a time. Call it again if it is still needed after reading the result above."})
                    actions.append({"tool": call.function.name, "args": call.function.arguments, "chars": 0, "output": "NOT RUN"})
                    continue
                try:
                    args = json.loads(call.function.arguments or "{}")
                    output = bench.text_of(await asyncio.wait_for(mcp.call_tool(call.function.name, args), 120))
                except Exception as error:
                    output = f"ERROR: {type(error).__name__}: {str(error)[:500]}"
                actions.append({"tool": call.function.name, "args": call.function.arguments, "chars": len(output), "output": output[:3000]})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
    return {"calls": calls, "actions": actions, "stop": stop, "final": final, "seconds": round(time.perf_counter() - start, 1),
            "tool_count": len(tools), "tool_schema_chars": len(json.dumps(tools))}


async def main(out: Path, seeds: list[int], names: list[str], arms: list[str]) -> None:
    from openai import AsyncOpenAI
    out.mkdir(parents=True, exist_ok=True)
    bench.CODE = (out / "code").resolve()
    if not bench.CODE.exists():
        bench.CODE.mkdir()
        for name in bench.CODE_FILES:
            source = bench.AUTOAPPLY / name
            (shutil.copytree if source.is_dir() else shutil.copy2)(source, bench.CODE / name)
    work_root = bench.ROOT / "tmp" / "realbench_work" / out.resolve().name
    jobs = [(arm, name, seed) for seed in seeds for name in names for arm in arms
            if not (out / f"{arm}_{name}_s{seed}.json").exists()]
    random.Random(0).shuffle(jobs)
    llm = AsyncOpenAI(base_url=bench.LLM_URL, api_key="local", timeout=600)
    queue = asyncio.Queue()
    for job in jobs:
        queue.put_nowait(job)
    base_port = int(os.environ.get("REALBENCH_PORT", "9500"))

    async def worker(number: int) -> None:
        while not queue.empty():
            arm, name, seed = queue.get_nowait()
            try:
                result = await run_one(llm, arm, name, seed, work_root / f"w{number}", base_port + number)
            except Exception as error:
                result = {"page": name, "arm": arm, "seed": seed, "calls": [], "actions": [], "sent": [], "seconds": 0,
                          "stop": f"harness_error: {type(error).__name__}: {error}", "score": score.score(name, []), "correct": None}
            (out / f"{arm}_{name}_s{seed}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
            s = result["score"]
            print(f"{arm:10} {name:22} s{seed} correct={result['correct']!s:5} sent={s['submitted']!s:5} wrong={len(s['wrong'])} "
                  f"calls={len(result['calls']):2} stop={result['stop'][:50]}", flush=True)

    await asyncio.gather(*(worker(i) for i in range(WORKERS)))


if __name__ == "__main__":
    arms = os.environ.get("ARMS", "playwright,ultron").split(",")
    asyncio.run(main(Path(sys.argv[1]), [int(s) for s in sys.argv[2].split(",")], sys.argv[3:] or PAGES, arms))
