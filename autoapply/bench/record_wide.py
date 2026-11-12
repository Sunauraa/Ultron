"""Record the "wide" set of real pages: other ATSs (Workday, iCIMS, Oracle, SmartRecruiters, Teamtailor, Personio, Gem,
BambooHR, Jobvite) and companies' own career sites that embed an ATS form. Recorded read-only with replay.record:
pages are loaded, nothing is clicked, typed or sent. Pages chosen on 2026-11-11 from each board's public listing.

Usage: python bench/record_wide.py   (skips pages already recorded)
"""

import asyncio
import copy
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from replay import record  # noqa: E402

PAGES = HERE / "pages_wide"
URLS = {
    # Companies' own career sites, with the ATS form in an iframe
    "site_stripe": "https://stripe.com/careers/apply/abuse-investigator/8172487",
    "site_databricks": "https://databricks.com/company/careers/open-positions/job?gh_jid=8805655002",
    "site_airbnb": "https://careers.airbnb.com/positions/8365363?gh_jid=8365363",
    "site_coinbase": "https://www.coinbase.com/careers/positions/8175363?gh_jid=8175363",  # Cloudflare bot check
    # Other ATSs with a public form
    "teamtailor_teamtailor": "https://career.teamtailor.com/jobs/8694933-smb-account-executive/applications/new",
    "personio_f24": "https://f24.jobs.personio.de/job/1316737/apply?display=en",
    "gem_gem": "https://jobs.gem.com/gem/am9icG9zdDoxt66pB6mvVDH0kCIS4bLF",
    "bamboohr_onezero": "https://onezero.bamboohr.com/careers/316",
    "jobvite_nutanix": "https://jobs.jobvite.com/nutanix/job/oncCAfwv/apply",
    # Account, sign-in or bot walls
    "workday_nvidia": "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/Switzerland-Zurich/GPU-Compiler-Intern_JR2029779/apply",
    "workday_nvidia_manual": "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/Switzerland-Zurich/GPU-Compiler-Intern_JR2029779/apply/applyManually",
    "icims_nasco": "https://careers-nasco.icims.com/jobs/4416/senior-cloud-operations-engineer/login",
    "oracle_jpmc": "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/210594721/apply/email",
    "smartrecruiters_bosch": "https://jobs.smartrecruiters.com/oneclick-ui/company/BoschGroup/publication/515358fc-8f57-4148-9c5f-38a22066676b?dcr_ci=BoschGroup",
}

# Data a form asks for only after a click (recording clicks nothing), fetched afterwards with a plain GET and added to
# the recording: BambooHR loads its Country and State lists when "Apply for This Job" opens the form.
LATER_GETS = {
    "bamboohr_onezero": ["https://onezero.bamboohr.com/ajax/get_countries", "https://onezero.bamboohr.com/ajax/get_states?country=1"],
}


def add_gets(out: Path, urls: list[str]) -> None:
    har_path = out / "page.har"
    har = json.loads(har_path.read_text())
    have = {e["request"]["url"] for e in har["log"]["entries"]}
    template = next(e for e in har["log"]["entries"] if e["request"]["method"] == "GET" and e["response"]["status"] == 200)
    for url in urls:
        if url in have:
            continue
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
        with urllib.request.urlopen(request, timeout=30) as response:
            body, kind = response.read().decode(), response.headers.get("Content-Type", "application/json")
        entry = copy.deepcopy(template)
        entry["request"].update(url=url, headers=[], queryString=[], cookies=[])
        entry["response"].update(status=200, statusText="OK", headers=[{"name": "Content-Type", "value": kind}], cookies=[],
                                 content={"size": len(body), "mimeType": kind, "text": body}, redirectURL="")
        har["log"]["entries"].append(entry)
        print(f"{out.name}: added {url}")
    har_path.write_text(json.dumps(har))


async def main() -> None:
    for name, url in URLS.items():
        out = PAGES / name
        if (out / "page.har").exists():
            continue
        try:
            await record(url, out)
            print(f"{name}: {(out / 'page.har').stat().st_size // 1024} KB")
        except Exception as error:
            print(f"{name}: recording failed ({error})")
    for name, urls in LATER_GETS.items():
        add_gets(PAGES / name, urls)


if __name__ == "__main__":
    asyncio.run(main())
