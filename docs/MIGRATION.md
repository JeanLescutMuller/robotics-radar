# Migration plan
1. Read local owner instructions: ~/gdrive/Personal/my-context/AGENTS_SHARED.md; robotics facts; GitHub task-management skill. Respect current rules if they supersede this historical handover.
2. Select Mac or VM and runtime. Confirm browser/network, credentials, API scopes and scheduler (launchd/cron/systemd). Do not store credentials in git.
3. Enumerate **all** calendars and Todoist Robotics project; reconcile existing entries against historical leads; verify reports of successful past writes. Calendar create failures were previously reported.
4. Implement collectors, URL canonicalization, fuzzy dedup, source tracking, timezone-aware normalization, scoring, task/calendar reconciliation, and notification gating.
5. Use persistent state e.g. SQLite, with event IDs, source URLs, snapshots, score history, external Calendar/Todoist IDs, last_checked, write log.
6. Test dry-run with duplicates, all-day placeholders, timezone DST, changed registration, failed writes, missing hours and repeated runs. Confirm permissions to Couple.
7. Enable mutations after review; verify readback and record audit trail. Schedule daily run with monthly six-month inventory and >=30-day announcement refresh **on every run**.
8. Decide notification destination with owner before enabling unattended notifications.
No runnable software, prior VM files or scheduler was created by ChatGPT. Do not present this repository as a deployed service.
