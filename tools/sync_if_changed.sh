#!/usr/bin/env bash
# Auto-sync: regenerate Literature notes from Zotero ONLY when the library changed
# (a new paper was added/removed). Cheap to run often — it just reads one count.
# Triggered by launchd (StartInterval + WatchPaths on zotero.sqlite); see
# tools/install_schedule.sh.
set -u
ROOT="${PAPER_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"
PY="$(command -v python3 || true)"
[ -z "$PY" ] && exit 0
export ZOTERO_DIR="${ZOTERO_DIR:-$HOME/Zotero}"
STATE="Inbox/.zotero_seen"
LOG="Daily/sync.log"
mkdir -p Inbox Daily

# Fingerprint of the library (read-only): item count + most-recent dateAdded.
FP="$("$PY" - <<'PY' 2>/dev/null || true
import os, sqlite3
p = os.path.join(os.path.expanduser(os.environ.get("ZOTERO_DIR", "~/Zotero")), "zotero.sqlite")
try:
    con = sqlite3.connect(f"file:{p}?immutable=1", uri=True)
    n, last = con.execute("select count(*), coalesce(max(dateAdded),'') from items").fetchone()
    print(f"{n}:{last}")
except Exception:
    pass
PY
)"

[ -z "$FP" ] && exit 0                      # Zotero DB unreadable right now — skip
[ "$FP" = "$(cat "$STATE" 2>/dev/null)" ] && exit 0   # nothing new — fast no-op

printf '\n=== auto-sync %s (library changed) ===\n' "$(date)" >> "$LOG"
"$PY" tools/lit_note.py sync-all >> "$LOG" 2>&1 && \
"$PY" tools/lit_note.py topics   >> "$LOG" 2>&1 && \
echo "$FP" > "$STATE"
