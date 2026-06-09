#!/usr/bin/env bash
# Guided first-time setup for the Research Agent.
# Checks prerequisites, verifies Zotero access, and builds your notes from Zotero.
# Safe to re-run (idempotent).

set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$(command -v python3 || true)"
ZOTERO_DIR="${ZOTERO_DIR:-$HOME/Zotero}"

say()  { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }
err()  { printf "  \033[31m✗\033[0m %s\n" "$*"; }

say "Research Agent setup  (root: $ROOT)"

# ---- 1. Python ------------------------------------------------------------
if [ -z "$PY" ]; then
  err "python3 not found. Install Python 3.9+ and re-run."; exit 1
fi
ok "python3: $("$PY" --version 2>&1)"

# ---- 2. Claude Code (optional but recommended) ----------------------------
if command -v claude >/dev/null 2>&1; then
  ok "Claude Code: $(command -v claude)"
else
  warn "Claude Code CLI not found. The free parts (fetch, sync, graph) still work,"
  warn "but Q&A, value cards and deep reads need it → https://www.anthropic.com/claude-code"
fi

# ---- 3. Zotero database ---------------------------------------------------
DB="$ZOTERO_DIR/zotero.sqlite"
if [ -f "$DB" ]; then
  ok "Zotero DB: $DB"
else
  err "zotero.sqlite not found at $DB"
  warn "Set ZOTERO_DIR to your Zotero data folder and re-run, e.g.:"
  warn "    ZOTERO_DIR=\"\$HOME/Zotero\" bash tools/setup.sh"
  exit 1
fi
export ZOTERO_DIR

# ---- 4. Verify read-only access ------------------------------------------
say "Verifying read-only Zotero access"
if "$PY" tools/zotero_read.py stats; then
  ok "Zotero is readable (read-only, immutable)."
else
  err "Could not read the Zotero DB."; exit 1
fi

# ---- 5. Create vault folders ---------------------------------------------
say "Creating vault folders"
for d in Literature Topics Inbox Daily Research; do
  mkdir -p "$d"; touch "$d/.gitkeep"
done
ok "Literature/ Topics/ Inbox/ Daily/ Research/ ready"

# ---- 6. Build notes from Zotero ------------------------------------------
say "Building literature notes + topic maps from Zotero (idempotent)"
"$PY" tools/lit_note.py sync-all
"$PY" tools/lit_note.py topics
ok "Notes written to Literature/ and Topics/"

# ---- 7. Connector check (optional) ---------------------------------------
say "Checking the Zotero connector (only needed to SAVE papers)"
if curl -s -m 4 http://localhost:23119/connector/ping >/dev/null 2>&1; then
  ok "Connector is reachable — saving papers to Zotero will work."
else
  warn "Connector not reachable. To save papers later, enable:"
  warn "  Zotero → Settings → Advanced → 'Allow other applications … to communicate with Zotero'"
fi

# ---- Done -----------------------------------------------------------------
say "Setup complete 🎉  Next steps:"
cat <<EOF
  1. Fetch today's papers:        python3 tools/fetch.py
  2. Auto-fill value cards:       python3 tools/digest_cards.py     (needs Claude Code)
  3. Open the knowledge graph:    python3 tools/viz.py --serve
  4. Talk to the agent:           cd "$ROOT" && claude   then try  /papers  or  /ask ...
  5. (optional) daily automation: bash tools/install_schedule.sh    (macOS)

  Tune what it surfaces by editing .interests.yaml
EOF
