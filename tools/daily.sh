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

# Run at most once per day. Schedule this job at several times (07:00/13:00/20:00)
# so a laptop that was ASLEEP at one slot still catches a later one — the first
# successful run stamps the day and the rest become no-ops. ('--force' overrides.)
STAMP="Daily/.lastrun"
if [ "$(cat "$STAMP" 2>/dev/null)" = "$TODAY" ] && [ "${1:-}" != "--force" ]; then
  exit 0
fi

print "\n=== paper-agent run $(date) ===" >> "$LOG"

# 1+2  Zotero -> vault (idempotent; preserves user-written sections)
"$PY" tools/lit_note.py sync-all >> "$LOG" 2>&1
"$PY" tools/lit_note.py topics   >> "$LOG" 2>&1

# 3  fetch candidates -> Inbox/
print "\n## Fetched $(date +%H:%M)\n" >> "$LOG"
"$PY" tools/fetch.py >> "$LOG" 2>&1

# 4  auto-generate value cards + render the graph (provider-agnostic via tools/llm.py;
#    pick the agent with RESEARCH_AGENT_LLM=claude|codex, default claude).
AGENT="${RESEARCH_AGENT_LLM:-claude}"
if command -v "$AGENT" >/dev/null; then
  "$PY" tools/digest_cards.py >> "$LOG" 2>&1 || \
    print "(digest_cards skipped: $AGENT failed)" >> "$LOG"
fi
"$PY" tools/viz.py >> "$LOG" 2>&1 || true
echo "$TODAY" > "$STAMP"          # mark today done (core steps succeeded)

# 5  optional agentic reading plan
if [[ "${PAPER_AGENT_LLM:-0}" == "1" ]] && command -v "$AGENT" >/dev/null; then
  print "\n## Reading plan\n" >> "$LOG"
  if [[ "$AGENT" == "codex" ]]; then
    codex exec --sandbox read-only "Read AGENTS.md and today's Inbox/*.md stubs, then write a short prioritized reading plan grouped by my interest areas." >> "$LOG" 2>&1 || \
      print "(reading plan skipped: codex failed)" >> "$LOG"
  else
    claude -p "/papers digest" --permission-mode acceptEdits >> "$LOG" 2>&1 || \
      print "(reading plan skipped: claude failed)" >> "$LOG"
  fi
fi

print "\n=== done $(date) ===" >> "$LOG"
