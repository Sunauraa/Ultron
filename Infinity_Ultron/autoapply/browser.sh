#!/bin/bash
# Keep one Chrome running with the job-hunting profile and a local debugging port, so Ultron can drive it
# and filled forms stay open for you after the agent exits. Safe to run again: it does nothing if Chrome is up.
# The debugging port lets any program on this computer control this browser, so use this profile only for applying.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${ULTRON_PORT:-9222}"
PYTHON="${ULTRON_PYTHON:-python3}"

if curl -s -m 2 "http://127.0.0.1:$PORT/json/version" > /dev/null; then
  exit 0
fi

PROFILE=$("$PYTHON" -c "import tomllib; print(tomllib.load(open('config.toml','rb'))['apply'].get('browser_profile','browser-profile'))")
HEADLESS=$("$PYTHON" -c "import tomllib; print(tomllib.load(open('config.toml','rb'))['apply'].get('headless', False))")
CHROME="${CHROME:-}"
if [ -z "$CHROME" ]; then
  for c in google-chrome google-chrome-stable chromium chromium-browser "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
    if command -v "$c" > /dev/null 2>&1 || [ -x "$c" ]; then CHROME="$c"; break; fi
  done
fi
if [ -z "$CHROME" ]; then  # fall back to Playwright's own Chromium
  CHROME=$("$PYTHON" -c "from playwright.sync_api import sync_playwright as s; p = s().start(); print(p.chromium.executable_path); p.stop()")
fi

ARGS=(--user-data-dir="$PWD/$PROFILE" --remote-debugging-port="$PORT" --remote-debugging-address=127.0.0.1 --no-first-run --no-default-browser-check)
[ "$HEADLESS" = "True" ] && ARGS+=(--headless=new)
nohup "$CHROME" "${ARGS[@]}" about:blank > /dev/null 2>&1 &
for _ in $(seq 1 30); do
  curl -s -m 2 "http://127.0.0.1:$PORT/json/version" > /dev/null && exit 0
  sleep 1
done
echo "Chrome did not start on port $PORT" >&2
exit 1
