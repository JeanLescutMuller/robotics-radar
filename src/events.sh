#!/bin/bash
# ~/opt/robotics-radar/events.sh: job robotics-radar.events (stage A, the public stage), for job-runner (separate project, ~/dev/job-runner).
# Source: src/events.sh; ../install.sh copies it there and the Mac's LaunchAgent com.jeanlescut.robotics-radar.events
# runs it every hour (and at login).
# Requirements:
#   - Mac only (DESIGN.md §2); hourly tick (StartInterval 3600, and at login)
#   - one success per UTC day
#   - at most 3 failures per UTC day, an hour apart (the tick spaces them)
#   - not when offline
#   - timeout 60 min, shorter than the tick, but a claim anyway (a run by hand may overlap)
#   - writes (Todoist, the shared calendar) only when ~/.config/robotics-radar/config.yaml says dry_run: false
#   - PATH: launchd's has neither claude (~/.local/bin) nor gws (Homebrew)
#   - summary: the "plan:" line
#   - alert: red after 48 h without a success (events.conf; the Mac may sleep)
. ~/opt/job-runner/lib.sh
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

jr_claim 60
jr_skip_if SUCCESS day "ran today already (days start 00:00 UTC)"
jr_skip_if FAILURE day "3 failures today" 3
jr_online || jr_skip "offline"

jr_execute 60 env PYTHONUTF8=1 .venv/bin/python src/stage_a/run.py --write   # writes only when the config says dry_run: false
[ "$JR_RC" = 0 ] && jr_summary_grep 'plan:'
