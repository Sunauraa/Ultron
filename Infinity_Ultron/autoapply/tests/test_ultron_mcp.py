"""End-to-end test of ultron_mcp.py through a real MCP client, on local fixture pages (no LLM, no real sites).

Checks: hidden fields are never listed or filled; answers the agent writes are flagged; approval mode sends
nothing and logs "ready"; click refuses send buttons; blocked sites are refused; auto mode sends and logs "submitted";
cover letters follow config and are checked, saved and held; learned questions are pre-filled and forgotten when changed;
pop-ups are decided by the pop-up model, and Ultron never presses a send, link-away, unlabelled or repeated button in one.
Wide set (other ATSs and company sites): a form in a company page's frame, sign-in walls and bot checks logged as
needs_human, Gem-style forms (text-before labels, unnamed radios, "Please select" dropdowns, read-only boxes),
phone country pickers, non-English apply buttons, failed and "add another" uploads.
Usage: python tests/test_ultron_mcp.py   (exit code 0 when every check passes)
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

HERE = Path(__file__).parent
ROOT = HERE.parent
WORK = ROOT.parent / "tmp" / "ultron_mcp_test"
PORT = 8791
ANSWERS = """# My answers
First name: Mai
Last name: Tran
Full name: Mai Tran
Email: mai.tran@example.com
Phone: 555-0142
LinkedIn: https://linkedin.com/in/maitran
Current location: San Francisco, CA
Legally authorized to work in the United States: Yes
Require visa sponsorship: No
How did you hear about this job: Company website
Gender: Decline to self-identify
Privacy policy consent: Yes
"""
failures: list[str] = []


def check(condition: bool, what: str) -> None:
    print(("PASS " if condition else "FAIL ") + what)
    if not condition:
        failures.append(what)


def setup(auto_submit: bool) -> None:
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    config = (ROOT / "config.example.toml").read_text().replace("auto_submit = false", f"auto_submit = {str(auto_submit).lower()}").replace("headless = false", "headless = true")
    (WORK / "config.toml").write_text(config)
    (WORK / "answers.md").write_text(ANSWERS)
    from reportlab.pdfgen import canvas
    pdf = canvas.Canvas(str(WORK / "resume.pdf"))
    pdf.drawString(72, 720, "Mai Tran - ML engineer. Python, PyTorch. Built a retrieval system at Example Corp.")
    pdf.save()


async def call(session: ClientSession, tool: str, **arguments) -> str:
    result = await session.call_tool(tool, arguments)
    return "\n".join(c.text for c in result.content if getattr(c, "text", None))


def field_id(listing: str, label: str) -> int:
    match = re.search(r"\[(\d+)\] " + re.escape(label), listing)
    assert match, f"{label!r} not in:\n{listing}"
    return int(match.group(1))


def log_rows() -> list[dict]:
    path = WORK / "applied.csv"
    return list(csv.DictReader(path.open())) if path.exists() else []


async def run(auto_submit: bool) -> None:
    setup(auto_submit)
    traffic = WORK / "traffic.log"
    server = subprocess.Popen([sys.executable, str(HERE / "fixtures" / "server.py"), str(PORT), str(traffic)])
    time.sleep(1)
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "ultron_mcp.py"), str(WORK)],
                                   env={**os.environ, "ULTRON_CDP": "http://127.0.0.1:1"})
    try:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            mode = "auto" if auto_submit else "approval"

            refused = await call(session, "open_job", url="https://www.linkedin.com/jobs/view/1")
            check("Refused" in refused, f"[{mode}] blocked site refused")

            # Ashby-like page.
            page = await call(session, "open_job", url=f"http://127.0.0.1:{PORT}/ashby_like.html")
            print(page)
            check("Closed a pop-up with 'Accept all'" in page, f"[{mode}] cookie bar closed by the pop-up model")
            check("SSN" not in page and "2 hidden field(s)" in page, f"[{mode}] faded and off-page fields left out")
            check("(use submit)" in page, f"[{mode}] send button marked")
            check(re.search(r"\] Email \*? ?\(text\) = 'mai.tran@example.com'", page) is not None and "--- answers.md ---" in page,
                  f"[{mode}] open_job filled the email from answers.md and showed answers.md")
            check(re.search(r"Resume.*= 'resume.pdf'", page) is not None, f"[{mode}] open_job attached the resume")
            check(re.search(r"Why do you want[^\n]*=", page) is None, f"[{mode}] open_job left the open question to the agent")
            check("Will you now or in the future require visa sponsorship? * (one of) [Yes | No]" in page, f"[{mode}] untyped Yes/No buttons read as a required question")
            ids = {label: field_id(page, label) for label in ["Full name", "Email", "Resume", "Are you legally", "Will you now", "Current location", "Why do you want"]}
            # What run2's local model did when it skipped answers.md: made-up contact details.
            phone = field_id(page, "Phone")
            made_up = await call(session, "fill", entries=[{"field": ids["Email"], "value": "johndoe@example.com", "overwrite": True},
                                                           {"field": phone, "value": "555-1234", "overwrite": True}])
            print(made_up)
            check(made_up.count("not filled") == 2 and "johndoe@example.com" in made_up and "'555-1234'" in made_up,
                  f"[{mode}] an email or phone number the user never gave is refused")
            own = await call(session, "fill", entries=[{"field": phone, "value": "+1 555-0142", "overwrite": True}])
            check("not filled" not in own, f"[{mode}] the user's own phone number with a country code is accepted")
            filled = await call(session, "fill", entries=[
                {"field": ids["Full name"], "value": "Mai Tran"}, {"field": ids["Email"], "value": "mai.tran@example.com"},
                {"field": ids["Are you legally"], "value": "Yes"}, {"field": ids["Will you now"], "value": "No"},
                {"field": ids["Current location"], "value": "San Francisco, CA"},
                {"field": ids["Why do you want"], "value": "I build retrieval systems and want to work on research tooling."},
                {"field": 999, "value": "x"}])
            print(filled)
            check("(written by you" in [l for l in filled.splitlines() if l.startswith(f"[{ids['Why do you want']}]")][0], f"[{mode}] essay flagged as written by the agent")
            check(all("written" not in l for l in filled.splitlines() if not l.startswith(f"[{ids['Why do you want']}]")), f"[{mode}] answers.md values not flagged")
            check("isn't a visible field" in filled, f"[{mode}] unknown field id refused")
            uploaded = await call(session, "upload_resume", field=ids["Resume"])
            check("resume.pdf" in uploaded, f"[{mode}] resume uploaded")
            listing = await call(session, "read_form")
            send_id = int(re.search(r"\[(\d+)\] Submit Application \(use submit\)", listing).group(1))
            refused = await call(session, "click", button=send_id)
            check("Refused" in refused, f"[{mode}] click on send button refused")
            result = await call(session, "submit")
            print(result)
            posts = traffic.read_text() if traffic.exists() else ""
            check("LEAK" not in posts, f"[{mode}] nothing leaked from hidden fields")
            if auto_submit:
                # The essay was written by the agent and config holds those for review.
                check("Stopped before sending" in result and "POST" not in posts, f"[{mode}] written answer held for review")
            else:
                check("Stopped before sending (approval mode)" in result and "POST" not in posts, f"[{mode}] approval mode sent nothing")
            check(log_rows()[-1]["status"] == "ready", f"[{mode}] logged as ready")

            # Greenhouse-like page: every answer comes from answers.md except the salary question, which has no answer.
            page = await call(session, "open_job", url=f"http://127.0.0.1:{PORT}/greenhouse_like.html")
            print(page)
            check("Date of birth" not in page, f"[{mode}] 1 px field left out")
            ids = {label: field_id(page, label) for label in ["First Name", "Last Name", "Email", "How did you hear", "Gender", "What are your salary", "I agree"]}
            filled = await call(session, "fill", entries=[
                {"field": ids["First Name"], "value": "Mai"}, {"field": ids["Last Name"], "value": "Tran"},
                {"field": ids["Email"], "value": "mai.tran@example.com"}, {"field": ids["How did you hear"], "value": "Company website"},
                {"field": ids["Gender"], "value": "Decline to self-identify"}, {"field": ids["I agree"], "value": "yes"}])
            print(filled)
            check(f"[{ids['I agree']}] = 'checked'" in filled, f"[{mode}] a checkbox filled 'yes' is ticked and reported as checked")
            vague = await call(session, "fill", entries=[{"field": ids["I agree"], "value": "maybe", "overwrite": True}])
            on = await call(session, "fill", entries=[{"field": ids["I agree"], "value": "on", "overwrite": True}])
            check("give 'checked' or 'unchecked'" in vague and f"[{ids['I agree']}] = 'checked'" in on and "= 'checked'" in await call(session, "read_form"),
                  f"[{mode}] a checkbox value that isn't on or off is refused, never unticks; 'on' ticks it")
            result = await call(session, "submit")
            print(result)
            check("Not submitted" in result and "salary" in result, f"[{mode}] empty required field blocks submit")
            again = await call(session, "submit")
            check("same result as your earlier submit" in again and log_rows()[-1]["url"].endswith("greenhouse_like.html") is False,
                  f"[{mode}] the same refusal twice is pointed out, nothing logged yet")
            logged = await call(session, "log", status="needs_info", notes="answers.md has no salary expectation")
            check("needs_info" in logged, f"[{mode}] needs_info logged")
            check(await call(session, "log", status="submitted", notes="x") != "", f"[{mode}] log call returns")
            check(log_rows()[-1]["status"] == "needs_info", f"[{mode}] agent can't log submitted itself")
            saved = json.loads((WORK / "questions.json").read_text())
            check([q["question"] for q in saved] == ["What are your salary expectations?"] and saved[0]["jobs"][0]["url"].endswith("greenhouse_like.html"),
                  f"[{mode}] needs_info saved the empty required question for the user")
            tools = [t.name for t in (await session.list_tools()).tools]
            check("add_answer" not in tools and "check_form" not in tools, f"[{mode}] add_answer not offered in a scheduled run")
            asked = subprocess.run([sys.executable, str(ROOT / "ask.py"), str(WORK)], input="150000 USD\n", capture_output=True, text=True, timeout=30)
            print(asked.stdout)
            check("What are your salary expectations?: 150000 USD" in (WORK / "answers.md").read_text() and json.loads((WORK / "questions.json").read_text()) == [],
                  f"[{mode}] ask.py wrote the user's answer to answers.md and cleared the question")
            answers_now = await call(session, "get_answers")
            check("150000 USD" in answers_now, f"[{mode}] the new answer is read by the next job")

            if auto_submit:
                page = await call(session, "open_job", url=f"http://127.0.0.1:{PORT}/greenhouse_like.html")
                ids = {label: field_id(page, label) for label in ["First Name", "Last Name", "Email", "How did you hear", "What are your salary", "I agree"]}
                (WORK / "answers.md").write_text(ANSWERS + "Salary expectations: 150000 USD\n")
                await call(session, "fill", entries=[
                    {"field": ids["First Name"], "value": "Mai"}, {"field": ids["Last Name"], "value": "Tran"},
                    {"field": ids["Email"], "value": "mai.tran@example.com"}, {"field": ids["How did you hear"], "value": "Company website"},
                    {"field": ids["What are your salary"], "value": "150000 USD"}, {"field": ids["I agree"], "value": "yes"}])
                result = await call(session, "submit")
                print(result)
                posts = traffic.read_text()
                check("confirmed" in result and posts.count("POST /submit") == 1 and log_rows()[-1]["status"] == "submitted", f"[{mode}] auto mode sent and logged submitted")
                check("LEAK" not in posts, f"[{mode}] still nothing leaked")
    finally:
        server.terminate()
        server.wait()


LETTER = """Dear Gamma Analytics hiring team,

I am applying for the Data Engineer role. Your posting describes pipelines that analysts rely on every day, and that
is the work I have enjoyed most: building systems other people can trust without having to think about them.

At Example Corp I built a retrieval system in Python and PyTorch, from the ingestion jobs to the evaluation that told
us when it got worse. I care about the boring parts that keep data correct, such as tests on every transform, clear
ownership and alerts that mean something, as much as about the models that sit on top.

I would be glad to talk about how I could help your team ship reliable data products.

Sincerely,
Mai Tran"""


async def run_letters() -> None:
    """Cover letters (config-gated, research first, checked, saved, held for review) and learned answers."""
    setup(auto_submit=False)
    (WORK / "answers.md").write_text(ANSWERS + "Desired pay: 150,000 USD per year\n")
    traffic = WORK / "traffic.log"
    server = subprocess.Popen([sys.executable, str(HERE / "fixtures" / "server.py"), str(PORT), str(traffic)])
    time.sleep(1)
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "ultron_mcp.py"), str(WORK)],
                                   env={**os.environ, "ULTRON_CDP": "http://127.0.0.1:1"})
    url = f"http://127.0.0.1:{PORT}/letter_like.html"
    try:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            page = await call(session, "open_job", url=url)
            print(page)
            ids = {label: field_id(page, label) for label in ["Full name", "Desired compensation", "Resume", "Cover Letter", "Motivation letter"]}
            check(f"[{ids['Cover Letter']}] needs a cover letter" in page and f"[{ids['Motivation letter']}] is a cover letter and config writes one only when required: leave it empty" in page,
                  "[letters] open_job says which cover letters to write, from config")
            check(re.search(r"Desired compensation \* \(text\)\n", page) is not None, "[letters] a question answers.md doesn't name is left to the agent")
            filled = await call(session, "fill", entries=[{"field": ids["Desired compensation"], "value": "150,000 USD per year"},
                                                          {"field": ids["Motivation letter"], "value": "I like data."}])
            print(filled)
            check("written by you" not in filled.splitlines()[0], "[letters] the agent's answers.md value isn't flagged")
            check("use cover_letter" in filled, "[letters] fill refuses a cover-letter field")
            learned = json.loads((WORK / "learned.json").read_text())
            check(learned == {"desired compensation": {"question": "Desired compensation", "line": "Desired pay"}}, "[letters] the question was learned with its answers.md line")
            early = await call(session, "cover_letter", field=ids["Cover Letter"], text=LETTER)
            check("research_company first" in early, "[letters] cover_letter needs research_company first")
            research = await call(session, "research_company")
            check("No job data from the board" in research and "page_text" in research, "[letters] research_company says when the site has no job API")
            check("How to write the cover letter" in research and "120-350 words" in research, "[letters] research_company gives the writing guide when a letter is needed")
            short = await call(session, "cover_letter", field=ids["Cover Letter"], text="Dear team, hire me. Mai")
            placeholder = await call(session, "cover_letter", field=ids["Cover Letter"], text=LETTER.replace("Gamma Analytics", "[Company]"))
            wrong = await call(session, "cover_letter", field=ids["Resume"], text=LETTER)
            optional = await call(session, "cover_letter", field=ids["Motivation letter"], text=LETTER)
            stock = await call(session, "cover_letter", field=ids["Cover Letter"], text=LETTER.replace("I am applying", "I am passionate about applying"))
            invented = await call(session, "cover_letter", field=ids["Cover Letter"], text=LETTER.replace("a retrieval system", "a retrieval system serving 40% more queries"))
            check("stock phrase" in stock and "'passionate'" in stock and "40 aren't in the posting" in invented, "[letters] stock phrases and invented numbers refused")
            check("must have 120 to 350" in short and "placeholder" in placeholder and "isn't a visible cover-letter field" in wrong and "only when the form requires" in optional,
                  "[letters] short, placeholder, wrong-field and not-required letters refused")
            done = await call(session, "cover_letter", field=ids["Cover Letter"], text=LETTER)
            print(done)
            pdfs = list((WORK / "cover_letters").glob("*.pdf"))
            from pypdf import PdfReader
            pdf_text = " ".join(" ".join(PdfReader(pdfs[0]).pages[0].extract_text().split()).split()) if pdfs else ""
            check(len(pdfs) == 1 and pdf_text.startswith("Mai Tran mai.tran@example.com · 555-0142") and "boring parts that keep data correct" in pdf_text
                  and pdf_text.endswith("Sincerely, Mai Tran"), "[letters] the PDF has the heading from answers.md and the whole letter")
            result = await call(session, "submit")
            print(result)
            row = log_rows()[-1]
            check("Stopped before sending" in result and row["status"] == "ready" and "cover_letters/" in row["notes"] and "POST" not in (traffic.read_text() if traffic.exists() else ""),
                  "[letters] the letter is held for review and named in the log")

            page = await call(session, "open_job", url=url)
            print(page)
            check(f"[{ids['Desired compensation']}] Desired compensation * (text) = '150,000 USD per year'" in page and "as answered on earlier forms" in page,
                  "[letters] the learned question is pre-filled on the next form")
            changed = await call(session, "fill", entries=[{"field": ids["Desired compensation"], "value": "160,000 USD", "overwrite": True}])
            check("written by you" in changed and json.loads((WORK / "learned.json").read_text()) == {}, "[letters] changing a learned answer forgets it")

            (WORK / "config.toml").write_text((WORK / "config.toml").read_text().replace('write = "required"', 'write = "off"'))
            page = await call(session, "open_job", url=url)
            refused = await call(session, "cover_letter", field=ids["Cover Letter"], text=LETTER)
            check(f"[{ids['Cover Letter']}] is a cover letter and cover letters are off in config.toml: log needs_info" in page and "Refused" in refused,
                  "[letters] with cover letters off, a required one means needs_info")
    finally:
        server.terminate()
        server.wait()


def check_guards() -> None:
    """clickable_choice: even when the model is sure, Ultron presses only a safe, unambiguous button."""
    sys.path.insert(0, str(ROOT))
    import popups
    import ultron_mcp as u

    def case(choice: str, confidence: float, buttons: list[dict]) -> dict | None:
        popup = {"key": "0", "text": "Some pop-up text here", "buttons": [{"id": b["id"], "text": b["text"]} for b in buttons]}
        u._decisions[(popup["text"], tuple(b["text"] for b in buttons))] = (choice, confidence)
        state = {"buttons": [{"sends": False, "leaves": False, "link": False, "popup": "0", **b} for b in buttons]}
        return u.clickable_choice(popup, state)

    close = {"id": "1", "text": "Close"}
    check(case("click Close", 0.9, [close]) is not None, "[pop-ups] a sure, safe choice is pressed")
    check(case("click Close", popups.GATE - 0.01, [close]) is None, "[pop-ups] below the gate it goes to the agent")
    check(case("click Sign in", 0.99, [{"id": "1", "text": "Sign in", "leaves": True}]) is None, "[pop-ups] a link off the page is never pressed")
    check(case("click Send", 0.99, [{"id": "1", "text": "Send"}]) is None and case("click Go", 0.99, [{"id": "1", "text": "Go", "sends": True}]) is None,
          "[pop-ups] a send button is never pressed")
    check(case("click OK", 0.99, [{"id": "1", "text": "OK"}, {"id": "2", "text": "OK"}]) is None, "[pop-ups] a repeated label is never pressed")
    check(case("click (no label)", 0.99, [{"id": "1", "text": "(no label)"}]) is None, "[pop-ups] an unlabelled button is never pressed")
    check(case("leave alone", 0.99, [close]) is None and case("escalate", 0.99, [close]) is None, "[pop-ups] leave alone and escalate press nothing")


async def run_popups() -> None:
    """Real pop-ups on a page, in auto mode: a cookie dialog, a chat widget, a fixed header, a newsletter overlay that
    appears later with its own email box, an in-page "Are you sure?" before sending, and a browser confirm()."""
    setup(auto_submit=True)
    traffic = WORK / "traffic.log"
    server = subprocess.Popen([sys.executable, str(HERE / "fixtures" / "server.py"), str(PORT), str(traffic)])
    time.sleep(1)
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "ultron_mcp.py"), str(WORK)],
                                   env={**os.environ, "ULTRON_CDP": "http://127.0.0.1:1"})
    url = f"http://127.0.0.1:{PORT}/popup_like.html"
    try:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            page = await call(session, "open_job", url=url)
            print(page)
            check("Closed a pop-up with 'Reject all'" in page and "[cookies:none]" in page, "[pop-ups] the cookie dialog is declined, not accepted")
            check("Pop-up left alone" in page and "Chat with us" in page and "Open chat" not in page.split("Buttons:")[-1],
                  "[pop-ups] the chat widget is left alone and its button isn't offered as a form button")
            check("All jobs" not in page.split("\n[")[0], "[pop-ups] a fixed site header isn't a pop-up")
            time.sleep(5)
            phone = field_id(page, "Phone")
            filled = await call(session, "fill", entries=[{"field": phone, "value": "555-0142", "overwrite": True}])
            print(filled)
            check("Closed a pop-up with 'No thanks'" in page + filled, "[pop-ups] the newsletter overlay that came later is declined")
            listing = await call(session, "read_form")
            check("Your email" not in listing and "Pop-up" not in listing.replace("Pop-up left alone", ""), "[pop-ups] nothing is left open but the chat widget")
            result = await call(session, "submit")
            print(result)
            posts = traffic.read_text() if traffic.exists() else ""
            check("Confirmed sending in a pop-up with 'Submit application'" in result and posts.count("POST /submit") == 1 and "confirmed" in result,
                  "[pop-ups] an in-page 'Are you sure?' is confirmed only as part of submit")
            page = await call(session, "open_job", url=url + "?native=1")
            time.sleep(5)
            result = await call(session, "submit")
            print(result)
            posts = traffic.read_text() if traffic.exists() else ""
            check("Browser dialogs: confirm 'Submit your application to Delta Systems?' (accepted)" in result and posts.count("POST /submit") == 2,
                  "[pop-ups] a browser confirm() is accepted only while submit is sending")
            check("subscribe" not in posts and "chat" not in posts and "LEAK" not in posts, "[pop-ups] Subscribe and Open chat never pressed, nothing typed into the overlay")
            check(log_rows()[-1]["status"] == "submitted", "[pop-ups] logged submitted")
    finally:
        server.terminate()
        server.wait()


async def run_contacts() -> None:
    """Fields about someone else (emergency contact, reference) or another fact (passport country) never get the
    user's own answers.md values, from pre-fill or unflagged from the agent; made-up phone numbers are refused."""
    setup(auto_submit=False)
    (WORK / "answers.md").write_text(ANSWERS + "Mobile: 555-0142\nContact phone: 555-0142\nCountry: United States\n")
    server = subprocess.Popen([sys.executable, str(HERE / "fixtures" / "server.py"), str(PORT), str(WORK / "traffic.log")])
    time.sleep(1)
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "ultron_mcp.py"), str(WORK)],
                                   env={**os.environ, "ULTRON_CDP": "http://127.0.0.1:1"})
    try:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            page = await call(session, "open_job", url=f"http://127.0.0.1:{PORT}/contacts_like.html")
            print(page)
            check("Mobile * (text) = '555-0142'" in page and "Country of residence * (text) = 'United States'" in page,
                  "[contacts] the user's own phone and country are pre-filled")
            check(re.search(r"Passport country \* \(text\)\n", page) and re.search(r"Emergency contact phone \* \(text\)\n", page)
                  and re.search(r"Reference email \(text\)\n", page) and re.search(r"Contact 1: E-mail address \(text\)\n", page),
                  "[contacts] passport country, emergency phone, reference email and a numbered contact's email are not")
            check(page.count("(no label) (one of)") == 2 and "About you" not in page.split("(one of)")[0].splitlines()[-1],
                  "[contacts] a lone radio isn't labelled with the whole form's text")
            ids = {label: field_id(page, label) for label in ["Reference email", "Emergency contact phone", "I confirm"]}
            filled = await call(session, "fill", entries=[{"field": ids["Reference email"], "value": "mai.tran@example.com"},
                                                         {"field": ids["Emergency contact phone"], "value": "555-9999"},
                                                         {"field": ids["I confirm"], "value": True}])
            print(filled)
            lines = filled.splitlines()
            check("written by you" in lines[0], "[contacts] the user's email put in the reference's field is flagged for review")
            check("not filled" in lines[1] and "'555-9999'" in lines[1], "[contacts] a made-up emergency phone number is refused")
            check(lines[2].startswith(f"[{ids['I confirm']}] = 'checked'"), "[contacts] a true/false value is accepted, not a failed call")
    finally:
        server.terminate()
        server.wait()


async def run_styled() -> None:
    """A form built like Recruitee's: the phone box starts with a calling code, the radios' inputs sit under their
    labels, the consent box's input is invisible, and "Thank you!" is on the page before anything is sent."""
    setup(auto_submit=True)
    (WORK / "answers.md").write_text(ANSWERS + "Date available: January 5, 2027\n")
    traffic = WORK / "traffic.log"
    server = subprocess.Popen([sys.executable, str(HERE / "fixtures" / "server.py"), str(PORT), str(traffic)])
    time.sleep(1)
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "ultron_mcp.py"), str(WORK)],
                                   env={**os.environ, "ULTRON_CDP": "http://127.0.0.1:1"})
    try:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            page = await call(session, "open_job", url=f"http://127.0.0.1:{PORT}/styled_like.html")
            print(page)
            check(re.search(r"Phone number \* \(text\)\n", page) is not None, "[styled] a calling code alone is not a phone number, and isn't pre-filled over")
            check("I consent to Zeta Labs" in page, "[styled] a consent box with an invisible input is listed")
            ids = {label: field_id(page, label) for label in ["Phone number", "Do you need visa sponsorship?", "I consent"]}
            filled = await call(session, "fill", entries=[{"field": ids["Phone number"], "value": "555-0142"},
                                                         {"field": ids["Phone number"], "value": "+1 555-0142"},
                                                         {"field": ids["Do you need visa sponsorship?"], "value": "No"},
                                                         {"field": ids["I consent"], "value": "Yes"}])
            print(filled)
            check(re.search(r"Date Available \(text, a date as mm/dd/yyyy\) = '01/05/2027'", page) is not None,
                  "[styled] answers.md's date is pre-filled in the box's format, and kept")
            dates = await call(session, "fill", entries=[{"field": field_id(page, "Date Available"), "value": "As soon as possible", "overwrite": True},
                                                        {"field": field_id(page, "Date Available"), "value": "January 5, 2027", "overwrite": True}])
            check("give a date (as mm/dd/yyyy)" in dates and dates.endswith("= '01/05/2027'") and "'01/05/2027'" in await call(session, "read_form"),
                  "[styled] a date is typed in the box's format and kept, as answers.md's own; a non-date is refused")
            lines = filled.splitlines()
            check("calling code +31" in lines[0], "[styled] a number without its calling code is refused where the page wants one")
            check(lines[1] == f"[{ids['Phone number']}] = '+1 555-0142'", "[styled] the user's phone with a calling code counts as their own answer")
            check(lines[2].startswith(f"[{ids['Do you need visa sponsorship?']}] = 'No'") and lines[3].startswith(f"[{ids['I consent']}] = 'checked'"),
                  "[styled] a radio under its label and an invisible consent box are ticked")
            result = await call(session, "submit")
            print(result)
            posts = traffic.read_text() if traffic.exists() else ""
            check('"sponsor":"No"' in posts and '"consent":"on"' in posts and '"phone":"+1 555-0142"' in posts and '"start":"01/05/2027"' in posts,
                  "[styled] the page sent the ticked choices and the date")
            check("confirmed" not in result, "[styled] 'Thank you!' shown before sending doesn't confirm the application")
    finally:
        server.terminate()
        server.wait()


async def run_review() -> None:
    """review = true: submit shows a review sheet and sends nothing; note_mistake records Ultron's mistakes (a wrong
    pop-up choice also as a training example); submit with reviewed=true then sends, in auto mode."""
    setup(auto_submit=True)
    config = WORK / "config.toml"
    config.write_text(config.read_text().replace("review = false", "review = true"))
    traffic = WORK / "traffic.log"
    server = subprocess.Popen([sys.executable, str(HERE / "fixtures" / "server.py"), str(PORT), str(traffic)])
    time.sleep(1)
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "ultron_mcp.py"), str(WORK)],
                                   env={**os.environ, "ULTRON_CDP": "http://127.0.0.1:1"})
    try:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            check("note_mistake" in tools, "[review] note_mistake is offered when review is on")
            page = await call(session, "open_job", url=f"http://127.0.0.1:{PORT}/popup_like.html")
            time.sleep(5)
            phone = field_id(page, "Phone")
            await call(session, "fill", entries=[{"field": phone, "value": "555-0142", "overwrite": True}])
            sheet = await call(session, "submit", reviewed=True)  # reviewed before seeing the sheet: the sheet comes first
            print(sheet)
            posts = traffic.read_text() if traffic.exists() else ""
            check(sheet.startswith("Review before sending") and "POST /submit" not in posts, "[review] submit shows the sheet first and sends nothing")
            check(re.search(r"Email \* = 'mai.tran@example.com' \(Ultron: pre-filled", sheet) is not None and f"[{phone}] Phone = '555-0142' (filled by you)" in sheet,
                  "[review] the sheet says where each value came from")
            check(re.search(r"P1 click Reject all \(\d+% sure\)", sheet) is not None, "[review] the sheet lists the pop-up model's decisions")
            bad = await call(session, "note_mistake", kind="pop-up", ultron_did="declined cookies", right="click Pay now", popup=1)
            noted = await call(session, "note_mistake", kind="pop-up", ultron_did="clicked Reject all", right="click Manage preferences", popup=1)
            field_note = await call(session, "note_mistake", kind="pre-fill", ultron_did="put a work email", right="personal email", field=phone)
            check("must be one of" in bad and "training example" in noted and field_note.startswith("Noted"), "[review] note_mistake checks a pop-up's right choice")
            rows = [json.loads(l) for l in (WORK / "mistakes.jsonl").read_text().splitlines()]
            examples = [json.loads(l) for l in (WORK / "popup_examples.jsonl").read_text().splitlines()]
            check(len(rows) == 2 and rows[1]["field"]["value"] == "555-0142" and rows[0]["popup"]["choice"] == "click Reject all",
                  "[review] mistakes.jsonl records the field and the pop-up")
            check(len(examples) == 1 and examples[0]["options"][examples[0]["label"]] == "click Manage preferences" and examples[0]["context"].startswith("BUTTONS "),
                  "[review] a wrong pop-up choice becomes a training example")
            result = await call(session, "submit", reviewed=True)
            print(result)
            posts = traffic.read_text() if traffic.exists() else ""
            check(posts.count("POST /submit") == 1 and "2 Ultron mistake(s) noted" in log_rows()[-1]["notes"], "[review] after review, auto mode sends and logs the review")
    finally:
        server.terminate()
        server.wait()


async def run_wide() -> None:
    """Pages built like the other ATSs and company career sites found on the wide set of real pages."""
    setup(auto_submit=False)
    (WORK / "answers.md").write_text(ANSWERS.replace("Phone: 555-0142", "Phone: (415) 555-0142").replace("Gender: Decline to self-identify", "Gender: Female")
                                     + "Country: United States\n")
    traffic = WORK / "traffic.log"
    server = subprocess.Popen([sys.executable, str(HERE / "fixtures" / "server.py"), str(PORT), str(traffic)])
    time.sleep(1)
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "ultron_mcp.py"), str(WORK)],
                                   env={**os.environ, "ULTRON_CDP": "http://127.0.0.1:1"})
    base = f"http://127.0.0.1:{PORT}"
    try:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            page = await call(session, "open_job", url=f"{base}/wide_company.html")
            print(page)
            check("Ultron fills it here, on the company's page" in page and "Can't apply" not in page,
                  "[wide] a form in a company page's frame is used in place; a menu 'Log in' link is no wall")
            check("Link to this job" not in page and "Newsletter" not in page, "[wide] a read-only pre-set box and the top page's newsletter box are left out")
            check(re.search(r"\] First name \* \(text\) = 'Mai'", page) is not None, "[wide] a question written as text before its box is its label")
            check(re.search(r"\] Resume \* \(file\) = 'resume.pdf'", page) is not None and page.count("(file)") == 1,
                  "[wide] the resume box is labelled by its question, not its widget, and the fresh 'add another' box isn't listed")
            check("Will you now or in the future require sponsorship? * (one of) [Yes | No]" in page, "[wide] unnamed radios form one question")
            check(re.search(r"\] Gender \(dropdown\) = 'Female'", page) is not None, "[wide] a 'Please select' button is a dropdown, pre-filled from answers.md")
            check(re.search(r"\] Country \(dropdown\) = 'United States'", page) is not None, "[wide] a dropdown button that starts with a value is listed")
            check("Change file (one of)" not in page, "[wide] a text button beside an icon button is not a question")
            check(re.search(r"\] Phone \* \(text\) = '\+1", page) is not None, "[wide] the phone goes in with the user's calling code over a +61 picker")
            ids = {label: field_id(page, label) for label in ["Will you now", "Gender"]}
            filled = await call(session, "fill", entries=[{"field": ids["Will you now"], "value": "No"},
                                                         {"field": ids["Gender"], "value": "Decline to self-identify", "overwrite": True}])
            print(filled)
            check("= 'No'" in filled and "= 'Decline to self-identify'" in filled, "[wide] an unnamed radio and a menu dropdown are filled")
            again = await call(session, "read_form")
            check(re.search(r"\] Gender \(dropdown\) = 'Decline to self-identify'", again) is not None, "[wide] a dropdown stays listed, with its question, once chosen")
            check(re.search(r"Will you now[^\n]*= 'No'", again) is not None, "[wide] the radio choice reads back")
            loads = (traffic.read_text() if traffic.exists() else "").count("GET /wide_gem.html")
            check(loads == 1, f"[wide] the framed form is filled in its frame on the company's page, never opened on its own ({loads} load(s))")

            page = await call(session, "open_job", url=f"{base}/wide_signin.html")
            print(page)
            check("Can't apply here without the user" in page and log_rows()[-1]["status"] == "needs_human", "[wide] a sign-in wall is logged needs_human")
            page = await call(session, "open_job", url=f"{base}/wide_bot.html")
            print(page)
            check("bot check" in page and log_rows()[-1]["status"] == "needs_human", "[wide] a bot check is logged needs_human")

            page = await call(session, "open_job", url=f"{base}/wide_workable.html")
            print(page)
            ids = {label: field_id(page, label) for label in ["Are you eligible", "Notice period"]}
            filled = await call(session, "fill", entries=[{"field": ids["Are you eligible"], "value": "YES"}, {"field": ids["Notice period"], "value": "4 weeks"}])
            print(filled)
            check(f"[{ids['Are you eligible']}] = 'YES'" in filled and "Options: Available immediately | 2 weeks | 1 month" in filled,
                  "[wide] a radio kept on its box (aria-checked) is ticked; a read-only list shows its options when nothing matches")
            filled = await call(session, "fill", entries=[{"field": ids["Notice period"], "value": "1 month"}])
            again = await call(session, "read_form")
            check(f"[{ids['Notice period']}] = '1 month'" in filled and re.search(r"Are you eligible[^\n]*= 'YES'", again)
                  and re.search(r"Notice period[^\n]*= '1 month'", again), "[wide] both read back: the radio from its box, the read-only list's choice")

            page = await call(session, "open_job", url=f"{base}/wide_apply_de.html")
            print(page)
            check("Opened the form with 'Jetzt bewerben'" in page, "[wide] a German apply button opens the form")
            check(re.search(r"\] Resume \* \(file\)\n", page) is not None, "[wide] a failed upload is not reported as attached")
            upload = await call(session, "upload_resume", field=field_id(page, "Resume"))
            print(upload)
            check("upload failed" in upload and "try uploading again" in upload, "[wide] upload_resume reports the page's upload error")

            # jobs.txt lists the company's page with the board's own form as a sixth column: used when the page can't be.
            (WORK / "jobs.txt").write_text(f"{base}/wide_signin.html\tAcme\tML Engineer\tgem\tRemote\t{base}/wide_gem.html\n"
                                           f"{base}/wide_noform.html\tAcme\tData Engineer\tgem\tRemote\t{base}/wide_gem.html\n"
                                           f"{base}/wide_gem.html?only\tAcme\tDesigner\tgem\tRemote\t{base}/wide_gem.html?only\n")
            for company_page, why in [("wide_signin.html", "asks to sign in"), ("wide_noform.html", "no application form")]:
                page = await call(session, "open_job", url=f"{base}/{company_page}")
                print(page)
                check("opened the job board's own form" in page and why in page and re.search(r"\] First name \* \(text\) = 'Mai'", page) is not None,
                      f"[board] a company page with {why} falls back to the board's form, pre-filled")
                await call(session, "log", status="needs_info", notes="test")
                row = log_rows()[-1]
                check(row["url"] == f"{base}/{company_page}" and row["notes"].startswith("Board's form used (") and why in row["notes"],
                      f"[board] applied.csv keys the job by its company page and notes the board fallback ({why})")
            page = await call(session, "open_job", url=f"{base}/greenhouse_like.html")
            for _ in range(3):
                result = await call(session, "submit")
            print(result)
            check(result.endswith("as needs_human. Stop.") and log_rows()[-1]["status"] == "needs_human"
                  and log_rows()[-1]["notes"].startswith("Ultron stopped the agent: submit gave the same result 3 times (Required field"), "[loop] a third identical refused submit logs the job needs_human for the user")
            check(await call(session, "fill", entries=[{"field": 1, "value": "x"}]) == "This job is already logged.", "[loop] nothing is filled after the job is logged")
            (WORK / "jobs.txt").write_text((WORK / "jobs.txt").read_text() + f"{base}/wide_bot.html\tAcme\tSRE\tgem\tRemote\t{base}/wide_noform.html\n")
            page = await call(session, "open_job", url=f"{base}/wide_bot.html")
            check(page.endswith("Logged as needs_human. Stop.") and log_rows()[-1]["status"] == "needs_human" and "bot check" in log_rows()[-1]["notes"],
                  "[board] when neither the company's page nor the board's page has a form, Ultron logs needs_human itself")
            page = await call(session, "open_job", url=f"{base}/wide_gem.html?only")
            await call(session, "log", status="skipped", notes="test")
            check("board's own form" not in page and log_rows()[-1]["notes"].startswith("Board's form used (the board names no page on the company's own site)"),
                  "[board] a job the board lists on no company page is applied on the board, and applied.csv says so")
            # Auto mode on a form with "Apply and save" and "Apply without saving": the plain one is pressed.
            (WORK / "jobs.txt").unlink()
            (WORK / "config.toml").write_text((WORK / "config.toml").read_text().replace("auto_submit = false", "auto_submit = true"))
            page = await call(session, "open_job", url=f"{base}/wide_gem.html")
            await call(session, "fill", entries=[{"field": field_id(page, "Will you now"), "value": "No"}])
            result = await call(session, "submit")
            print(result)
            posts = traffic.read_text()
            check("gem: Apply without saving" in posts and "gem: Apply and save" not in posts,
                  "[wide] of 'Apply and save' and 'Apply without saving', the one that keeps no profile sends the form")
            (WORK / "config.toml").write_text((WORK / "config.toml").read_text().replace("auto_submit = true", "auto_submit = false"))
            page = await call(session, "open_job", url=f"{base}/wide_company.html")
            check("board's own form" not in page, "[board] a job not in jobs.txt opens as given, with no fallback")
            await call(session, "log", status="skipped", notes="test")
            check(not log_rows()[-1]["notes"].startswith("Board's form used"), "[board] ...and its log row has no board note")
    finally:
        server.terminate()
        server.wait()


check_guards()
asyncio.run(run_review())
asyncio.run(run_styled())
asyncio.run(run_contacts())
asyncio.run(run_popups())
asyncio.run(run(auto_submit=False))
asyncio.run(run(auto_submit=True))
asyncio.run(run_letters())
asyncio.run(run_wide())
print(f"\n{len(failures)} failure(s)" + (": " + "; ".join(failures) if failures else ""))
sys.exit(1 if failures else 0)
