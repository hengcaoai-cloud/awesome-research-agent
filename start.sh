#!/usr/bin/env bash
# 🚀 One-command launch.
#   First run  → checks prerequisites + builds your notes from Zotero (setup).
#   Every run  → fetches today's papers, generates value cards, opens the graph.
#
#   bash start.sh                 # do everything and open http://127.0.0.1:8765
#   PORT=9000 bash start.sh       # custom port
#   bash start.sh --setup         # force re-run first-time setup
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PY="$(command -v python3 || true)"
export ZOTERO_DIR="${ZOTERO_DIR:-$HOME/Zotero}"
PORT="${PORT:-8765}"
AGENT="${RESEARCH_AGENT_LLM:-claude}"

say() { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }

[ -z "$PY" ] && { echo "✗ Python 3.9+ is required."; exit 1; }

# 1) First-time setup (or --setup): verify prerequisites + build notes from Zotero.
if [ "${1:-}" = "--setup" ] || ! ls Literature/*.md >/dev/null 2>&1; then
  say "First-time setup"
  bash tools/setup.sh || exit 1
fi

# 2) Fetch today's papers (skip if already fetched today).
TODAY="$(date +%Y-%m-%d)"
LAST="$("$PY" -c "import json;print(json.load(open('Inbox/.last_fetch.json')).get('date',''))" 2>/dev/null || true)"
if [ "$LAST" != "$TODAY" ]; then
  say "Fetching today's papers"
  "$PY" tools/fetch.py >/dev/null 2>&1 && echo "  done." || echo "  (fetch skipped)"
else
  echo "  Today's papers already fetched."
fi

# 3) Value cards (needs the agent CLI). Run in the background so the graph opens now.
if command -v "$AGENT" >/dev/null 2>&1; then
  say "Generating value cards via $AGENT (in background)"
  ( "$PY" tools/digest_cards.py >/dev/null 2>&1 && echo "  ✓ value cards ready — refresh the page." ) &
else
  echo "  (no '$AGENT' CLI found — skipping value cards; the graph still works)"
fi

# 4) Launch the interactive knowledge graph (opens your browser; Ctrl-C to stop).
say "Opening the knowledge graph at http://127.0.0.1:$PORT  (Ctrl-C to stop)"
exec "$PY" tools/viz.py --serve --port "$PORT"
