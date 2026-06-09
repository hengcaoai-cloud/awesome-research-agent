#!/bin/zsh
# Daily research-agent job. Run by launchd (com.paper.agent.plist) or by hand.
#   1. sync new/changed Zotero papers into the Obsidian vault
#   2. rebuild topic MOCs
#   3. fetch relevant new papers (arXiv freshness + S2 recommendations) into Inbox/
#   4. (PAPER_AGENT_LLM=1) let Claude write a prioritized reading plan into Daily/
# Steps 1-3 are free and need no auth; step 4 uses tokens.

set -e
ROOT="${PAPER_ROOT:-$HOME/Paper}"
cd "$ROOT"
PY="$(command -v python3)"
TODAY="$(date +%Y-%m-%d)"
LOG="Daily/${TODAY}.md"
mkdir -p Daily

print "\n=== paper-agent run $(date) ===" >> "$LOG"

# 1+2  Zotero -> vault (idempotent; preserves user-written sections)
"$PY" tools/lit_note.py sync-all >> "$LOG" 2>&1
"$PY" tools/lit_note.py topics   >> "$LOG" 2>&1

# 3  fetch candidates -> Inbox/
print "\n## Fetched $(date +%H:%M)\n" >> "$LOG"
"$PY" tools/fetch.py >> "$LOG" 2>&1

# 4  auto-generate value cards (problem/innovation/directions) for the new batch,
#    then render the interactive knowledge graph — so cards are ready every day.
if command -v claude >/dev/null; then
  "$PY" tools/digest_cards.py >> "$LOG" 2>&1 || \
    print "(digest_cards skipped: claude headless failed)" >> "$LOG"
fi
"$PY" tools/viz.py >> "$LOG" 2>&1 || true

# 5  optional agentic reading plan
if [[ "${PAPER_AGENT_LLM:-0}" == "1" ]] && command -v claude >/dev/null; then
  print "\n## Reading plan\n" >> "$LOG"
  claude -p "/papers digest" --permission-mode acceptEdits >> "$LOG" 2>&1 || \
    print "(papers digest skipped: claude headless failed)" >> "$LOG"
fi

print "\n=== done $(date) ===" >> "$LOG"
