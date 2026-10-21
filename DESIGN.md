# robotics-radar: design

What we build to meet `REQUIREMENTS.md`, and the phases of the migration from ChatGPT. Written 2026-10-20 from ChatGPT's handover (this repo's first commits) and the live Todoist section Professional › Robotics (read 2026-10-20: 40+ open event tasks, about half of them a registration still to do).

| | |
|---|---|
| Command | `~/opt/robotics-radar/entrypoint.sh` (job `robotics-radar`), started by an hourly launchd tick; does one run a day |
| Reads | the sources in `doc/SOURCES.md`; Google Calendar (all visible calendars); Todoist Professional › Robotics; Gmail (confirmation emails); `~/.config/robotics-radar/config.yaml` |
| Writes | `~/opt/robotics-radar/state/radar.sqlite`, `~/opt/robotics-radar/logs/`; Couple calendar events; event tasks; registrations in the user's name |
| Acts | yes: registers the user for free events (§5); Claude tokens for scoring and forms only (§3) |
| Consumed by | the user: Todoist "My day", the Couple calendar |

## 1. The run

```
launchd tick (hourly, Mac) ─► entrypoint.sh (job-runner: once a day, skip if done)
  │
  ├─ 1 discover      Python: Luma, Voxel51, ETH/UZH talks, DARE, Meetup, Eventbrite…   (doc/SOURCES.md)
  │                  claude -p: one broad web search a week, for new organisers
  ├─ 2 merge         Python + SQLite: canonical URL, normalised title/date/organiser
  ├─ 3 score         claude -p: only new or changed events
  ├─ 4 reconcile     Python: Calendar (gws CLI), Todoist (API); dry-run, read back
  ├─ 5 register      Python + headless Chrome (own profile); check the confirmation email
  └─ 6 notify        NOT BUILT: waits for ~/dev/alerting (§9)
```

## 2. Where it runs: the Mac (user, 2026-10-20)

**Choice:** the MacBook, like auto-job-apply. **Reason:** registration needs a Chrome profile logged in to Luma, Eventbrite, Meetup…, a user who can solve a CAPTCHA or log in again, and reading the site's confirmation code from Gmail: all already working on the Mac (`~/dev/job-applications/step6_sending/`, `common/chrome.py`). **Rejected:** the VM: always on, but no logged-in Chrome, no user at the screen; would mean rebuilding all three. A daily run that slips a few hours while the Mac sleeps costs nothing: safety dates are days ahead.

## 3. Script first, Claude only for judgement

**Choice:** a Python program does everything that is the same every day; `claude -p` is called only for scoring a new or changed event, the weekly broad search, and reading an unfamiliar registration form. **Reason:** the user has few tokens; ChatGPT re-read every source every day. **[assumed]** 5–20 new or changed events a day; to measure in phase 2.

| Step | Who | Why |
|---|---|---|
| discover known sources | Python (HTTP, the pages' own JSON where they have it) | cheap, deterministic |
| broad web search | `claude -p`, weekly | finds organisers no list knows |
| merge | Python + SQLite | must be exact and repeatable |
| score | `claude -p` | judgement on the user's goals (Drive `facts/robotics.md`) |
| Calendar, Todoist | Python: `gws`, Todoist REST API | readback, no duplicates |
| register | Python + Playwright on headless Chrome; `claude -p` for a form it does not know | the model of job-applications step 6 |

## 4. State: one SQLite file

`~/opt/robotics-radar/state/radar.sqlite`, written in one transaction per run. Every table starts with `ts`, `dt`.

| Table | Holds |
|---|---|
| `events` | one row per event: the normalised fields of `REQUIREMENTS.md` Normalize, its score, its registration group |
| `sources` | every URL an event was seen at, first/last seen |
| `snapshots` | the page text at each check, to see what changed (date, venue, full, waitlist) |
| `links` | the event's Todoist task id and Calendar event id |
| `registrations` | each try: group, form fields sent, result, the confirmation email's id, a screenshot path |
| `writes` | every external write and its readback |

First fill (phase 1): from Todoist Professional › Robotics, the calendars and `data/historical-events.json`, so the existing 40+ event tasks are matched, never duplicated.

## 5. Registration: three groups (user, 2026-10-20: free events only)

| Group | When | What the radar does |
|---|---|---|
| **auto** | free (price 0 on the official page), registration open (or a waitlist), score ≥75, the form asks only for known answers (name, email, company/role, LinkedIn), no new account | registers; waits for the confirmation email; the event task becomes `: confirm attendance` or `: check application status`; its Couple event says "registered" |
| **ask first** | as auto, but the form has a free-text question ("why do you want to join?") | writes the answers (skill `writing-for-others`) in a comment on the event task, retitles it `: approve my answers`; the user's "ok" in a comment → the next run submits |
| **never** | paid, a new account needed, a password or a CAPTCHA, invitation code, unclear eligibility | event task only, as today |

- Form email: the `form.email` value in `~/.config/robotics-radar/config.yaml` (the user's `+events` address, so a Gmail filter can label the replies; user, 2026-10-20). The site's login (Luma's account) stays whatever the user logged in with.
- Logged in once: the user logs in to Luma, Eventbrite and Meetup in `~/opt/robotics-radar/chrome/` in a visible window (skill `chrome-headless`), then headless forever; a login page later = an event task for the user, never a password typed.
- Trust ramp: the first two weeks every auto registration stops before the final click and saves a screenshot; the user looks at them; then submission is switched on (one line in `entrypoint.sh`, like auto-job-apply).
- Proof: "registered" only after the site's confirmation email (or page) is seen; otherwise the event task says what failed.

## 6. Personal values and secrets: outside the repo (user, 2026-10-20)

The repo stays public. `~/.config/robotics-radar/config.yaml` (chmod 600) holds the Couple calendar id, the Todoist project and section ids, the form answers; `config/config.example.yaml` shows the keys with placeholders. Tokens: `gws`'s own login; the Todoist token is read (never printed, never copied) from `~/.config/task-management/todoist_token.env`, as skill task-management's `references/todoist_api.md` says for scripts and jobs. The Chrome profile in `~/opt/robotics-radar/chrome/`, never committed. The calendar and Todoist ids are still in this repo's early commits: harmless alone (they give no access), so history is not rewritten.

## 7. Phases

| # | What | Writes | Done when | The user's time |
|---|---|---|---|---|
| 0 | this design; ids moved to `~/.config/robotics-radar/` | none | committed (2026-10-20) ✅ | — |
| 1 | read all calendars and Professional › Robotics; check the historical leads; fill SQLite (`src/reconcile.py`) ✅ 2026-10-21 | none: a report; then the 4 tasks of past events deleted with the user's OK | every event task and Couple event matched to one event, the doubts listed | read one table |
| 2 | steps 1–4 in dry-run; the job installed ✅ 2026-10-21. Shortened (user, 2026-10-21): ChatGPT runs in dry-run instead and posts its plan as a Todoist comment; each run compares | none | the radar finds at least what ChatGPT finds, no duplicate in its dry-run writes | look at one comparison |
| 3 | Calendar and Todoist writes on ✅ 2026-10-21 (first run: 5 tasks, 25 Couple entries, all read back; a second run planned nothing) | Calendar, Todoist | every write read back, no duplicate; after a week of daily comparisons, **the user turns off the ChatGPT schedule** | 1 min |
| 4 | registration, auto group, screenshots only, then on; then ask first | registrations | 10 confirmed registrations, none wrong | log in once to each site; look at screenshots |
| 5 | notifications through alerting | — | waits for alerting (§9) | — |

## 7b. Phase 2 as built (2026-10-21)

```
src/run.py ── collect.py ──┬─ luma()      Luma's public API: categories ai, tech near Zürich + the Zürich page (keyword filter),
                           │               + organiser calendars (config + every organiser of an event scored ≥60)
                           ├─ voxel51()   Voxel51's public CMS (Sanity): online or Swiss events
                           ├─ pages()     config/sources.yaml pages: text hashed; Claude Haiku reads it only when it changed
                           └─ broad_search()  Claude Sonnet + web search, at most weekly
          merge (keys, event URLs, close date + similar title) → link (event tasks, every calendar, Luma emails)
          → score (Sonnet, only new or changed) → plan (table plans) → state/run_report.md
```

| Choice | Reason | Rejected |
|---|---|---|
| Luma's public API (`api.lu.ma`), no browser | gives free/price, sold out, approval, waitlist, spots [verified 2026-10-21] | Luma search: needs a login (phase 4's Chrome) |
| a listing page is read by Claude only when its text changed | the daily cost is near zero when nothing moved | a parser per site: brittle, many sites |
| JavaScript-only pages (DARE, Meetup, SECA) listed apart, not read | plain HTTP gets no events [verified 2026-10-21] | read them now: needs the headless Chrome of phase 4 |
| events known only from a task (ChatGPT's) are tracked from the task | the past-task and calendar rules apply to them too | ignore them until a source finds them |
| the job is installed in phase 2, dry-run | a week of daily comparisons without anyone running it | run by hand daily |

## 8. Changed from ChatGPT's handover

| Handover said | Now | Why |
|---|---|---|
| Todoist "Robotics project" (its id) | that id is the Project **Professional**; event tasks go in its Section **Robotics** | Todoist reorganised on 2026-10-19 (skill `task-management`) |
| description starts `Stream: Robotics - Events` | `Subsection: Events` in the metadata block at the end of the Description (after `created_by:`) | the `Stream:` line no longer exists; since 2026-10-21 the metadata lines go in a `<metadata>` … `</metadata>` block, last (skill `task-management`) |
| ids in `config.example.yaml` | in `~/.config/robotics-radar/config.yaml` | public repo (§6) |
| `docs/MIGRATION.md` | §7 | one plan |
| notify on new ≥75 events | not built yet | §9 |

## 9. Notifications: later

Not built (user, 2026-10-20): `~/dev/alerting` will carry them once its channels work. Todoist task "Send the radar's notifications through alerting" (Personal › Projects - IT, depends on alerting's channel setup). Until then the user sees everything in Todoist.

## Acceptance

- Two runs in a row on the same day write nothing the second time.
- An event already in any calendar, or already an event task, is never added again.
- Each registration has its confirmation email in the `registrations` table, and its event task says the next step.
- No personal value in `git grep` (ids, email, answers).

## Answered points (user, 2026-10-21)

| Was open | Answer |
|---|---|
| Gmail label for the `+events` replies | `Professional/Robotics/Events`, with a filter on the `+events` address |
| company/role line on forms | company "Meta", role "Lead Data Scientist" (`form:` in the private config) |
| event tasks of events now over | deleted by the radar (each run, step 4) |
| which events go on the calendar | every event the user can still attend or register for, registered or not; one closed to the user is not added, and the radar's own Couple event for it is removed (title prefix and marker `ROBOTICS_RADAR_AUTO`, never a user's own event) |

## Open points

- Unconfirmed time: a whole-day Couple event "time not confirmed", updated when the time is published [proposed 2026-10-21].
