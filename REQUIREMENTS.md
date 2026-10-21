# robotics-radar: requirements

Goal (user, 2026-10-20): the radar already finds the events, but registering for them is too much work for me; automate the registration a bit.

Two stages, clearly apart (user, 2026-10-21):

| Stage | What I get |
|---|---|
| **A** | a calendar of robotics events near Zürich, always up to date, that I can share: friends and people I meet at events subscribe to it with a QR code |
| **B** | I accept an event in my calendar, and I am registered for it automatically |

## Discovery
On **every** run rebuild/refresh credible upcoming inventory for approximately six months; explicitly revisit announcements and changed listings from at least 30 days. Search Zürich/Swiss robotics, embodied/Physical AI, autonomous systems, robot learning, manipulation, humanoids, CV for robotics, multimodal/VLM, evaluation, autonomous manufacturing, robotics startups and hardware/deep tech. Include useful online talks.

## Normalize
Record title, organizer, local date, start/end, timezone, venue/city, format, official event and registration URLs, all sources, price/currency, registration state/deadline, eligibility, language, summary, first/last seen, checked timestamp. Merge listings by URL, normalized title/date/organizer, venue and aliases. Use past events only to discover recurring organizers.

## Scoring
0–100 combining career pivot relevance, networking/prestige, technical quality, Zürich convenience, price/value, eligibility, scheduling and uniqueness. Bonus for robotics CV/evaluation, autonomous manufacturing, founder networks, Google Founder's Stories with robotics connection, TEDx at Google Europallee. Penalize commercial/generic AI, expensive, invitation-only, full and travel-heavy events. 85–100 exceptional, 75–84 high, 60–74 interesting, below 60 suppress.

## Calendar (stage A)
The radar fills **the shared calendar** "Robotics & Physical AI events near Zürich", public, instead of my own calendars (user, 2026-10-21; its id: `calendar.target_id` in `~/.config/robotics-radar/config.yaml`). Anyone with the QR code can view it and subscribe. Every upcoming event I can still attend or register for (registration open, a waitlist, not yet open, or no registration needed) is on it (user, 2026-10-21); an event closed to me (full without waitlist, cutoff passed) is not.

Each entry gives a viewer, me or anyone, what they need to decide whether to go (user, 2026-10-21): a short neutral summary (what, who speaks or organises, for whom), where, organiser, price, registration state and deadline, the registration page, the official page, and the pages where the radar found it. Nothing about me: no score, no Todoist link, no "you are registered". Title `🤖 <title>`, timezone Europe/Zurich, physical location, no Google Meet; uncertain time: a whole-day event saying the time is not confirmed. Marker `ROBOTICS_RADAR_AUTO`.

I am a guest of every entry, so it shows in my own calendar as an invitation I can accept or decline; except when I already have my own entry for that event (a Luma calendar invite, one I made): never a duplicate in what I see. Before any write the radar reads **all visible calendars**, including all-day placeholders.

## Todoist (stage B)
An event task only for an event I **accepted** and the radar **could not register by itself** (user, 2026-10-21): answers to approve, an event not on Luma, paid or closed, a failed try, a registration to cancel. One task per event, in Todoist Professional › Robotics (ids in `~/.config/robotics-radar/config.yaml`), `Subsection: Events` in its metadata block (skill task-management), titled `<event>: <what I must do>` (`approve the answers`, `register`, `cancel the registration`, `check the filled form`), due today; the radar's comments on it say how. Never completed by the radar; the task of an event that is over is deleted (user, 2026-10-21). No `agent`, `chatgpt`, `claude` labels. The 54 event tasks of before were deleted on 2026-10-21 (backup `~/opt/robotics-radar/state/event_tasks_before_2026-10-21_cleanup.json`); the 4 where I had already acted (registered, applied) were kept.

## Registration (stage B)
Only the events I **accepted** in my calendar are registered, not every good one (user, 2026-10-21). An accepted free Luma event is registered without me, and its event task says it is done (Luma's confirmation) and what comes next. When a form needs my own words, I approve the drafted answers first in a comment on the event task. Nothing paid, no new account, no password typed, no CAPTCHA bypassed: those, and events not on Luma, get a comment "register yourself, here". If I decline an event the radar registered me for, I am told to cancel it. I can check the first registrations before they are sent for real.

## Notification
Later (user, 2026-10-20): through the alerting project once it works. Until then, nothing but Todoist and the calendar.

## Reliability
Idempotent repeated runs, dry-run, per-source logs, error handling, DST, atomic state, retries, no invented details, readback verification, avoid private data in logs and repository.

## Decided questions
| Question | Answer |
|---|---|
| Laptop or VM? | the laptop (Mac) |
| Which events may be registered automatically? | free events only, score ≥75 (2026-10-20; since 2026-10-21: the ones I accept) |
| Email on forms? | my `+events` Gmail address, so a filter labels the replies |
| Public repo? | stays public; personal values outside it, in `~/.config/robotics-radar/` |
| Notifications? | not now; through the alerting project later |
| Gmail label for the `+events` replies? | yes, `Professional/Robotics/Events` (user, 2026-10-21) |
| Company and role on forms? | company "Meta", role "Lead Data Scientist" (user, 2026-10-21) |
| Event tasks of events that are over? | deleted (user, 2026-10-21) |
| Which events go on the calendar? | all I can still attend or register for, registered or not; not those closed to me (user, 2026-10-21) |
| Which calendar? | a shared, public one with a QR code, instead of Couple (user, 2026-10-21) |
| Which events are registered? | only those I accept in my calendar (user, 2026-10-21; it replaces "every free event ≥75") |
| Which events get a task? | only those I accepted and the radar could not register by itself (user, 2026-10-21) |
| Phone number on forms? | only when the form requires one; kept in the private config (`form.phone`, from Google Contacts) (user, 2026-10-21) |

## Out of scope
- Paid events, buying tickets, creating accounts.
- Any notification channel other than the alerting project.
