# Complete functional requirements
## Discovery
On **every** run rebuild/refresh credible upcoming inventory for approximately six months; explicitly revisit announcements and changed listings from at least 30 days. Search Zürich/Swiss robotics, embodied/Physical AI, autonomous systems, robot learning, manipulation, humanoids, CV for robotics, multimodal/VLM, evaluation, autonomous manufacturing, robotics startups and hardware/deep tech. Include useful online talks.

## Normalize
Record title, organizer, local date, start/end, timezone, venue/city, format, official event and registration URLs, all sources, price/currency, registration state/deadline, eligibility, language, summary, first/last seen, checked timestamp. Merge listings by URL, normalized title/date/organizer, venue and aliases. Use past events only to discover recurring organizers.

## Scoring
0–100 combining career pivot relevance, networking/prestige, technical quality, Zürich convenience, price/value, eligibility, scheduling and uniqueness. Bonus for robotics CV/evaluation, autonomous manufacturing, founder networks, Google Founder's Stories with robotics connection, TEDx at Google Europallee. Penalize commercial/generic AI, expensive, invitation-only, full and travel-heavy events. 85–100 exceptional, 75–84 high, 60–74 interesting, below 60 suppress.

## Calendar
Before **any** write search **all visible calendars**, especially Couple, personal/primary, Family, including all-day placeholders. Fuzzy-match title, organizer, URL, date/time and venue. NEVER duplicate if equivalent exists anywhere. New event score >=80, exact confirmed date/start/end, registration open and clear eligibility: create **only** on Couple calendar `5vut7ufd25i34mnf92599ofo3c@group.calendar.google.com`. Title `🤖 [Robotics Radar] <title>`, event color ID `1` (pastel #a4bdfc), timezone Europe/Zurich, physical location, no Google Meet. Description: score/rationale, organizer, summary, price, eligibility, registration state/deadline, registration URL, official event URL, all material sources, discovery date, marker `ROBOTICS_RADAR_AUTO`. Uncertain time, unopened registration or unclear eligibility => do not auto-add; flag for review.

## Todoist
For every useful upcoming event normally >=60, ensure exactly **one** event-specific task in Robotics project `6hj34MgwvM37xF5c`. Search project first by normalized title and URLs; update equivalent instead of duplicate. Never complete/delete. No `agent`, `chatgpt`, `claude` labels. Description MUST start exactly `Stream: Robotics - Events`. Action titles: `: register` (open), `: request admission` / `: check application status` (approval), `: join waitlist` (full), `: confirm attendance` (approved/purchased), `: plan attendance` (no registration), `: find registration / register` (unpublished). For already registered event keep/update existing logistics task, no redundant registration task. Due date = **operational safety action date**, never event date; description explicitly says so and separately states actual event date. True published cutoff supersedes defaults. Without cutoff: 7 days local, 10–14 curated, 3 online, 2 no-registration; accelerate if close/full/waitlist. Never after published deadline. Dedicated premium deadline field currently unavailable.

## Notification
Notify only for new >=75 event OR material change to previously tracked high-priority event (date/time/venue, registration status, full). Include score, calendar action and Todoist created/updated. Otherwise silent. Do not assume any channel without authorization.

## Reliability
Idempotent repeated runs, dry-run, per-source logs, error handling, DST, atomic state, retries, no invented details, readback verification, avoid private data in logs and repository.
