# robotics-radar: rules for agents

Two stages (user, 2026-10-21): **stage A** (`src/stage_a/`, job `robotics-radar.events`, daily) finds robotics and Physical AI events near Zürich for the next six months and keeps **the shared calendar** up to date (and the event tasks in Todoist); **stage B** (`src/stage_b/`, job `robotics-radar.register`, hourly) registers the user for the events they **accepted** in it. They meet only through the shared calendar (and B reads A's `state/radar.sqlite` to find an event's task). State (2026-10-21): both run; B's last click on Luma is on (`registration.submit: true`, user, 2026-10-21).

Read before working: `REQUIREMENTS.md` (what the user gets), `DESIGN.md` (what we build, the phases), `doc/SOURCES.md` (where events come from), `data/historical-events.json` (ChatGPT's leads, unverified).

## Rules

- **Public repo** (user, 2026-10-20: stays public). Never commit a calendar ID, a Todoist ID, an email address, form answers, tokens, cookies, the Chrome profile, Calendar contents or Todoist exports. Real values live in `~/.config/robotics-radar/config.yaml` (chmod 600); `config/config.example.yaml` holds placeholders only.
- **The shared calendar is public**: an entry holds only the event's own facts (`stage_a/write.py` `calendar_body`): never a score, a Todoist link, the user's state, or text from a Todoist task.
- **Dry-run by default** until a phase's writes are tested; every Calendar or Todoist write is read back.
- **Never duplicate** an event in any visible calendar, or an event task in Todoist (`REQUIREMENTS.md` Calendar, Todoist).
- **Registration**: only events the user accepted in the calendar (user, 2026-10-21), free, registration group "auto", or "ask first" after the user's "ok" (`DESIGN.md` §5). Never pay, never create an account, never type a password, never bypass a CAPTCHA: hand it to the user as a Todoist task.
- **Notifications are not built** (user, 2026-10-20): they wait for `~/dev/alerting` (Todoist task "Send the radar's notifications through alerting"). Do not add another channel.
- Event tasks: only stage B makes one, for an event the user accepted and the radar could not register by itself (user, 2026-10-21). They are the user's: no `agent`/`claude`/`chatgpt` labels, never complete them; delete the task of an event that is over.
- Chrome: headless, own data folder `~/opt/robotics-radar/chrome/` (skill `chrome-headless`).
- Scheduled job: skill `jobs-and-services`, through job-runner, model `~/dev/job-applications/auto-job-apply/`.

## Vocabulary

| Word | Meaning | Never say |
|---|---|---|
| **event** | one dated talk, meetup, workshop, hackathon or conference | listing, lead (except ChatGPT's file) |
| **run** | one daily pass of the radar: discover → merge → score → Calendar/Todoist → register | scan, sweep |
| **score** | 0–100, how worth it an event is for the user (`REQUIREMENTS.md` Scoring) | rating, rank |
| **event task** | the one Todoist task per event, in Professional › Robotics, `Subsection: Events` | ticket, card |
| **safety date** | an event task's due date: the day to act (register, apply), never the event's date | deadline (reserved for the organiser's published cutoff) |
| **registration** | signing the user up for an event (register, request admission, join a waitlist) | booking, enrolment |
| **registration group** | auto / ask first / never: what the radar may do for an event (`DESIGN.md` §5) | tier, level |
| **stage A** / **stage B** | A: find events, keep the shared calendar up to date. B: register the user for the events they accepted | phase (phases are the migration steps, `DESIGN.md` §7) |
| **shared calendar** | the public Google calendar "Robotics & Physical AI events near Zürich" that stage A fills, shared by a QR code | public calendar, feed |
| **accept** | the user's "Yes" on the invitation of a shared-calendar entry in their own calendar: stage B's only trigger | RSVP, opt in |

## Commands

```bash
cd ~/dev/robotics-radar
.venv/bin/python src/stage_a/run.py --no-search > state/run.log 2>&1   # stage A, dry-run by hand (state/ here); report state/run_report.md
.venv/bin/python src/stage_b/run.py > state/register.log 2>&1          # stage B, dry-run; report state/register_report.md
.venv/bin/python src/stage_a/qr.py                                     # the shared calendar's QR code (a PNG in the Drive)
bash install.sh                                                        # deploy HEAD to ~/opt/robotics-radar, load both jobs
```

The job's own state and reports: `~/opt/robotics-radar/state/` (never edited by hand). Claude cost per run: the report's first table.
