#!/bin/zsh
# Weekly research-agent job (launchd: com.paper.agent.weekly.plist, Sun 07:30).
# Runs the daily sync/fetch first, then asks Claude for a weekly synthesis +
# research-direction prompts. Needs claude headless (uses tokens).
set -e
ROOT="${PAPER_ROOT:-$HOME/Paper}"
cd "$ROOT"
WK="$(date +%G-W%V)"
LOG="Research/weekly/${WK}.md"
mkdir -p Research/weekly

# the 07:00 daily run already synced + fetched today; go straight to synthesis
if command -v claude >/dev/null; then
  claude -p "/research weekly" --permission-mode acceptEdits >> "Daily/$(date +%Y-%m-%d).md" 2>&1 || \
    print "(weekly digest skipped: claude headless failed)" >> "Daily/$(date +%Y-%m-%d).md"
fi
