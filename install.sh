#!/bin/bash
# Deploys robotics-radar on this Mac. Idempotent.
#   1. the committed HEAD -> ~/opt/robotics-radar/ (its runtime data state/ and chrome/ are never overwritten)
#   2. its Python: ~/opt/robotics-radar/.venv (requirements.txt), kept between deploys, rebuilt when requirements.txt changes
#   3. two jobs, each a job-runner entrypoint + dashboard settings, run every hour and at login by its LaunchAgent (RunAtLoad):
#        stage A  events.sh    job robotics-radar.events     com.jeanlescut.robotics-radar.events     (once a day: find events, the shared calendar)
#        stage B  register.sh  job robotics-radar.register   com.jeanlescut.robotics-radar.register   (every hour: register what the user accepted)
#   4. self-migration: the single job robotics-radar of before 2026-10-21 (entrypoint.sh, com.jeanlescut.robotics-radar) is removed
# Writes happen only when ~/.config/robotics-radar/config.yaml says dry_run: false (and, for Luma's last click, registration.submit: true).
# Needs: ~/.config/robotics-radar/config.yaml, task-management's Todoist token, gws logged in, /opt/anaconda3/bin/python3, Google Chrome.
#
# Usage: bash install.sh       Undo: bash uninstall.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DST="$HOME/opt/robotics-radar"
OLD=com.jeanlescut.robotics-radar        # the single job until 2026-10-21
JOBS=(events register)                    # src/<job>.sh → job robotics-radar.<job>
PY=/opt/anaconda3/bin/python3             # builds the venv

# -- 0. Checks ----------------------------------------------------------------------------------------------------
[ -f "$HOME/.config/robotics-radar/config.yaml" ] || { echo "missing ~/.config/robotics-radar/config.yaml (keys: config/config.example.yaml)"; exit 1; }
[ -f "$HOME/opt/job-runner/lib.sh" ] || echo "NOTE: job-runner is not installed (~/opt/job-runner/lib.sh missing): every check fails until it is"

# -- 1. Code ------------------------------------------------------------------------------------------------------
[ -z "$(git -C "$SRC" status --porcelain --untracked-files=no)" ] || echo "WARNING: uncommitted changes are NOT deployed"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
git -C "$SRC" archive HEAD | tar -x -C "$TMP"
RUNTIME=(state/ chrome/ logs/ .venv/ DEPLOYED); for j in "${JOBS[@]}"; do RUNTIME+=("$j.sh" "$j.conf" "$OLD.$j.plist"); done
EXCL=(); for x in "${RUNTIME[@]}"; do EXCL+=(--exclude="/$x"); done
mkdir -p "$DST/state"
rsync -a --delete "${EXCL[@]}" "$TMP/" "$DST/"

# -- 2. Python ----------------------------------------------------------------------------------------------------
if ! cmp -s "$DST/requirements.txt" "$DST/.venv/requirements.txt"; then
  "$PY" -m venv --clear "$DST/.venv"
  "$DST/.venv/bin/pip" install -q -r "$DST/requirements.txt" > "$TMP/pip.log" 2>&1 || { tail -5 "$TMP/pip.log"; exit 1; }
  cp "$DST/requirements.txt" "$DST/.venv/requirements.txt"
fi
"$DST/.venv/bin/python" -m py_compile "$DST"/src/*.py "$DST"/src/stage_*/*.py

echo "$(git -C "$SRC" rev-parse --short HEAD) $(date -Iseconds)" > "$DST/DEPLOYED"

# -- 3. Self-migration: the single job of before 2026-10-21 --------------------------------------------------------
launchctl bootout "gui/$UID/$OLD" 2>/dev/null || true
for f in "$HOME/Library/LaunchAgents/$OLD.plist" "$DST/$OLD.plist" "$DST/entrypoint.sh" "$DST/entrypoint.conf"; do
  if [ -e "$f" ] || [ -L "$f" ]; then rm "$f"; echo "removed the old job's $f"; fi
done

# -- 4. The jobs: real plists in ~/opt, symlinks in ~/Library/LaunchAgents ------------------------------------------
for j in "${JOBS[@]}"; do
  NAME=$OLD.$j; AGENT="$HOME/Library/LaunchAgents/$NAME.plist"
  cp "$TMP/src/$j.sh" "$DST/$j.sh"; cp "$TMP/src/$j.conf" "$DST/$j.conf"
  if [ -f "$HOME/opt/job-runner/put-conf.sh" ]; then
    bash "$HOME/opt/job-runner/put-conf.sh" "robotics-radar.$j" "$DST/$j.conf" || echo "WARNING: dashboard settings of robotics-radar.$j not sent"
  else echo "WARNING: job-runner not installed (~/opt/job-runner/put-conf.sh missing): dashboard settings not sent"; fi
  cat > "$DST/$NAME.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$NAME</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DST/$j.sh</string></array>
  <key>StartInterval</key><integer>3600</integer><key>RunAtLoad</key><true/><key>AbandonProcessGroup</key><true/>
</dict></plist>
PLIST
  plutil -lint "$DST/$NAME.plist" >/dev/null
  mkdir -p "$(dirname "$AGENT")"
  ln -sfn "$DST/$NAME.plist" "$AGENT"
  launchctl bootout "gui/$UID/$NAME" 2>/dev/null || true
  launchctl bootstrap "gui/$UID" "$AGENT"
done
C="$HOME/.config/robotics-radar/config.yaml"
echo "deployed $(cat "$DST/DEPLOYED"); jobs loaded: ${JOBS[*]}; $(grep -q "^dry_run: false" "$C" && echo "WRITES ON (Todoist, the shared calendar)" || echo "dry-run: plans only"); Luma last click: $(grep -q "^  submit: true" "$C" && echo ON || echo "off (forms filled, not sent)")"
