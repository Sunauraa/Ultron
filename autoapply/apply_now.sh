#!/bin/bash
# Apply to one job with you in the conversation. When answers.md lacks something the form needs, the agent asks
# you, saves your reply to answers.md (add_answer) and fills it, instead of stopping with needs_info.
# Usage: ./apply_now.sh URL        (AGENT=claude only: Codex has no interactive MCP prompt here)
set -euo pipefail
cd "$(dirname "$0")"
DIR="$PWD"
PYTHON="${ULTRON_PYTHON:-python3}"
URL="${1:?usage: ./apply_now.sh URL}"
mkdir -p logs
./browser.sh
cat > logs/mcp-interactive.json <<EOF
{"mcpServers": {"ultron": {"command": "$PYTHON", "args": ["$DIR/ultron_mcp.py", "$DIR"], "env": {"ULTRON_INTERACTIVE": "1"}}}}
EOF
prompt="$(cat prompt.md)

I'm here in this conversation. When a required question has no answer in answers.md and is a fact about me,
don't log needs_info: ask me (all such questions at once, with the form's options), save each reply with
add_answer exactly as I give it, then fill it and continue.

URL: $URL"
exec claude "$prompt" --mcp-config logs/mcp-interactive.json --strict-mcp-config \
  --allowedTools "mcp__ultron" \
  --disallowedTools "Bash,Edit,Write,MultiEdit,NotebookEdit,WebFetch,WebSearch,Task"
