"""Open every recorded page offline through Ultron (over CDP, as in real use) and print what Ultron reads.
Nothing is filled or sent (ULTRON_READ_ONLY=1). Used to check the replays and Ultron's reading of each platform.
With --fill, open_job also pre-fills from the persona's answers.md and resume (offline; nothing is submitted).

Usage: python bench/check_pages.py [--fill] [NAME or FOLDER ...]   (default: every page in bench/pages)
"""

import asyncio
import os
import shutil
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from replay import Replay  # noqa: E402

WORK = HERE.parent.parent / "tmp" / "check_pages"


FILL = "--fill" in sys.argv


async def check(folder: Path, port: int) -> None:
    work = WORK / folder.name
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    (work / "config.toml").write_text('[apply]\nauto_submit = false\nblocked_sites = []\n'
                                      + (f'[cover_letter]\nwrite = "{os.environ.get("COVER", "required")}"\n' if FILL else ""))
    persona = HERE / "persona"
    (work / "answers.md").write_text((persona / "answers.md").read_text() if FILL else "")
    if FILL:
        shutil.copy(persona / "resume.pdf", work / "resume.pdf")
    async with Replay(folder, port, work / "profile") as replay:
        env = {**{k: os.environ[k] for k in ("PATH", "PLAYWRIGHT_BROWSERS_PATH")}, "HOME": str(work),
               "ULTRON_CDP": f"http://127.0.0.1:{port}", "ULTRON_READ_ONLY": "0" if FILL else "1"}
        params = StdioServerParameters(command=sys.executable, args=[str(HERE.parent / "ultron_mcp.py"), str(work)], env=env)
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("open_job", {"url": replay.url})
            text = "\n".join(c.text for c in result.content if c.type == "text")
        print(f"===== {folder.name}  ({len(text)} chars, {len(replay.missing)} requests not in the recording)\n{text}\n")


async def main(names: list[str]) -> None:
    folders = [Path(n) if "/" in n else HERE / "pages" / n for n in names] if names else sorted((HERE / "pages").iterdir())
    for number, folder in enumerate(folders):
        try:
            await check(folder, 9400 + number)
        except Exception as error:
            print(f"===== {folder.name}: FAILED {type(error).__name__}: {error}\n")


if __name__ == "__main__":
    asyncio.run(main([a for a in sys.argv[1:] if a != "--fill"]))
