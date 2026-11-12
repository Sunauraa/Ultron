# Infinity Ultron

Claude Code applies to jobs for you. Each day it finds new postings on public job boards and opens each job on the company's own website. It fills the application from your answers and your resume. Then it either stops for you to check and send it (approval mode) or sends it itself (auto mode). Every job ends up in `applied.csv` with its status.

Ultron is the browser Claude Code uses for this. It's an MCP server that pre-fills everything that needs no judgement and decides pop-ups with a tiny on-device model. Sending is controlled in code, never by the model. Ultron began as a research project on tiny models for web forms and pop-ups; that work, its models and results are in [`ultron/`](ultron/README.md).

The full guide to the job pipeline is [`autoapply/README.md`](autoapply/README.md).

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

### 4. The daily run

```bash
echo "greenhouse anthropic" > companies.txt     # one company per line: "platform name", a board URL, or the careers page
./run.sh
```

`run.sh` runs these steps:
1. It fetches new postings from the boards (no LLM).
2. It filters them by your config, skipping jobs already in `applied.csv`.
3. For each job, up to `max_jobs_per_run`, it runs `claude -p` with only Ultron's tools. Each run's transcript is saved in `logs/`.

Every job is logged in `applied.csv`:

| Status | What you do |
|---|---|
| `ready` | The form is filled in its Chrome tab: check it, press Submit, then `python mark.py URL submitted` |
| `submitted` | Nothing: the page confirmed it |
| `needs_info` | A required question isn't in answers.md: run `python ask.py` to answer it, and the job is tried again on the next run |
| `needs_human` | A captcha, sign-in wall, Workday, or an error: apply yourself at the link |
| `skipped` | Nothing: the job was closed or had no form |

### 5. Run it every day

Keep Chrome open between runs: start it once with `./browser.sh` and leave it running. Then add a cron line with `crontab -e`. Cron's `PATH` is short, so name where `claude` and your Python are:

```
PATH=/home/you/.local/bin:/usr/local/bin:/usr/bin:/bin
ULTRON_PYTHON=/path/to/venv/bin/python
0 9 * * * /path/to/Infinity_Ultron/autoapply/run.sh >> /path/to/Infinity_Ultron/autoapply/logs/run.log 2>&1
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

Not tested yet:
- Real Claude Code end to end.
- Filling or sending an application on a live site.

Details are in [`autoapply/README.md`](autoapply/README.md#tested-so-far).

## Repository layout

| Folder | What's in it |
|---|---|
| `autoapply/` | The job pipeline: `fetch.py` and `filter.py`, `run.sh`, the Ultron browser MCP server (`ultron_mcp.py`), its pop-up model, tests and the offline benchmark. Full guide: [`autoapply/README.md`](autoapply/README.md) |
| `ultron/` | The research behind Ultron: the Browser Use plugin, the forms and pop-up models, their training data, benchmarks and results. See [`ultron/README.md`](ultron/README.md) |
| `.github/` | Publishes `ultron/docs/` (the demo page) with GitHub Pages |
