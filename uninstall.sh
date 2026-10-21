#!/bin/bash
# Removes robotics-radar's job from this Mac: the LaunchAgent and the deployed code. Keeps the runtime data
# (~/opt/robotics-radar/state/, chrome/) and ~/.config/robotics-radar/. Then mark the job decommissioned on the
# dashboard (skill jobs-and-services §5).
set -euo pipefail
DST="$HOME/opt/robotics-radar"
NAME=com.jeanlescut.robotics-radar
launchctl bootout "gui/$UID/$NAME" 2>/dev/null || true
for f in "$HOME/Library/LaunchAgents/$NAME.plist" "$DST/$NAME.plist" "$DST/entrypoint.sh" "$DST/entrypoint.conf" "$DST/DEPLOYED"; do
    if [ -e "$f" ] || [ -L "$f" ]; then rm "$f"; echo "removed $f"; fi
done
for d in src config doc data; do
    if [ -d "$DST/$d" ]; then rm -r "${DST:?}/$d"; echo "removed $DST/$d"; fi
done
echo "kept: $DST/state, $DST/chrome, ~/.config/robotics-radar"
