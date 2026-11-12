"""Record the real application pages of the benchmark: each company's newest posting, chosen by rule (no picking
by hand), fetched through fetch.py's own code and recorded read-only with replay.record.

Usage: python bench/build_pages.py   (skips pages already recorded)
"""

import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from fetch import postings  # noqa: E402
from replay import record  # noqa: E402

COMPANIES = {
    "greenhouse": ["anthropic", "stripe", "figma", "discord", "databricks", "cloudflare", "airbnb", "dropbox"],
    "lever": ["palantir", "spotify", "zoox"],
    "ashby": ["openai", "notion", "linear", "ramp", "cursor", "supabase"],  # cursor: its hosted pages are off (404), kept as a dead-link case
    "workable": ["huggingface", "skroutz", "blueground"],
    "recruitee": ["channable", "personio"],
}
PAGES = HERE / "pages"


async def main() -> None:
    for platform, companies in COMPANIES.items():
        for company in companies:
            out = PAGES / f"{platform}_{company}"
            if (out / "page.har").exists():
                continue
            jobs = sorted(postings(platform, company), key=lambda j: (str(j["posted"]), str(j["id"])), reverse=True)
            if not jobs:
                print(f"{platform} {company}: no postings")
                continue
            job = jobs[0]
            try:
                await record(job["url"], out)
            except Exception as error:
                print(f"{platform} {company}: recording failed ({error})")
                continue
            meta = json.loads((out / "meta.json").read_text())
            (out / "meta.json").write_text(json.dumps({**meta, **{k: job[k] for k in ("platform", "company", "title", "location", "posted", "id")}}, indent=1, default=str))
            print(f"{platform} {company}: {job['title']} -> {(out / 'page.har').stat().st_size // 1024} KB")


if __name__ == "__main__":
    asyncio.run(main())
