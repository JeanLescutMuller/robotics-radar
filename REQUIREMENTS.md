# robotics-radar: requirements

Goal (user, 2026-10-20): the radar already finds the events, but registering for them is too much work for me; automate the registration a bit.

## Discovery
On **every** run rebuild/refresh credible upcoming inventory for approximately six months; explicitly revisit announcements and changed listings from at least 30 days. Search Zürich/Swiss robotics, embodied/Physical AI, autonomous systems, robot learning, manipulation, humanoids, CV for robotics, multimodal/VLM, evaluation, autonomous manufacturing, robotics startups and hardware/deep tech. Include useful online talks.

## Normalize
Record title, organizer, local date, start/end, timezone, venue/city, format, official event and registration URLs, all sources, price/currency, registration state/deadline, eligibility, language, summary, first/last seen, checked timestamp. Merge listings by URL, normalized title/date/organizer, venue and aliases. Use past events only to discover recurring organizers.

## Scoring
0–100 combining career pivot relevance, networking/prestige, technical quality, Zürich convenience, price/value, eligibility, scheduling and uniqueness. Bonus for robotics CV/evaluation, autonomous manufacturing, founder networks, Google Founder's Stories with robotics connection, TEDx at Google Europallee. Penalize commercial/generic AI, expensive, invitation-only, full and travel-heavy events. 85–100 exceptional, 75–84 high, 60–74 interesting, below 60 suppress.

## Calendar
Before **any** write search **all visible calendars**, especially Couple, personal/primary, Family, including all-day placeholders. Fuzzy-match title, organizer, URL, date/time and venue. NEVER duplicate if equivalent exists anywhere. New event score >=80, exact confirmed date/start/end, registration open and clear eligibility: create **only** on the Couple calendar (its id: `calendar.target_id` in `~/.config/robotics-radar/config.yaml`). Title `🤖 [Robotics Radar] <title>`, event color ID `1` (pastel #a4bdfc), timezone Europe/Zurich, physical location, no Google Meet. Description: score/rationale, organizer, summary, price, eligibility, registration state/deadline, registration URL, official event URL, all material sources, discovery date, marker `ROBOTICS_RADAR_AUTO`. Uncertain time, unopened registration or unclear eligibility => do not auto-add; flag for review.

## Todoist
For every useful upcoming event normally >=60, ensure exactly **one** event-specific task in Todoist Professional › Robotics (ids in `~/.config/robotics-radar/config.yaml`). Search that Section first by normalized title and URLs; update equivalent instead of duplicate. Never complete/delete. No `agent`, `chatgpt`, `claude` labels. Description MUST start exactly `Subsection: Events` (skill task-management). Action titles: `: register` (open), `: request admission` / `: check application status` (approval), `: join waitlist` (full), `: confirm attendance` (approved/purchased), `: plan attendance` (no registration), `: find registration / register` (unpublished). For already registered event keep/update existing logistics task, no redundant registration task. Due date = **operational safety action date**, never event date; description explicitly says so and separately states actual event date. True published cutoff supersedes defaults. Without cutoff: 7 days local, 10–14 curated, 3 online, 2 no-registration; accelerate if close/full/waitlist. Never after published deadline. Dedicated premium deadline field currently unavailable.

## Registration
For a free event worth it, I am registered without doing anything, and I can see in its event task that it is done (confirmation received) and what comes next. When a form needs my own words, I approve them first in the event task. Nothing paid, no new account, no password typed, no CAPTCHA bypassed: those stay event tasks for me. I can check the first registrations before they are sent for real.

## Notification
Later (user, 2026-10-20): through the alerting project once it works. Until then, nothing but Todoist and the calendar.

## Reliability
Idempotent repeated runs, dry-run, per-source logs, error handling, DST, atomic state, retries, no invented details, readback verification, avoid private data in logs and repository.

## Decided questions
| Question | Answer (user, 2026-10-20) |
|---|---|
| Laptop or VM? | the laptop (Mac) |
| Which events may be registered automatically? | free events only, score ≥75 |
| Email on forms? | my `+events` Gmail address, so a filter labels the replies |
| Public repo? | stays public; personal values outside it, in `~/.config/robotics-radar/` |
| Notifications? | not now; through the alerting project later |

## Out of scope
- Paid events, buying tickets, creating accounts.
- Any notification channel other than the alerting project.
