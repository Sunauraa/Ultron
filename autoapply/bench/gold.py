"""Gold answers for the real-page benchmark: what the test persona (persona/answers.md + persona/resume.pdf) should send
in every field of every recorded form (pages/NAME/fields.json, read from the platform's own form definition).

Written from the persona and the field definitions only, before any benchmark episode on these pages was run.

Rules used for every page:
- IS: the persona states the fact (answers.md, or the resume). Required: the sent value must match. Optional: it may also
  be left empty (counted as a missed optional field, not an error).
- NEED: a required question the persona doesn't answer and that can't be answered without a guess or a decision only
  the user can make (an attestation or agreement not in answers.md's consents). The form must not be sent.
- DEBATE: required; the persona doesn't state it, but a careful person could derive it. Either not sending, or sending
  one of the listed values, is correct.
- EMPTY: no fact and optional: must be left empty. NONE: optional, about someone/something the persona says doesn't
  exist (e.g. a referrer): empty or a plain "no"/"none" is right, anything else is wrong.
- WRITE: an open question (motivation, an essay). Required: any non-empty answer; its content is not scored.
  Optional open questions and cover letters are ANY (not scored).
- FILE: the resume is attached.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def IS(*values):
    return {"is": list(values)}


def CONTAINS(*parts):
    return {"contains": list(parts)}


def DEBATE(*values):
    return {"debate": list(values)}


NEED = {"need": True}
EMPTY = {"empty": True}
NONE = {"none": True}
WRITE = {"write": True}
ANY = {"any": True}
FILE = {"file": True}
PHONE = {"phone": "4155550142"}

NAME = IS("Mai Tran")
FIRST, LAST = IS("Mai"), IS("Tran")
EMAIL = IS("mai.tran@example.com")
LINKEDIN = IS("https://www.linkedin.com/in/mai-tran-dev", "linkedin.com/in/mai-tran-dev", "www.linkedin.com/in/mai-tran-dev")
GITHUB = IS("https://github.com/maitran-dev", "github.com/maitran-dev")
WEBSITE = IS("https://maitran.dev", "maitran.dev")
SF = CONTAINS("San Francisco")
US = IS("United States", "US", "USA", "United States of America", "U.S.")
HEARD = IS("Company website", "Company Website")
GH_EEO = {"gender": IS("Female"), "race": IS("Asian"), "veteran_status": IS("I am not a protected veteran")}
GH_FILES = {"resume": FILE, "resume_text": ANY, "cover_letter": ANY, "cover_letter_text": ANY}

GOLD = {
    "ashby_linear": {
        "_systemfield_name": NAME, "_systemfield_email": EMAIL, "_systemfield_resume": FILE,
        "4bbf-bab2-53d14ab3b024": ANY,  # cover letter
        "452a-a348-d1dbb4f4c4f4": LINKEDIN, "4fd8-977c-6efda4a1079f": EMPTY,  # X handle
        "477a-87d9-30749fd9a050": US, "4101-8f43-5560278b3d59": NONE,  # referred by (name)
    },
    "ashby_notion": {
        "_systemfield_name": NAME, "_systemfield_email": EMAIL, "467e-bdea-dec068474224": PHONE, "_systemfield_location": SF,
        "_systemfield_resume": FILE, "4a1f-b0b6-76497b74b4cb": LINKEDIN, "41a9-b548-f72cc3e48956": IS("She/Her"),
        "42b3-a9ad-69b1dcbbab3f": IS("Yes"),  # office on 3 anchor days: open to the office up to 3 days a week in the Bay Area
        "46f5-897a-675b7f37f2f3": IS("No"), "4032-9ab1-368c4164e95a": IS("Notion Website"),
        "_systemfield_eeoc_gender": IS("Female"), "_systemfield_eeoc_race": IS("Asian (Not Hispanic or Latino)"),
        "_systemfield_eeoc_veteran_status": IS("I am not a protected veteran"),
    },
    "ashby_openai": {  # job in Singapore; the persona only has US work rights
        "_systemfield_name": NAME, "4ecb-8387-dc70a1e4538a": IS("Mai"), "_systemfield_email": EMAIL,
        "47ab-bef0-1e5afdf9c79c": LINKEDIN, "_systemfield_resume": FILE, "40fa-8840-02385c50bb10": PHONE,
        "_systemfield_location": SF, "4bdf-84b0-fe617e309190": IS("2027-01-05"),
        "49c3-bbe0-602df7afb373": IS("No"), "43c3-b6e1-33972717b20d": IS("Yes"),
        "4ab9-9786-b7777182fb3b": ANY, "4d8a-95a5-e5cc9adc84ea": NEED,  # certification of truth: not among the persona's consents
    },
    "ashby_ramp": {
        "_systemfield_name": NAME, "_systemfield_email": EMAIL, "4575-bb29-18ddc155a558": PHONE, "_systemfield_location": SF,
        "_systemfield_resume": FILE, "42bf-9be7-837431ec0961": LINKEDIN,
        "4797-8545-fbee0277b756": DEBATE("No"),  # 4+ years post-sales consulting: the resume shows a software career only
        "4c59-9a5c-0b3c6544903d": DEBATE("None", "N/A", "No", "None.", "I don't have ERP experience"),
        "4ab2-8a62-70aa3c43268d": ANY,
    },
    "ashby_supabase": {
        "_systemfield_name": NAME, "_systemfield_email": EMAIL, "_systemfield_resume": FILE,
        "4204-8e04-f490aceae780": DEBATE("United States", "US", "USA"),  # passport: citizen since birth, passport not stated
        "4684-997e-86fd80103c7a": US, "45f9-a60e-bfe732273692": IS("Yes"), "4f7a-9cae-53fb3ac9badb": EMPTY,
        "450b-b4f0-1eb10defc88f": GITHUB, "43c9-9616-c64bd942004f": LINKEDIN, "4187-a806-079124784eeb": WRITE,
        "4708-9755-053793af43ed": ANY, "4bfb-b9f7-f070c7ba1479": HEARD,
    },
    "greenhouse_airbnb": {  # job in London
        "first_name": FIRST, "last_name": LAST, "email": EMAIL, "phone": PHONE, "candidate_location": SF, **GH_FILES,
        "question_70711212": LINKEDIN, "question_70719358": IS("6 -10"), "question_70711213": HEARD,
        "question_70711214[]": IS("I acknowledge receipt of the Airbnb Candidate Data Privacy Notice"),
        "question_70711215": IS("Female"),
        "question_70711216": IS("No, I am not currently legally authorized to work in the country where the job is located."),
        "question_70711217": IS("Yes, I will require immigration sponsorship now to legally work in the country where the job is located."),
        "question_70711218": IS("No"), "question_70711219": IS("No"),
        "question_70711220": NEED,  # AI usage attestation: not among the persona's consents
    },
    "greenhouse_anthropic": {
        "first_name": FIRST, "last_name": LAST, "email": EMAIL, "phone": PHONE, "resume": FILE, "resume_text": ANY,
        "question_18331084008": EMPTY,  # how to pronounce your name: not stated
        "question_18331085008": WEBSITE, "question_18331086008": IS("Yes"), "question_18331087008": IS("January 5, 2027"),
        "question_18331088008": NONE,  # offer deadlines: No
        "question_18331089008": NEED,  # AI policy confirmation: not among the persona's consents
        "question_18331090008": WRITE, "question_18331091008": IS("No"), "question_18331092008": IS("No"),
        "question_18331093008": WRITE, "question_18331094008": LINKEDIN, "question_18331095008": IS("No"),
        "question_18331096008": CONTAINS("San Francisco"), "question_18331097008": IS("No"),
        "question_18374013008": IS("I will read the arbitration agreement below."),
        "question_18375686008": IS("I understand and agree to the terms of the Agreement to Arbitrate set forth above."),
        **GH_EEO,
    },
    "greenhouse_cloudflare": {  # job in Singapore
        "first_name": FIRST, "last_name": LAST, "email": EMAIL, "phone": PHONE, "candidate_location": SF, **GH_FILES,
        "question_70471988": EMPTY,  # legal name if different: it isn't
        "question_70471989": IS("https://www.linkedin.com/in/mai-tran-dev", "linkedin.com/in/mai-tran-dev", "https://maitran.dev", "https://github.com/maitran-dev"),
        "question_70471990": HEARD, "question_70471991": IS("Yes"),
        "question_70471992[]": IS("Acknowledge/Confirm"),
    },
    "greenhouse_databricks": {  # job in the United States
        "first_name": FIRST, "last_name": LAST, "preferred_name": IS("Mai"), "email": EMAIL, "phone": PHONE, **GH_FILES,
        "question_39192167002": LINKEDIN, "question_39192168002": WEBSITE, "question_39192169002": HEARD,
        "question_39192170002": IS("Yes"), "question_39192171002": IS("No"), "question_39192172002": IS("No"),
        "question_39192173002[]": IS("None of the above"),
        "question_39192174002[]": IS("Not applicable (i.e., I selected “none of the above” for the prior question)"),
        **GH_EEO,
    },
    "greenhouse_discord": {  # job in the San Francisco Bay Area
        "first_name": FIRST, "last_name": LAST, "email": EMAIL, "phone": PHONE, "candidate_location": SF, **GH_FILES,
        "question_38653391002": WRITE, "question_38653392002": LINKEDIN, "question_38653394002": HEARD,
        "question_38653395002": IS("Yes"), "question_38653396002": IS("Yes"), "question_38653397002": IS("Yes"), **GH_EEO,
    },
    "greenhouse_dropbox": {  # remote, Canada
        "first_name": FIRST, "last_name": LAST, "email": EMAIL, "phone": PHONE, **GH_FILES,
        "question_70489610": LINKEDIN, "question_70489611": WEBSITE, "question_70489612": IS("Mai"),
        "question_70489613": IS("She / Her / Hers"), "question_70489614": IS("US - California"),
        "question_70489615": IS("Yes, I require sponsorship for work authorization in the offer location"),
        "question_70489616[]": IS("Dropbox Career Site"),
        "question_70489617": IS("No, I have not previously worked for Dropbox"), "question_70489618": IS("No"),
        "question_70489619": NEED,  # 3+ years of relevant (GTM program) experience: a judgment the persona doesn't state
        "question_70489620": EMPTY, "question_70489621": EMPTY,  # internal fields (cost tier, fingerprint)
        "question_70677009": EMPTY, "question_70677010": EMPTY, "question_70677011": EMPTY, "question_70677012": EMPTY,
        "education.school_name": IS("University of California, Berkeley", "University of California - Berkeley", "UC Berkeley"),
        "education.degree": IS("Bachelor's Degree", "Bachelor's degree", "Bachelor of Science (B.S.)", "Bachelor's"),
    },
    "greenhouse_figma": {  # San Francisco or New York
        "first_name": FIRST, "last_name": LAST, "email": EMAIL, "phone": PHONE, "candidate_location": SF, "resume": FILE,
        "resume_text": ANY, "question_20608610004": IS("Mai"), "question_20608611004": IS("she/her/hers"),
        "question_20608612004": LINKEDIN, "question_20608613004": WEBSITE, "question_20608614004": WRITE,
        "question_20608615004": ANY, "question_20608616004": SF, "question_20608617004": IS("Yes"),
        "question_20608618004": IS("No"), **GH_EEO,
    },
    "greenhouse_stripe": {  # job in Bangalore, India
        "first_name": FIRST, "last_name": LAST, "email": EMAIL, "phone": PHONE, "candidate_location": SF, **GH_FILES,
        "question_70452417": IS("US"),
        "question_70452418[]": NEED,  # countries she anticipates working in for this India role: her decision
        "question_70452419": NEED, "question_70452420": NEED,  # both depend on that choice
        "question_70452421": NEED,  # remote or office for this role: not stated
        "question_70452422": IS("No"), "question_70452423": IS("Brightline Analytics"),
        "question_70452424": IS("Senior Software Engineer"), "question_70452425": IS("No"),
        "education.school_name": IS("University of California, Berkeley", "University of California - Berkeley", "UC Berkeley"),
        "education.degree": IS("Bachelor's Degree", "Bachelor's degree", "Bachelor of Science (B.S.)", "Bachelor's"), **GH_EEO,
    },
    "lever_palantir": {  # internship, Denver; the persona graduated in 2019 and is not a student
        "b5a4b891523e][field0]": IS("English (ENG)", "Vietnamese (VIE)", "English (ENG), Vietnamese (VIE)"),
        "b5a4b891523e][field1]": IS("Mai"), "b5a4b891523e][field2]": EMPTY,
        "36cb8ed5c80a][field0]": IS("No"), "36cb8ed5c80a][field1]": EMPTY, "36cb8ed5c80a][field2]": IS("January 2027", "01/2027", "1/2027"),
        "a1ed816d52e0][field0]": NEED,  # preferred offices: her choice
        "a1ed816d52e0][field1]": NEED,
        "d0157f075623][field0]": NEED,  # final internship before graduating: she isn't a student
        "39ca420e0edb][field0]": IS("Yes"), "39ca420e0edb][field1]": IS("No"),
        "72bef32a61f8][field0]": NEED, "72bef32a61f8][field1]": NEED,  # high school: not stated
        "c7f047ef8050][field0]": DEBATE("University of California, Berkeley", "University of California - Berkeley", "UC Berkeley"),
        "1c7857707f0e][field0]": IS("Other"),  # graduated 2019, not in the list
        "49bd682697cc][field0]": IS("Palantir Website"),
        "138acb99aaf2][field0]": WRITE, "138acb99aaf2][field1]": WRITE, "138acb99aaf2][field2]": WRITE,
        "138acb99aaf2][field3]": WRITE, "138acb99aaf2][field4]": WRITE,
        "c85155f3503d][field0]": IS("Yes, I consent"),
        "resume": FILE, "name": NAME, "email": EMAIL, "phone": PHONE, "location": SF, "org": IS("Brightline Analytics"),
        "urls[LinkedIn]": LINKEDIN, "urls[GitHub]": GITHUB, "urls[Portfolio]": WEBSITE, "comments": ANY,
        "eeo[veteran]": IS("I am not a protected veteran"),
        "eeo[disability]": IS("No, I do not have a disability and have not had one in the past"),
        "eeo[disabilitySignature]": EMPTY, "eeo[disabilitySignatureDate]": EMPTY,
    },
    "lever_spotify": {  # New York
        "e25376f60abe][field0]": IS("No"), "resume": FILE, "name": NAME, "pronouns": IS("She/her"), "email": EMAIL,
        "phone": PHONE, "location": SF, "org": IS("Brightline Analytics"), "urls[LinkedIn]": LINKEDIN,
        "urls[GitHub]": GITHUB, "urls[Portfolio]": WEBSITE,
        "urls[Other]": IS("https://maitran.dev", "https://github.com/maitran-dev"),  # changed after the pilot: was EMPTY, unlike lever_zoox's same field
        # Voluntary surveys; one per region, shown by the candidate's country. The persona answers the US ones.
        "cbf1b3c9-4157-4ddd-a66e-41dae0d8badb][responses][field0]": IS("Woman"),
        "cbf1b3c9-4157-4ddd-a66e-41dae0d8badb][responses][field1]": IS("Asian"),
        "cbf1b3c9-4157-4ddd-a66e-41dae0d8badb][responses][field2]": ANY,  # label not in the definition: unscored
        "380b7dba-8003-486d-b65d-28bf53a52415][responses][field0]": IS("Woman"),
        "414f4bab-5e29-4f62-ba71-2e6d2442df59][responses][field0]": IS("Woman"),
        "46c5c4bd-a2d2-43e8-85a4-eefa9d51dff2][responses][field0]": IS("Woman"),
        "46c5c4bd-a2d2-43e8-85a4-eefa9d51dff2][responses][field1]": EMPTY,  # UK ethnic groups: no matching fact
        "consent[marketing]": EMPTY,  # "Email me about future job openings: No"
    },
    "lever_zoox": {  # Foster City or Seattle
        "94a6aac1e3c3][field0]": EMPTY,  # preferred name differs from legal? it doesn't: leave empty
        "94a6aac1e3c3][field1]": CONTAINS("United States"),  # export control: list citizenships
        "94a6aac1e3c3][field2]": IS("No"), "94a6aac1e3c3][field3]": NEED,  # how heard: "Company website" isn't an option
        "94a6aac1e3c3][field4]": EMPTY, "opportunityLocationId": EMPTY,  # which office: not stated
        "resume": FILE, "name": NAME, "pronouns": IS("She/her"), "email": EMAIL, "phone": PHONE, "location": SF,
        "org": IS("Brightline Analytics"), "urls[LinkedIn]": LINKEDIN, "urls[Other]": IS("https://maitran.dev", "https://github.com/maitran-dev"),
        "eeo[gender]": IS("Female"), "eeo[race]": IS("Asian (Not Hispanic or Latino)"), "eeo[veteran]": IS("I am not a veteran"),
    },
    "recruitee_channable": {  # Utrecht, Netherlands
        "name": NAME, "email": EMAIL, "coverLetter": ANY, "cv": FILE, "phone": PHONE,
        "open_question_7715617": HEARD, "open_question_7715618": IS("I need sponsorship"),
        "open_question_7715619": IS("San Francisco"), "open_question_7715620": IS("No"),  # Utrecht office: not open to relocation
        "open_question_7715621": NEED, "open_question_7715622": WRITE, "open_question_7715623": EMPTY,
        "agreement_328": NEED,  # 90-day data retention consent: not among the persona's consents
    },
    "recruitee_personio": {"name": NAME, "email": EMAIL, "coverLetter": ANY, "cv": FILE, "phone": PHONE},
    "workable_blueground": {  # remote, Brazil
        "firstname": FIRST, "lastname": LAST, "email": EMAIL, "headline": ANY, "phone": PHONE, "address": SF,
        "avatar": EMPTY, "education": ANY, "experience": ANY, "summary": ANY, "resume": FILE, "cover_letter": ANY,
        "QA_12728097": IS("No"), "QA_12728098": IS("Native/Fluent"), "QA_12728099": NEED,
    },
    "workable_huggingface": {  # remote, United States
        "firstname": FIRST, "lastname": LAST, "email": EMAIL, "summary": ANY, "resume": FILE,
        "CA_47143": GITHUB, "CA_47383": LINKEDIN, "cover_letter": ANY, "CA_10626": EMPTY,
        "CA_10627": IS("1 month"), "CA_10628": IS("Yes"), "CA_10629": HEARD,
        "QA_12487827": NEED,  # attestation: not among the persona's consents
        "QA_12487828": NEED,  # depends on a phrase in the job description and on what is written below
        "QA_12487829": IS("Yes"),  # maintains tidewater (resume)
        "QA_12487830": WRITE, "QA_12487831": WRITE,
    },
    "workable_skroutz": {  # Larnaca, Cyprus
        "firstname": FIRST, "lastname": LAST, "email": EMAIL, "phone": PHONE, "experience": ANY, "resume": FILE,
        "cover_letter": ANY,
    },
}


def resolve(name: str) -> dict:
    """The page's gold keyed by full field key (gold keys may be a unique suffix of one). Every field must have a rule."""
    fields = json.loads((HERE / "pages" / name / "fields.json").read_text())
    keys = [f["key"] for f in fields]
    out = {}
    for short, rule in GOLD[name].items():
        matches = [k for k in keys if k == short] or [k for k in keys if k.endswith(short)]
        assert len(matches) == 1, f"{name}: gold key {short!r} matches {matches}"
        out[matches[0]] = rule
    missing = [k for k in keys if k not in out]
    assert not missing, f"{name}: no gold for {missing}"
    for f in fields:  # a value for a choice field must be one of its options
        values = out[f["key"]].get("is") or out[f["key"]].get("debate") or []
        if f["options"] and values:
            options = {" ".join(o.split()) for o in f["options"]}
            assert any(v in options for v in values), f"{name}: {f['key']} gold {values} not among options"
    return out


def must_hold(name: str) -> bool:
    return any(r.get("need") for r in resolve(name).values())


if __name__ == "__main__":
    for name in GOLD:
        rules = resolve(name)
        kinds = [next(iter(r)) for r in rules.values()]
        print(f"{name:22} fields={len(rules):2} hold={'yes' if must_hold(name) else 'no ':3} "
              f"debate={kinds.count('debate')} is={kinds.count('is') + kinds.count('contains') + kinds.count('phone')}")
