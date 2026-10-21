#!/bin/bash
# Removes robotics-radar's two jobs from this Mac (robotics-radar.events, robotics-radar.register, and the single job
# robotics-radar of before 2026-10-21): the LaunchAgents and the deployed code. Keeps the runtime data
# (~/opt/robotics-radar/state/, chrome/), the venv and ~/.config/robotics-radar/. Then mark the jobs decommissioned on the
# dashboard (skill jobs-and-services §5). The shared calendar stays as it is (delete it in Google Calendar if wanted).
set -euo pipefail
DST="$HOME/opt/robotics-radar"
OLD=com.jeanlescut.robotics-radar
for NAME in "$OLD" "$OLD.events" "$OLD.register"; do
    launchctl bootout "gui/$UID/$NAME" 2>/dev/null || true
    for f in "$HOME/Library/LaunchAgents/$NAME.plist" "$DST/$NAME.plist"; do
        if [ -e "$f" ] || [ -L "$f" ]; then rm "$f"; echo "removed $f"; fi
    done
done
for f in "$DST/entrypoint.sh" "$DST/entrypoint.conf" "$DST/events.sh" "$DST/events.conf" "$DST/register.sh" "$DST/register.conf" "$DST/DEPLOYED"; do
    if [ -e "$f" ]; then rm "$f"; echo "removed $f"; fi
done
for d in src config doc data; do
    if [ -d "$DST/$d" ]; then rm -r "${DST:?}/$d"; echo "removed $DST/$d"; fi
done
echo "kept: $DST/state, $DST/chrome, $DST/.venv, ~/.config/robotics-radar"
