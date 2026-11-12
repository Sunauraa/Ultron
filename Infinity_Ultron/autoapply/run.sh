#!/bin/bash
# The daily chain: fetch -> filter -> one agent run per job -> applied.csv.
# Cron example (9am daily):  0 9 * * * /path/to/autoapply/run.sh >> /path/to/autoapply/logs/run.log 2>&1
# AGENT=claude (default) or AGENT=codex. ULTRON_PYTHON: the Python with playwright, mcp and pypdf installed.
set -euo pipefail
cd "$(dirname "$0")"
DIR="$PWD"
PYTHON="${ULTRON_PYTHON:-python3}"
AGENT="${AGENT:-claude}"
mkdir -p logs
exec 9> logs/.run.lock
flock -n 9 || { echo "$(date -Is) another run is still going"; exit 0; }

echo "$(date -Is) run start"
"$PYTHON" fetch.py
"$PYTHON" filter.py
MAX=$("$PYTHON" -c "import tomllib; print(tomllib.load(open('config.toml','rb'))['apply'].get('max_jobs_per_run', 5))")
./browser.sh

# Ultron is the agent's only browser; the agent gets no shell or file tools, so it can't send a form any other way.
cat > logs/mcp.json <<EOF
{"mcpServers": {"ultron": {"command": "$PYTHON", "args": ["$DIR/ultron_mcp.py", "$DIR"]}}}
EOF

count=0
# url: the job on the company's own site when the board names one, else on the board; Ultron falls back to the board's form.
while IFS=$'\t' read -r url company title platform location board; do
  # Boards that ask for an account before the form: no agent run, the job is logged for you to apply yourself.
  if [ "$platform" = "workday" ]; then
    "$PYTHON" mark.py --if-missing "$url" needs_human "Workday asks for an account on the company's site first: apply yourself at this link"
    continue
  fi
  # Past the cap, keep reading so later Workday jobs are still logged; other jobs wait for the next run.
  [ "$count" -ge "$MAX" ] && continue
  count=$((count + 1))
  playbook="playbooks/$platform.md"
  prompt="$(cat prompt.md)

$( [ -f "$playbook" ] && cat "$playbook" || true )

Job: $title at $company ($location)
URL: $url"
  echo "$(date -Is) $company | $title"
  log="logs/$(date +%Y%m%d-%H%M%S)-$count-${company//[^A-Za-z0-9._-]/_}.log"
  if [ "$AGENT" = "codex" ]; then
    codex exec --sandbox read-only --skip-git-repo-check \
      -c "mcp_servers.ultron.command=\"$PYTHON\"" -c "mcp_servers.ultron.args=[\"$DIR/ultron_mcp.py\", \"$DIR\"]" \
      "$prompt" < /dev/null > "$log" 2>&1 || true
  else
    claude -p "$prompt" --mcp-config logs/mcp.json --strict-mcp-config \
      --allowedTools "mcp__ultron" \
      --disallowedTools "Bash,Edit,Write,MultiEdit,NotebookEdit,WebFetch,WebSearch,Task" \
      --max-turns 40 --output-format json < /dev/null > "$log" 2>&1 || true
  fi
  # An agent that crashed or ran out of turns never logged the job: log it so it isn't retried blindly.
  "$PYTHON" mark.py --if-missing "$url" needs_human "Agent ended without logging; see $log"
done < jobs.txt
WAITING=$("$PYTHON" -c "import questions, pathlib; print(len(questions.load(pathlib.Path('.'))))")
[ "$WAITING" != "0" ] && echo "$(date -Is) $WAITING question(s) need your answer: run $PYTHON ask.py"
echo "$(date -Is) run end"
