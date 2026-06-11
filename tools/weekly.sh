#!/usr/bin/env bash
# Weekly research-agent job (launchd: com.paper.agent.weekly.plist, Sun 07:30).
# Runs the daily sync/fetch first, then asks Claude for a weekly synthesis +
# research-direction prompts. Needs claude headless (uses tokens).
set -e
ROOT="${PAPER_ROOT:-$HOME/Paper}"
cd "$ROOT"
PY="$(command -v python3)"
WK="$(date +%G-W%V)"
LOG="Research/weekly/${WK}.md"
mkdir -p Research/weekly

# backlog: resurface papers saved >14 days ago with zero highlights/notes
DAYLOG0="Daily/$(date +%Y-%m-%d).md"
printf '%b\n' "\n## 📚 积压重浮 $(date +%H:%M)\n" >> "$DAYLOG0"
"$PY" tools/backlog.py >> "$DAYLOG0" 2>&1 || true

# glossary: refresh the cross-paper concept MOC (only new concepts cost tokens)
"$PY" tools/glossary.py >> "$DAYLOG0" 2>&1 || true

# the 07:00 daily run already synced + fetched today; go straight to synthesis.
# Provider-agnostic: RESEARCH_AGENT_LLM=claude|codex (default claude).
AGENT="${RESEARCH_AGENT_LLM:-claude}"
DAYLOG="Daily/$(date +%Y-%m-%d).md"
if command -v "$AGENT" >/dev/null; then
  if [[ "$AGENT" == "codex" ]]; then
    codex exec --sandbox read-only "Read AGENTS.md, then write this week's research synthesis (what moved in my fields + 2-3 directions to consider) and save it to $LOG." >> "$DAYLOG" 2>&1 || \
      printf '%b\n' "(weekly digest skipped: codex failed)" >> "$DAYLOG"
  else
    claude -p "/research weekly" --permission-mode acceptEdits >> "$DAYLOG" 2>&1 || \
      printf '%b\n' "(weekly digest skipped: claude failed)" >> "$DAYLOG"
  fi
fi
