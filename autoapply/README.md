# Ultron: the pipeline

*Until Landing That Role, Overnight, Nonstop.*

Ultron applies to jobs for you every day, with Claude Code (or Codex) as its brain. Its browser, an MCP server, keeps the token bill small and the dangerous actions under code control.

```
companies.txt
   ↓  [1] fetch.py     (cron, daily, no LLM)  public job-board APIs and feeds (boards listed below)
postings.jsonl
   ↓  [2] filter.py    keywords, location, age; skips anything already in applied.csv
jobs.txt  (queue)
   ↓  [3] claude -p    one run per job, with only the Ultron browser tools
           open the job on the company's own site (the board's form if that has none)
           → Ultron pre-fills answers.md and the resume → fill the rest → submit (or stop for you)
   ↓  [4] log          written by Ultron in code, not by the model
applied.csv  (time, url, company, title, platform, status, notes)
```

## Setup (once, on the computer that will run it)

```bash
pip install playwright mcp pypdf reportlab numpy && playwright install chromium     # Python 3.11+
cp config.example.toml config.toml        # keywords, locations, THE SWITCH
cp answers.example.md answers.md          # your answers, one "Question: answer" per line
cp /path/to/your/resume.pdf resume.pdf
echo "greenhouse anthropic" > companies.txt   # or a board URL, or the company's careers page (below)
./browser.sh                              # opens the dedicated Chrome profile
```

Each morning, start `claude` in this folder and ask "submit job applications to those that just published within 24 hours". `CLAUDE.md` leads it to run `./run.sh --hours 24`, rerun while jobs wait in the queue, report each job with what you should do, and ask you in the chat any question answers.md lacks. Without the chat: the cron line from the top of `run.sh`, with `--hours 24`.

**Which jobs count as published in the last N hours (`--hours N`).** The date the board gives: Greenhouse's `first_published` (never `updated_at`, which changes on any edit), Lever's `createdAt`, and so on. A board that gives only a day counts that whole day, so such a job can be up to about two and a half days old. A posting with no date counts only when fetch.py first saw it inside the window and its board had been read before (`boards_read.json`), so the first read of a board takes none of its undated jobs. Without `--hours`, `max_age_days` in config.toml applies.

The Chrome window must stay open between runs: approval mode leaves each filled form in its own tab.

## Where the jobs come from

One line per company in `companies.txt`, in any of three forms:

- `greenhouse anthropic`: the platform and the board's name.
- A board's address: `https://jobs.ashbyhq.com/notion`, `https://onezero.bamboohr.com/careers`...
- **The company's own careers page:** `https://www.figma.com/careers/`. fetch.py finds the job board the page uses, from its HTML or, when the board is loaded by script, from the page rendered in a headless browser. If the page names several boards, only those whose job list answers are kept. A page that names none, or still more than one, is reported and skipped. What was found is saved in `boards.json`, so the page is read once. The careers page here is only a way to find the board; where the application is made is below.

| Board | Read from | Applied to |
|---|---|---|
| Greenhouse, Lever, Ashby, Workable, Recruitee | public job-board APIs | yes |
| Teamtailor, Personio, BambooHR, Gem | RSS / XML / JSON job feeds | yes |
| Workday | the board's sitemap | no: Workday asks you to create an account on the company's site first. `run.sh` logs these jobs `needs_human` with the link, without an agent run |
| SmartRecruiters, iCIMS, Oracle, Jobvite and others | not read | if a page from one is opened, Ultron reports its bot check or sign-in wall and the job is logged `needs_human` |

## Where the application is made

Jobs are found on the job boards, and applied to on the company's own website when the board names the job's page there.

- **Greenhouse** gives each job's page on the company's site (`absolute_url`, for example `careers.airbnb.com/positions/…`, `stripe.com/jobs/search?gh_jid=…`). That page is the job's `url` in jobs.txt. The board's own form is kept beside it, as the 6th column.
- The company's page usually shows the board's form in a frame. Ultron fills it **inside the company's page**, and the form is sent from there. It does not open the frame on its own. Pop-ups on the company's page around the form are handled too.
- **Fallback:** if the company's page has no application form, doesn't open, or shows a sign-in wall or bot check, Ultron opens the board's form for the same job instead. The job is never skipped for this. The notes in applied.csv start with `Board's form used (<why>)`. The job keeps its company-page url as its key, so it is never applied to twice.
- **Lever, Ashby, Workable, Recruitee, Teamtailor, Personio, BambooHR and Gem** name no company page in their APIs, so those jobs are applied to on the board's form. applied.csv says `Board's form used (the board names no page on the company's own site)`.
- Either way the application lands in the same applicant-tracking system. Whether applying from the company's page gets more replies has not been measured.

## The switch: approval mode, then auto

`auto_submit` in `config.toml`:

- **`false` (start here).** Ultron fills the form and stops before the final send. The tab stays open, and the job is logged as `ready`, with any answers the agent wrote listed in `notes`. You check it and click Submit yourself, then run `python mark.py URL submitted`. Use this period to fix `answers.md` and your filters.
- **`true`.** Ultron sends the form and logs `submitted` once the page confirms it. Forms with answers the agent wrote itself (e.g. "Why us?") are still held as `ready` unless `auto_submit_written_answers = true`.

**Review before sending (`review = true`).** `submit` first shows the agent (Claude Code or Codex) a review sheet: every field, its value and where it came from (pre-filled by Ultron from answers.md, learned on an earlier form, filled or written by the agent, already on the page), and every pop-up Ultron's model decided. The agent fixes what's wrong, records each mistake Ultron made with `note_mistake`, then calls `submit` again. `auto_submit` still decides who gives the final go: `true`, the reviewed form is sent; `false`, it waits for you as `ready`. Mistakes go to `mistakes.jsonl`, for fixing Ultron later. A wrong pop-up choice is also saved to `popup_examples.jsonl` as a labelled example in the pop-up model's training format.

The switch is read in code by Ultron's `submit` tool. The agent has no other way to send a form: it gets only Ultron's tools (no shell, no file edits, no web fetch). Ultron's `click` refuses buttons that would send the form.

## Statuses in applied.csv

| Status | Meaning | What you do |
|---|---|---|
| `ready` | Filled, waiting for you (approval mode, or the agent wrote an answer) | Review the tab, submit, `python mark.py URL submitted` |
| `submitted` | Sent, and the page confirmed it | Nothing |
| `needs_info` | A required question isn't answered in answers.md (named in notes) | Run `python ask.py` (below): the job is queued again on the next run |
| `needs_human` | Captcha, an error, or the agent stopped without logging | Do it by hand, or mark it skipped |
| `skipped` | Closed, or no form | Nothing |

## When answers.md doesn't have the answer

The agent never guesses a fact about you. What happens instead depends on whether you are there:

- **Scheduled runs (cron).** Nobody can be asked, so the job is logged `needs_info`, and Ultron saves every required question still empty (with the form's options) to `questions.json`. At the end of the run, `run.sh` prints how many are waiting. Run `python ask.py`: it asks each question once, even if several jobs asked it; you type the answer or an option's number. Each answer is added to `answers.md`, which queues those jobs again on the next run. Later forms use it too.
- **With you there: `./apply_now.sh URL`.** Claude runs interactively. When a required fact is missing, it asks you in the conversation, saves your reply to `answers.md` with Ultron's `add_answer` tool, fills it and carries on. `add_answer` works only in this mode (`ULTRON_INTERACTIVE=1`), so a scheduled run can't write its own guesses into `answers.md`.

## Learned answers

Forms word the same question differently ("Desired compensation", "Salary expectations"). Ultron pre-fills a field when one answers.md line clearly names its question. When it can't tell, the agent fills it. If the agent uses a value copied word for word from one answers.md line, Ultron remembers that this question is answered by that line (`learned.json`). Later forms asking the same question are pre-filled with no model call. Only the link is stored, never the value: editing answers.md changes every learned answer. If the agent changes a learned answer on a form, the link is forgotten. Delete an entry in `learned.json` to make Ultron forget it.

## Cover letters

Set `[cover_letter] write` in config.toml: `off`, `required` (only when the form requires one; the default) or `always`.

- **Research comes only from the job's own board.** `research_company` reads the posting and the company intro from the platform's public job API or feed (every board fetch.py applies to). Nothing is looked up by company name elsewhere, so no fact can belong to another company with the same name.
- **How the letter is written follows the evidence.** In ResumeGo's field experiment (7,287 applications; figures as reported in write-ups of it), tailored letters got 16.4% callbacks, generic ones 12.5% and no letter 10.7%. [Cui, Dias & Ye (2025)](https://arxiv.org/abs/2509.25054) found that how closely a letter matches the post predicts callbacks. As AI-written letters converge, employers lean on concrete past work instead. So the letter names the role and one specific reason from the posting. It answers the posting's 2 or 3 main requirements, each with one real thing from your resume and its real numbers. It is 120–350 words, in the posting's language.
- **Checked in code before it is used.** The letter must name the company and the role. Every number in it must appear in the posting, answers.md or your resume. Placeholders and stock phrases ("passionate", "proven track record", "I am writing to") are refused. A rejected letter is rewritten by the agent, never sent.
- **A file field gets a one-page PDF** with your name and contact line from answers.md; a text box gets the text. Every letter is saved in `cover_letters/`. Letters count as written by the agent, so they are held for your review unless `auto_submit_written_answers` is true.

## Pop-ups

Cookie bars, newsletter overlays, chat widgets and notices are decided by Ultron's own pop-up model, not by word lists. This is the original Ultron model (`ultron-dialogs-0.1`: a byte-level transformer of under 1M parameters, two checkpoints averaged), run with numpy (`popups.py`, about 90 ms a pop-up on CPU). For each pop-up it picks one button to press, "leave alone" or "escalate". On 281 held-out pop-ups from the original project, it answered 252 at its 0.6 confidence gate and was right on 94.4% of those. `tests/test_popups.py` checks that the numpy version gives the PyTorch original's probabilities on all 318 test pop-ups (largest difference 7e-7, no choice different).

- **What counts as a pop-up:** a dialog (`role=dialog`, `aria-modal`, an open `<dialog>`) or a fixed box over the page. Site headers, navigation and footers are not. Nor is a box with 3 or more visible fields to type in, since that is the form itself.
- **Ultron presses a button itself only when** the model is at least 60% sure and exactly one button has that label. Even then it never presses a send button, a link to another page or a button with no label. Everything else is shown to the agent with the model's choice, and `submit` won't send while such a pop-up is open.
- **Pop-ups that come later** (a newsletter overlay after a few seconds) are handled before each `fill` and `submit`. Fields inside a pop-up are never pre-filled.
- **"Are you sure you want to submit?"** An in-page confirmation is pressed only inside `submit`, after the decision to send. The same applies to the browser's own `confirm()`. Any other browser dialog is dismissed and reported.
- **On the 22 recorded real pages,** it found 7 pop-ups and nothing else. Cookie bars on Lever (Palantir, Spotify) and Workable (Blueground, Hugging Face, Skroutz) were declined. Channable's Cookiebot banner, which has no decline button, was accepted with "Allow all", and its recruitment-scam notice was closed with ×. The other 16 pages, fixed site headers included, produced no pop-up.

## What Ultron guarantees in code

- **Hidden fields are never listed or filled.** Faded, tiny, clipped or off-page copies of fields are how pages steal what an agent types (EIA, ICLR 2025).
- **Answers come from answers.md, or are flagged.** Each value is checked against answers.md. A Yes/No only counts when the answers.md line is about the same question. Everything else is marked "written by the agent".
- **No made-up contact details.** An email address, or a phone number in a phone field, that isn't in answers.md or your resume is refused. Agents that skip answers.md invent them (`johndoe@example.com`, `555-1234`). A form sent with one is a lost application, since the company can't reach you.
- **Your answers stay yours.** A field that adds a word naming someone or something else is never given your answers.md value, and if the agent puts one there it is flagged for review. The words include emergency contact, reference, spouse, passport, previous job and similar. Your phone is not your emergency contact's, and the country you live in is not your passport country.
- **Nothing is sent with a required field empty,** an error showing, or a captcha up.
- **No account is made for you.** When a form has two send buttons, a button that would also save a profile or create an account is never pressed if a plain one is there. Gem has "Apply and save" and "Apply without saving".
- **A stuck agent doesn't burn its turns.** The second time a `fill` or `submit` gives the same failure, Ultron says repeating won't help. On the third, Ultron logs the job `needs_human` with the reason.
- **Only your resume file, and cover letters the config allows, can be uploaded.** Letters pass the checks above first.
- **High-ban-risk sites are never opened:** LinkedIn, Indeed, Glassdoor, ZipRecruiter and others; see `blocked_sites`. The boards Ultron applies to have public application forms with no login. A sign-in wall or bot check (also inside a frame) stops the job as `needs_human`; Ultron never signs in.

## Why it saves tokens

A general browser MCP sends the model a full page snapshot after most actions. Ultron sends a numbered field list instead. It also fills everything that needs no judgement before the model sees the form: on the 22 recorded real pages, `open_job` pre-filled 171 fields (resume, contact details, links, self-identification), and none were wrong. The model then fills only what's left and calls `submit`. On three real application pages this was about 1.9–2.3 KB of text each (Anthropic on Greenhouse: 25 fields; Palantir on Lever: 30 fields, with a 3,301-option university list summarised; OpenAI on Ashby: 14 fields). A whole form is filled in one or two `fill` calls. The benchmark in `bench/` measures the difference against Playwright MCP. On 21 real application pages replayed offline, and scored on the request each page actually sent, Ultron sent a fully correct application on 16 of 33 attempts with Qwen3-32B. Playwright MCP managed 0 of 33, and Ultron used about 12× fewer prompt tokens. The page recordings and raw results are kept out of the repository, since the recordings hold the sites' own traffic.

## Files

| File | What |
|---|---|
| `fetch.py`, `filter.py` | steps 1 and 2 (no LLM) |
| `ultron_mcp.py` | the Ultron browser MCP server |
| `prompt.md`, `playbooks/*.md` | what the agent is told; the playbook for the job's platform is added to the prompt |
| `run.sh`, `browser.sh`, `mark.py` | the cron chain, the long-lived Chrome, manual status changes |
| `CLAUDE.md`, `report.py` | what Claude Code does with the morning request; the end-of-run report |
| `boards_read.json` | written at run time: when each board was first read, for undated postings |
| `popups.py`, `models/popups/` | the pop-up model (numpy) and its two checkpoints |
| `jobinfo.py` | reads the posting and company intro from the job's board, for `research_company` |
| `learned.json`, `cover_letters/` | written at run time: learned question → answers.md line; every cover letter sent or held |
| `ask.py`, `questions.py`, `apply_now.sh` | answering the questions answers.md lacked (`--list` and `--answer N` for Claude to ask you in the chat); applying with you in the conversation |
| `config.example.toml`, `answers.example.md` | templates |
| `tests/` | end-to-end test of the MCP server on local fixture pages (`python tests/test_ultron_mcp.py`); the pop-up model against its PyTorch original (`tests/test_popups.py`); fetch, careers pages, filter, jobinfo and `run.sh` offline with a stand-in `claude` (`tests/test_pipeline.py`) |
| `boards.json` | written at run time: careers page → the board found on it |
| `bench/e2e/` | the whole pipeline end to end (`run.sh` → fetch → filter → agent → Ultron → applied.csv) on recorded real pages served offline, with a local model in place of `claude -p`; with real Claude Code, `record_demo.py` and `compose_demo.py` (the demo video, Ultron against Playwright MCP) and `daily_check.py` (the morning request) |

## Tested so far

- **Offline test suites (all pass):** `tests/test_ultron_mcp.py`, `tests/test_pipeline.py` and `tests/test_popups.py`, run as described in Files above. They also cover the company-page flow: a form in a frame filled in place (the frame's page is loaded once), the fallback to the board's form on a sign-in wall or a page with no form, and needs_human when neither page has a form.
- **Real pages, replayed offline:** 36 recorded pages, each served from its recording (`bench/replay.py`; nothing reaches the real site). `bench/check_pages.py --fill` opens and pre-fills each one:
  - Application forms on Greenhouse, Lever, Ashby, Workable, Recruitee, Teamtailor, Personio, BambooHR and Gem.
  - Three company career sites that show Greenhouse in a frame: Stripe, Airbnb and Databricks.
  - Coinbase (a bot check), and Workday, iCIMS, Oracle, SmartRecruiters and Jobvite. These are detected as walls only: Ultron never fills them.
- **The whole pipeline end to end** (`bench/e2e/`): the real `run.sh` → fetch → filter → agent → Ultron → `applied.csv`, on 31 of those pages (every form, the four company sites and Workday), in approval mode and in auto mode with review. A local model (Qwen3-32B-AWQ) stands in for `claude -p`, with the same flags and only Ultron's tools.
  - Final run, 62 jobs:
    - Approval mode: 24 ready, 3 needs_info, 3 needs_human, 1 skipped.
    - Auto mode with review: 22 held for review (ready), 1 submitted, 4 needs_info, 3 needs_human, 1 skipped.
  - No job ran out of turns. Every job was logged.
  - The needs_info and needs_human cases are the right outcome, with one exception: one run where the local model wrote its tool call as plain text, which `run.sh` logged needs_human ("Agent ended without logging"). The others:
    - needs_info: the persona's answers.md lacks the answer, or the page offers no option for it (Stripe's residence list has no United States).
    - needs_human: Workday, Coinbase's bot check, and Gem after sending, because the recording can't show the site's confirmation.
    - skipped: a closed job (Ashby's "Page not found").
  - The first two runs found 8 Ultron bugs, now fixed.
- **Real Claude Code** (`bench/e2e/`, one run each, on the recorded Figma page served offline, fictional applicant):
  - `record_demo.py`: the real `run.sh` in approval mode with review, against Claude Code with Playwright MCP and the facts in its prompt (told to stop before sending). Submit was pressed afterwards and the request the page sent was scored. Ultron: 31 s, 8 turns, $0.09, every scored field right. Playwright MCP: 97 s, 53 turns, $0.30, every scored field right but one optional field the facts answer left empty.
  - `daily_check.py`: `claude -p "submit job applications to those that just published within 24 hours"` with three postings queued (published 2 hours ago, 5 days ago, and undated from its board's first read). Claude ran `./run.sh --hours 24`; only the 2-hour-old job was applied to (`ready`); the other two were never opened. Its reply named the job, the answer the agent wrote itself, and `mark.py`.
- **Not tested:**
  - Real Claude Code on many jobs; Codex at all.
  - Jobvite past its consent step. The recording stops there.
  - Filling or sending a real application on a live site. Every page above is a recording.
  - The fallback onto a *real* board form after a company page fails. The board pages for the company-site jobs weren't recorded, so offline the fallback finds no form, and the fallback is tested on fixture pages.
  - Whether applying on the company's own page gets more replies than the board's form. The application lands in the same applicant-tracking system either way.
