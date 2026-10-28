#!/bin/bash
# ~/opt/robotics-radar/register.sh: job robotics-radar.register (stage B, the private registration stage), for job-runner (separate project, ~/dev/job-runner).
# Source: src/register.sh; ../install.sh copies it there and the Mac's LaunchAgent com.jeanlescut.robotics-radar.register
# runs it every hour (and at login).
# Requirements:
#   - Mac only: the radar's headless Chrome, logged in to the user's Luma account (DESIGN.md §5)
#   - every hour: an event the user accepts in the shared calendar is registered within the hour (spots go fast)
#   - not when offline
#   - timeout 30 min, a claim against a run by hand
#   - writes (Todoist comments, Luma) only when the config says dry_run: false; Luma's last click also needs registration.submit: true
#   - PATH: launchd's has neither claude (~/.local/bin, drafts answers) nor gws (Homebrew)
#   - summary: the "registration:" line
#   - alert: red after 6 h without a success (register.conf)
. ~/opt/job-runner/lib.sh
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

jr_claim 30
jr_online || jr_skip "offline"

jr_execute 30 env PYTHONUTF8=1 .venv/bin/python src/stage_b/run.py --write
[ "$JR_RC" = 0 ] && jr_summary_grep 'registration:'
