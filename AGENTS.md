# robotics-radar: rules for agents

Finds robotics and Physical AI events in Zürich/Switzerland for the next six months, puts them in Todoist and the Couple calendar, and registers the user for free ones. **State (2026-10-20): design only, no code yet**; ChatGPT's scheduled task still does discovery until phase 3 of `DESIGN.md`.

Read before working: `REQUIREMENTS.md` (what the user gets), `DESIGN.md` (what we build, the phases), `doc/SOURCES.md` (where events come from), `data/historical-events.json` (ChatGPT's leads, unverified).

## Rules

- **Public repo** (user, 2026-10-20: stays public). Never commit a calendar ID, a Todoist ID, an email address, form answers, tokens, cookies, the Chrome profile, Calendar contents or Todoist exports. Real values live in `~/.config/robotics-radar/config.yaml` (chmod 600); `config/config.example.yaml` holds placeholders only.
- **Dry-run by default** until a phase's writes are tested; every Calendar or Todoist write is read back.
- **Never duplicate** an event in any visible calendar, or an event task in Todoist (`REQUIREMENTS.md` Calendar, Todoist).
- **Registration**: only free events, score ≥75, registration group "auto", or "ask first" after the user's ok (`DESIGN.md` §5). Never pay, never create an account, never type a password, never bypass a CAPTCHA: hand it to the user as a Todoist task.
- **Notifications are not built** (user, 2026-10-20): they wait for `~/dev/alerting` (Todoist task "Send the radar's notifications through alerting"). Do not add another channel.
- Event tasks are the user's: no `agent`/`claude`/`chatgpt` labels on them, never complete or delete them.
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
