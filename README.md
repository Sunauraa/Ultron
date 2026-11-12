# Ultron

**Until Landing That Role, Overnight, Nonstop.**

Ultron applies to jobs for you, with Claude Code as its brain. Each day it finds new postings on public job boards and opens each job on the company's own website. It fills the application from your answers and your resume. Then it either stops for you to check and send it (approval mode) or sends it itself (auto mode). Every job ends up in `applied.csv` with its status.

Claude Code does the thinking; Ultron does the rest. It reads the job boards, filters the new postings, and gives Claude a browser of its own: an MCP server that pre-fills everything that needs no judgement and decides pop-ups with a tiny on-device model. Sending is controlled in code, never by the model. Ultron began as research on tiny models for web forms and pop-ups; that work, its models and results are in [`research/`](research/README.md).

The full guide to the job pipeline is [`autoapply/README.md`](autoapply/README.md). The project page, with a side-by-side video of Claude Code applying through Ultron and through Playwright MCP, is published from `docs/` with GitHub Pages.

## Run it with Claude Code

### What you need

- **Claude Code, installed and logged in.** Install it with `curl -fsSL https://claude.ai/install.sh | bash` (or `npm install -g @anthropic-ai/claude-code`). Then run `claude` once and log in. Each job is one `claude -p` run of up to 40 turns, charged to that account.
- **Python 3.11+, and Chrome or Chromium.**
- **A screen for the first runs.** Approval mode leaves each filled form open in Chrome for you. On a server without a screen, see [No screen](#no-screen) below.

### 1. Install (once)

```bash
cd autoapply
pip install playwright mcp pypdf reportlab numpy
playwright install chromium
```

If you install these into a virtual environment, point the scripts at it with `export ULTRON_PYTHON=/path/to/venv/bin/python`. Otherwise they use `python3`.

### 2. Add your details

```bash
cp config.example.toml config.toml
cp answers.example.md answers.md
cp /path/to/your/resume.pdf resume.pdf
```

- **`answers.md`:** one `Question: answer` per line (name, email, phone, links, work eligibility, salary...). Claude copies these values exactly, and Ultron checks that it did. A required question that isn't there is never guessed.
- **`config.toml`:**
  - `[filter]`: which job titles and locations you want.
  - `[apply]`: `auto_submit = false` to start; `review = true` makes Claude check every field before the form is held or sent; `max_jobs_per_run`.

These files, and everything the runs write (`applied.csv`, `logs/`, `browser-profile/`...), are in `.gitignore`.

### 3. Apply to one job while you watch

```bash
./apply_now.sh https://job-boards.greenhouse.io/<company>/jobs/<id>
```

This opens Chrome and an interactive Claude Code session. Claude can use only Ultron's tools: no shell, no file edits, no web access.
1. Claude opens the job.
2. Ultron pre-fills what answers.md and your resume cover.
3. Claude fills the rest. When a required question isn't in answers.md, Claude asks you and saves your answer there.
4. In approval mode it stops before sending. Check the form in Chrome and press Submit yourself, then record it with `python mark.py URL submitted`.

### 4. Every morning: ask Claude Code

List the companies once:

```bash
echo "greenhouse anthropic" > companies.txt     # one company per line: "platform name", a board URL, or the careers page
```

Then each morning, start Claude Code in `autoapply/` and ask:

```
cd autoapply && claude
> submit job applications to those that just published within 24 hours
```

`autoapply/CLAUDE.md` tells Claude Code what to do with that request. It runs `./run.sh --hours 24`, which:
1. Fetches new postings from the boards (no LLM).
2. Keeps those published in the last 24 hours that match your config and aren't already in `applied.csv`. A posting with no date counts only when it first appeared in that window, on a board read before. A board that gives only a day (no time) counts that whole day, so such a job can be up to about two and a half days old.
3. For each job, up to `max_jobs_per_run`, runs a separate `claude -p` with only Ultron's tools. Each run's transcript is saved in `logs/`.
4. Prints a report of this run: each job, its status and what you should do.

Claude reruns it while jobs still wait in the queue, then tells you the report. If a required question isn't in answers.md, Claude asks you in the chat (`python ask.py --list`), saves your reply (`python ask.py --answer N "reply"`), and offers to retry those jobs. It never answers for you and never changes `config.toml` unless you ask.

The first time, Claude Code asks permission to run `./run.sh`; choose "don't ask again" to make the routine one sentence.

Every job is logged in `applied.csv`:

| Status | What you do |
|---|---|
| `ready` | The form is filled in its Chrome tab: check it, press Submit, then `python mark.py URL submitted` |
| `submitted` | Nothing: the page confirmed it |
| `needs_info` | A required question isn't in answers.md: Claude asks you in the chat (or run `python ask.py`), and the job is tried again on the next run |
| `needs_human` | A captcha, sign-in wall, Workday, or an error: apply yourself at the link |
| `skipped` | Nothing: the job was closed or had no form |

### 5. Or without the chat, from cron

Keep Chrome open between runs: start it once with `./browser.sh` and leave it running. Then add a cron line with `crontab -e`. Cron's `PATH` is short, so name where `claude` and your Python are:

```
PATH=/home/you/.local/bin:/usr/local/bin:/usr/bin:/bin
ULTRON_PYTHON=/path/to/venv/bin/python
0 9 * * * /path/to/Infinity_Ultron/autoapply/run.sh --hours 24 >> /path/to/Infinity_Ultron/autoapply/logs/run.log 2>&1
```

### 6. Switch to auto

Once several runs look right, set `auto_submit = true`. From then on, Ultron sends a form when everything in it came from answers.md and your resume. Forms where Claude wrote an answer itself (a "Why us?" or a cover letter) are still held as `ready`, unless you also set `auto_submit_written_answers = true`.

### No screen

On a server, set `headless = true` in `config.toml`. To see and submit the held forms from your own computer, run `ssh -L 9222:127.0.0.1:9222 <server>`. Then open `chrome://inspect` in your local Chrome and add `localhost:9222` under "Configure".

### Codex instead of Claude Code

`AGENT=codex ./run.sh`. The Codex flags have not been tested yet.

### What has been tested

- **The three offline test suites** in `autoapply/tests/`.
- **36 recorded real application pages, replayed offline.** They cover Greenhouse, Lever, Ashby, Workable, Recruitee, Teamtailor, Personio, BambooHR and Gem, plus three company sites with Greenhouse in a frame.
- **The whole `run.sh` pipeline end to end**, with a local model standing in for `claude -p`.
- **Real Claude Code, on a recorded page served offline** (one run each): one application through Ultron (8 turns, $0.09, every scored field right) against Playwright MCP (53 turns, $0.30, also right); and the morning request above, which applied only to the job published in the last 24 hours.

Not tested yet:
- Filling or sending an application on a live site.

Details are in [`autoapply/README.md`](autoapply/README.md#tested-so-far).

## Repository layout

| Folder | What's in it |
|---|---|
| `autoapply/` | The job pipeline: `fetch.py` and `filter.py`, `run.sh`, the Ultron browser MCP server (`ultron_mcp.py`), its pop-up model, tests and the offline benchmark. Full guide: [`autoapply/README.md`](autoapply/README.md) |
| `research/` | The research behind Ultron: the Browser Use plugin, the forms and pop-up models, their training data, benchmarks and results. See [`research/README.md`](research/README.md) |
| `docs/` | The project page and demo video |
| `.github/` | Publishes `docs/` with GitHub Pages, and `research/docs/` under `/research/` |
