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

# the 07:00 daily run already synced + fetched today; go straight to synthesis.
# Provider-agnostic: RESEARCH_AGENT_LLM=claude|codex (default claude).
AGENT="${RESEARCH_AGENT_LLM:-claude}"
DAYLOG="Daily/$(date +%Y-%m-%d).md"
if command -v "$AGENT" >/dev/null; then
  if [[ "$AGENT" == "codex" ]]; then
    codex exec --sandbox read-only "Read AGENTS.md, then write this week's research synthesis (what moved in my fields + 2-3 directions to consider) and save it to $LOG." >> "$DAYLOG" 2>&1 || \
      print "(weekly digest skipped: codex failed)" >> "$DAYLOG"
  else
    claude -p "/research weekly" --permission-mode acceptEdits >> "$DAYLOG" 2>&1 || \
      print "(weekly digest skipped: claude failed)" >> "$DAYLOG"
  fi
fi
