#!/usr/bin/env bash
# Install (or remove) the scheduled daily + weekly jobs.
#   macOS  → launchd  (daily 07:00, weekly Sun 07:30)
#   Linux  → prints a cron snippet to add yourself
#
#   bash tools/install_schedule.sh             # install
#   bash tools/install_schedule.sh --uninstall # remove
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAILY="com.research-agent.daily"
WEEKLY="com.research-agent.weekly"
LA="$HOME/Library/LaunchAgents"

# Build a sane PATH for the headless job (launchd starts with a minimal one).
binpath() { command -v "$1" >/dev/null 2>&1 && dirname "$(command -v "$1")" || true; }
PATHVAL="$(binpath python3):$(binpath claude):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

if [ "$(uname)" != "Darwin" ]; then
  cat <<EOF
This installer targets macOS (launchd). On Linux, add to 'crontab -e':

  0 7 * * *   cd "$ROOT" && PAPER_AGENT_LLM=1 /bin/bash tools/daily.sh
  30 7 * * 0  cd "$ROOT" && /bin/bash tools/weekly.sh
EOF
  exit 0
fi

if [ "${1:-}" = "--uninstall" ]; then
  for L in "$DAILY" "$WEEKLY"; do
    launchctl unload "$LA/$L.plist" 2>/dev/null
    rm -f "$LA/$L.plist" && echo "removed $L"
  done
  exit 0
fi

mkdir -p "$LA" "$ROOT/Daily"

emit_plist() {  # $1 label  $2 script  $3 StartCalendarInterval-XML
  local label="$1" script="$2" cal="$3"
  cat > "$LA/$label.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$ROOT/tools/$script</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>PAPER_ROOT</key><string>$ROOT</string>
    <key>ZOTERO_DIR</key><string>${ZOTERO_DIR:-$HOME/Zotero}</string>
    <key>PATH</key><string>$PATHVAL</string>
    <key>PAPER_AGENT_LLM</key><string>1</string>
  </dict>
  <key>StartCalendarInterval</key>$cal
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$ROOT/Daily/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$ROOT/Daily/launchd.err.log</string>
</dict></plist>
EOF
  launchctl unload "$LA/$label.plist" 2>/dev/null
  launchctl load "$LA/$label.plist" && echo "installed $label"
}

# Daily at 07:00, 13:00, 20:00 — a laptop asleep at one slot catches a later one;
# daily.sh runs at most once per day (stamp file), so extra slots are no-ops.
emit_plist "$DAILY" daily.sh '<array>
    <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
  </array>'
emit_plist "$WEEKLY" weekly.sh '<dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>30</integer><key>Weekday</key><integer>0</integer></dict>'

cat <<EOF

Scheduled:
  • $DAILY  — every day at 07:00 / 13:00 / 20:00 (runs once; catches a laptop that
              was asleep at an earlier slot) → tools/daily.sh
  • $WEEKLY — Sundays 07:30 → tools/weekly.sh
Logs: $ROOT/Daily/launchd.{out,err}.log
Remove with:  bash tools/install_schedule.sh --uninstall
EOF
