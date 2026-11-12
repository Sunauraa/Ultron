"""Stand-in for `claude -p` in run.sh, driven by a local model (OpenAI-compatible server at LLM_URL).

Takes the flags run.sh passes: -p PROMPT, --mcp-config FILE, --max-turns N (the rest are accepted and ignored:
the stand-in only ever exposes the MCP servers' tools, which is what --allowedTools mcp__ultron plus the
disallowed list give Claude Code). Starts each MCP server from the config the way Claude Code does (inherited
environment), runs the tool loop (one tool call per turn, as in the benchmark) and prints a JSON result, with the
whole transcript, to stdout (run.sh saves it as the job's log).
"""

import argparse
import asyncio
import json
import os
import sys
import time

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from openai import AsyncOpenAI


async def main(args) -> dict:
    servers = json.loads(open(args.mcp_config).read())["mcpServers"]
    name, server = next(iter(servers.items()))
    params = StdioServerParameters(command=server["command"], args=server.get("args", []), env=dict(os.environ))
    llm = AsyncOpenAI(base_url=os.environ["LLM_URL"], api_key="local", timeout=600)
    messages, actions, stop, final, start = [{"role": "user", "content": args.p}], [], "max_turns", "", time.time()
    async with stdio_client(params) as (read, write), ClientSession(read, write) as mcp:
        await mcp.initialize()
        tools = [{"type": "function", "function": {"name": f"mcp__{name}__{t.name}", "description": t.description or "",
                                                   "parameters": t.input_schema}} for t in (await mcp.list_tools()).tools]
        for turn in range(args.max_turns):
            try:
                reply = await llm.chat.completions.create(model="local", messages=messages, tools=tools, temperature=0.7, max_tokens=2048,
                                                          seed=int(os.environ.get("E2E_SEED", "1")) * 1000 + turn,
                                                          extra_body={"chat_template_kwargs": {"enable_thinking": False}})
            except Exception as error:
                stop = f"llm_error: {str(error)[:300]}"
                break
            message = reply.choices[0].message
            messages.append(message.model_dump(exclude_none=True))
            if not message.tool_calls:
                final, stop = message.content or "", "done"
                break
            for number, call in enumerate(message.tool_calls):
                if number:
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": "Not run: one tool call at a time."})
                    continue
                tool = call.function.name.removeprefix(f"mcp__{name}__")
                try:
                    result = await asyncio.wait_for(mcp.call_tool(tool, json.loads(call.function.arguments or "{}")), 180)
                    output = "\n".join(c.text for c in result.content if c.type == "text")
                except Exception as error:
                    output = f"ERROR: {type(error).__name__}: {str(error)[:500]}"
                actions.append({"tool": tool, "args": call.function.arguments, "output": output[:4000]})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
    return {"type": "result", "subtype": stop, "result": final, "num_turns": len(actions), "duration_s": round(time.time() - start, 1),
            "actions": actions}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p")
    parser.add_argument("--mcp-config")
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--output-format")
    parser.add_argument("--strict-mcp-config", action="store_true")
    parser.add_argument("--allowedTools")
    parser.add_argument("--disallowedTools")
    print(json.dumps(asyncio.run(main(parser.parse_args())), indent=1))
    sys.stdout.flush()
