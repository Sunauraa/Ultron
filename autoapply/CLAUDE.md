# Applying to jobs

This folder is a job-application pipeline. The user starts Claude Code here and asks, for example, "submit job
applications to those that just published within 24 hours". Then:

1. **Run `./run.sh --hours 24`** from this folder. Use the hours the user names; "just published", "today" or "new
   jobs" means 24. It takes about a minute per job, so run it in the background and wait for it to finish.
   run.sh fetches the boards in companies.txt, keeps the jobs published in that window that match config.toml, and
   runs one separate Claude Code agent per job with only Ultron's browser tools. That agent fills the form and, as
   config.toml says, sends it or leaves it for the user. Never fill, submit or open job pages yourself.
2. **If it ends with "more job(s) wait in the queue"**, run the same command again, until none wait. Each run is
   capped at `max_jobs_per_run`.
3. **Report from what run.sh printed at the end** (the "This run:" report): the count for each status, then each job
   with what the user should do. When the report has `ready` jobs, say their forms are open in Chrome tabs to check
   and submit, then record each with `python mark.py URL submitted`.
4. **If questions are waiting** (run.sh says so): run `python ask.py --list` and ask the user every question at once
   in the chat, with the form's options. Save each reply with `python ask.py --answer N "reply"`, exactly as the
   user gave it. Never answer a question for the user. Then offer to run `./run.sh --hours 24` again: those jobs are
   retried while they are still in the window.
5. **Don't change config.toml** (`auto_submit`, `review`, the filters) unless the user asks. Going from approval
   mode to sending on its own is the user's decision.
6. **If run.sh fails** (Chrome didn't start, `claude` or a Python package not found, another run still going),
   report the error and how to fix it; don't work around it. ULTRON_PYTHON names the Python that has the packages.

A job's whole agent run is in `logs/` (named in applied.csv notes when the agent ended without logging).
