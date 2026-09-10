#!/bin/bash
# Nightly model-backed re-analysis of stored stories.
#
# Run by launchd (com.gsid.reanalyze). Deliberately conservative: it is
# unattended, so it bounds itself in TIME as well as story count and exits
# quietly when anything is missing rather than failing loudly every night.
#
# Disable with:  launchctl unload ~/Library/LaunchAgents/com.gsid.reanalyze.plist
set -uo pipefail

PROJECT="/Users/gauravshukla/Documents/Global security news"
KEY_FILE="$HOME/.groq_key"
PYTHON="/opt/anaconda3/bin/python"
LOG="$PROJECT/logs/reanalyze.log"

cd "$PROJECT" || exit 0

stamp() { date "+%Y-%m-%d %H:%M:%S"; }

# No key means the operator has not opted in (or revoked it). Not an error.
if [[ ! -s "$KEY_FILE" ]]; then
  echo "$(stamp) skipped: no key at $KEY_FILE" >> "$LOG"
  exit 0
fi

# Strip whitespace: a trailing newline from pbpaste produces a 401 that looks
# exactly like a bad key.
KEY="$(tr -d '[:space:]' < "$KEY_FILE")"

# Keep the log from growing without bound (roughly 2000 lines).
if [[ -f "$LOG" ]] && [[ $(wc -l < "$LOG") -gt 2000 ]]; then
  tail -n 500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

echo "$(stamp) starting nightly re-analysis" >> "$LOG"

GSID_AI_PROVIDER=openai \
GSID_OPENAI_BASE_URL="https://api.groq.com/openai/v1" \
OPENAI_API_KEY="$KEY" \
GSID_OPENAI_MODEL="openai/gpt-oss-120b" \
"$PYTHON" run.py --reanalyze \
    --limit 400 \
    --max-seconds 2700 \
    --only-provider heuristic \
    >> "$LOG" 2>&1

echo "$(stamp) finished (exit $?)" >> "$LOG"
exit 0
