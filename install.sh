#!/bin/bash
# Deploys robotics-radar on this Mac. Idempotent.
#   1. the committed HEAD -> ~/opt/robotics-radar/ (its runtime data state/ and chrome/ are never overwritten)
#   2. the job: ~/opt/robotics-radar/entrypoint.sh (copy of src/entrypoint.sh, for job-runner) and its dashboard settings
#      entrypoint.conf (sent to job-runner's dashboard by put-conf.sh), run every hour and at login by the LaunchAgent
#      com.jeanlescut.robotics-radar (RunAtLoad: one check now)
# Phase 2 (DESIGN.md §7): run.py only plans; nothing is written to Todoist, Calendar or Gmail.
# Needs: ~/.config/robotics-radar/config.yaml, task-management's Todoist token, gws logged in, /opt/anaconda3/bin/python3 (PyYAML).
#
# Usage: bash install.sh       Undo: bash uninstall.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DST="$HOME/opt/robotics-radar"
NAME=com.jeanlescut.robotics-radar
AGENT="$HOME/Library/LaunchAgents/$NAME.plist"
PY=/opt/anaconda3/bin/python3

# -- 0. Checks ----------------------------------------------------------------------------------------------------
[ -f "$HOME/.config/robotics-radar/config.yaml" ] || { echo "missing ~/.config/robotics-radar/config.yaml (keys: config/config.example.yaml)"; exit 1; }
"$PY" -c 'import yaml' || { echo "$PY has no PyYAML"; exit 1; }
[ -f "$HOME/opt/job-runner/lib.sh" ] || echo "NOTE: job-runner is not installed (~/opt/job-runner/lib.sh missing): every check fails until it is"

# -- 1. Code ------------------------------------------------------------------------------------------------------
[ -z "$(git -C "$SRC" status --porcelain --untracked-files=no)" ] || echo "WARNING: uncommitted changes are NOT deployed"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
git -C "$SRC" archive HEAD | tar -x -C "$TMP"
RUNTIME=(state/ chrome/ logs/ entrypoint.sh entrypoint.conf DEPLOYED "$NAME.plist")
EXCL=(); for x in "${RUNTIME[@]}"; do EXCL+=(--exclude="/$x"); done
mkdir -p "$DST/state"
rsync -a --delete "${EXCL[@]}" "$TMP/" "$DST/"
cp "$TMP/src/entrypoint.sh" "$DST/entrypoint.sh"
cp "$TMP/src/entrypoint.conf" "$DST/entrypoint.conf"
if [ -f "$HOME/opt/job-runner/put-conf.sh" ]; then
  bash "$HOME/opt/job-runner/put-conf.sh" robotics-radar "$DST/entrypoint.conf" || echo "WARNING: dashboard settings not sent"
else echo "WARNING: job-runner not installed (~/opt/job-runner/put-conf.sh missing): dashboard settings not sent"; fi
"$PY" -m py_compile "$DST"/src/*.py
echo "$(git -C "$SRC" rev-parse --short HEAD) $(date -Iseconds)" > "$DST/DEPLOYED"

# -- 2. The job's trigger: real plist in ~/opt, symlink in ~/Library/LaunchAgents ----------------------------------
cat > "$DST/$NAME.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$NAME</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DST/entrypoint.sh</string></array>
  <key>StartInterval</key><integer>3600</integer><key>RunAtLoad</key><true/><key>AbandonProcessGroup</key><true/>
</dict></plist>
PLIST
plutil -lint "$DST/$NAME.plist" >/dev/null
mkdir -p "$(dirname "$AGENT")"
ln -sfn "$DST/$NAME.plist" "$AGENT"
launchctl bootout "gui/$UID/$NAME" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$AGENT"
echo "deployed $(cat "$DST/DEPLOYED"); job $NAME loaded (dry-run: plans only)"
