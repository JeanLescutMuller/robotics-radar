"""One run of the radar (DESIGN.md §1): discover → merge → score → plan the Calendar/Todoist writes → write (phase 3).

Writes only with --write AND dry_run: false in ~/.config/robotics-radar/config.yaml (write.py); otherwise the planned writes
go to state/radar.sqlite (table plans) and the report only. Each run also compares with ChatGPT's dry-run log (Todoist comments).
Reads:  collect.py's sources, Todoist Professional › Robotics, every calendar, Luma emails (gws), the user's robotics facts
        (~/opt/my-setup/context/snapshot/facts/robotics.md, for scoring).
Writes: state/radar.sqlite, state/runs/<date>.md, state/run_report.md (the latest). All git-ignored.
Run:    python3 src/run.py [--no-search] [--write] > state/run.log 2>&1
"""
import json, re, sqlite3, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import collect, write
from common import (STATE, TZ, canon_url, claude_json, d_cfg, d_src, gws, log, parse_event_dates, same_event, similarity,
                    todoist_get, urls_in)

TODAY = datetime.now(TZ).date()
RANK = {'luma': 4, 'voxel51': 4, 'page': 3, 'search': 2, 'todoist': 1}   # whose facts win when two sources disagree
FINGERPRINT = ('start', 'end', 'venue', 'reg_state', 'price')            # a change here = a material change
ACTION_WORDS = {'confirm attendance': 'confirm', 'check application status': 'status', 'check waitlist status': 'waitlist',
                'join waitlist': 'waitlist', 'request admission': 'admission', 'register': 'register',
                'find registration / register': 'register', 'plan attendance': 'plan'}

STATE.mkdir(exist_ok=True); (STATE / 'runs').mkdir(exist_ok=True)
db = sqlite3.connect(STATE / 'radar.sqlite', isolation_level=None)
db.executescript('''
CREATE TABLE IF NOT EXISTS events (ts INT, dt TEXT, event_id INTEGER PRIMARY KEY, title TEXT, start TEXT, end TEXT, venue TEXT, city TEXT,
  online INT, organizer TEXT, url TEXT, reg_url TEXT, is_free INT, price TEXT, reg_state TEXT, deadline TEXT, summary TEXT, org_key TEXT,
  rank INT, score INT, score_reason TEXT, scored_fp TEXT, user_state TEXT, first_seen TEXT, last_seen TEXT, task_id TEXT, calendar_ids TEXT);
CREATE TABLE IF NOT EXISTS keys (source TEXT, key TEXT, event_id INT, PRIMARY KEY (source, key));
CREATE TABLE IF NOT EXISTS urls (url TEXT, event_id INT, PRIMARY KEY (url, event_id));
CREATE TABLE IF NOT EXISTS changes (ts INT, dt TEXT, event_id INT, field TEXT, old TEXT, new TEXT);
CREATE TABLE IF NOT EXISTS plans (ts INT, dt TEXT, run_ts INT, event_id INT, action TEXT, target TEXT, details TEXT);
CREATE TABLE IF NOT EXISTS runs (ts INT, dt TEXT, broad_search INT, n_candidates INT, n_new INT, n_changed INT, cost_usd REAL, errors TEXT);
CREATE TABLE IF NOT EXISTS organizers (source TEXT, org_key TEXT, name TEXT, PRIMARY KEY (source, org_key));
CREATE TABLE IF NOT EXISTS luma_cache (api_id TEXT PRIMARY KEY, stamp TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS pages (url TEXT PRIMARY KEY, hash TEXT, events TEXT, checked TEXT);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);''')
RUN_TS = int(time.time()); RUN_DT = datetime.fromtimestamp(RUN_TS, timezone.utc).isoformat(timespec='seconds')
db.execute("INSERT OR IGNORE INTO meta VALUES ('phase2_start', ?)", (str(RUN_TS),))
db.execute("INSERT OR IGNORE INTO meta VALUES ('db_id', ?)", (__import__('secrets').token_hex(3),))
DB_ID = write.DB_ID = db.execute("SELECT v FROM meta WHERE k='db_id'").fetchone()[0]
def own_id(text):
    # "Robotics Radar event: <db_id>-<n>" in what the radar wrote: the event itself, no matching needed
    m = re.search(rf'Robotics Radar event: {DB_ID}-(\d+)', text or '')
    return int(m[1]) if m and db.execute('SELECT 1 FROM events WHERE event_id=?', (int(m[1]),)).fetchone() else None
l_cost, l_errors = [], []
COLS = [r[1] for r in db.execute('PRAGMA table_info(events)')]


def clean_title(task_title):
    # the event's name inside a task title: "X: register", "Register for X if worthwhile", "Decide whether to attend X"
    t = re.sub(r'^(decide whether to (register for|attend)|register for|plan|decide and register for)\s+', '', task_title, flags=re.I)
    t = re.sub(r'\s+if worthwhile$', '', t, flags=re.I)
    return re.sub(r':\s*(register|request admission|check .*|join waitlist|confirm attendance|plan .*|find registration.*|decide.*)$', '', t, flags=re.I)


def d_event(row): return dict(zip(COLS, row))
def all_events(): return [d_event(r) for r in db.execute('SELECT * FROM events')]
def day(iso): return date.fromisoformat(iso[:10]) if iso else None
def match_view(e):   # what same_event() compares
    return {'title': e['title'], 'start': day(e['start']), 'urls': {r[0] for r in db.execute('SELECT url FROM urls WHERE event_id=?', (e['event_id'],))}}


# ---------- 1. discover ----------
# every task of the Section is matched (an event may be a task of another subsection, e.g. Swiss Robotics Day);
# only event tasks (subsection Events) are created, updated or deleted by the radar
l_all_tasks = todoist_get(f"tasks?section_id={d_cfg['todoist']['section_id']}&limit=200")
l_tasks = [t for t in l_all_tasks if d_cfg['todoist']['description_prefix'] in t['description'].split('\n')]   # the line, in the metadata block
l_slugs = sorted({u.split('/')[1] for t in l_tasks for u in urls_in(t['description']) if u.startswith('luma.com/') and u.count('/') == 1})
l_cand = []
for name, f in (('luma', lambda: collect.luma(db, l_slugs)), ('voxel51', lambda: collect.voxel51(db)), ('pages', lambda: collect.pages(db, l_cost))):
    try: l_cand += f()
    except Exception as e: log(f'ERROR {name}: {e}'); l_errors.append(f'{name}: {e}')
did_search = False
if '--no-search' not in sys.argv:
    l_cand_s, did_search = collect.broad_search(db, sorted({c['title'] for c in l_cand} | {e['title'] for e in all_events() if e['start'] and day(e['start']) >= TODAY}), l_cost)
    l_cand += l_cand_s
l_cand = [c for c in l_cand if c['start'] and day(c['start']) >= TODAY - timedelta(days=1)]
log(f'{len(l_cand)} candidates')

# ---------- 2. merge into events ----------
s_listing = {canon_url(u) for u in d_src['pages']}   # a listing page links many events: never proof of identity
n_new, s_changed = 0, set()

def upsert(c):
    global n_new
    row = db.execute('SELECT event_id FROM keys WHERE source=? AND key=?', (c['source'], c['key'])).fetchone()
    c_urls = {canon_url(u) for u in (c.get('url'), c.get('reg_url')) if u}
    eid = row[0] if row else next((e['event_id'] for e in all_events()
                                   if same_event({'title': c['title'], 'start': day(c['start']), 'urls': c_urls}, match_view(e), s_listing)), None)
    d_new = {k: c.get(k) for k in ('title', 'start', 'end', 'venue', 'city', 'online', 'organizer', 'url', 'reg_url', 'is_free', 'price',
                                   'reg_state', 'deadline', 'summary', 'org_key')}
    if eid is None:
        cur = db.execute(f"INSERT INTO events (ts, dt, {', '.join(d_new)}, rank, first_seen, last_seen) VALUES (?,?,{','.join('?' * len(d_new))},?,?,?)",
                         (RUN_TS, RUN_DT, *d_new.values(), RANK[c['source']], RUN_DT, RUN_DT))
        eid = cur.lastrowid; n_new += 1
    else:
        e = d_event(db.execute('SELECT * FROM events WHERE event_id=?', (eid,)).fetchone())
        # a better source overwrites; a worse one only fills what is empty
        d_set = {k: v for k, v in d_new.items() if v not in (None, '') and (RANK[c['source']] >= (e['rank'] or 0) or e[k] in (None, ''))}
        for k in FINGERPRINT:
            if k in d_set and e[k] not in (None, '') and str(d_set[k]) != str(e[k]):
                db.execute('INSERT INTO changes VALUES (?,?,?,?,?,?)', (RUN_TS, RUN_DT, eid, k, str(e[k]), str(d_set[k]))); s_changed.add(eid)
        d_set |= {'last_seen': RUN_DT, 'rank': max(RANK[c['source']], e['rank'] or 0), 'ts': RUN_TS, 'dt': RUN_DT}
        db.execute(f"UPDATE events SET {', '.join(f'{k}=?' for k in d_set)} WHERE event_id=?", (*d_set.values(), eid))
    db.execute('INSERT OR IGNORE INTO keys VALUES (?,?,?)', (c['source'], c['key'], eid))
    for u in c_urls: db.execute('INSERT OR IGNORE INTO urls VALUES (?,?)', (u, eid))
    return eid

for c in l_cand:
    try: upsert(c)
    except Exception as e: log(f'merge {c.get("title")}: {e}'); l_errors.append(f'merge: {e}')

# ---------- 3. link: event tasks, calendar entries, Luma emails ----------
if 'other_task_ids' not in COLS: db.execute('ALTER TABLE events ADD COLUMN other_task_ids TEXT'); COLS.append('other_task_ids')
db.execute('UPDATE events SET task_id=NULL, calendar_ids=NULL, other_task_ids=NULL')
for t in l_all_tasks:
    if t in l_tasks: continue
    start, _ = parse_event_dates(t['description'])
    tv = {'title': t['content'], 'start': start, 'urls': urls_in(t['description'])}
    eid = next((e['event_id'] for e in all_events() if same_event(tv, match_view(e), s_listing)), None)
    if eid: db.execute('UPDATE events SET other_task_ids=? WHERE event_id=?', (t['id'], eid))
d_task_by_id = {t['id']: t for t in l_tasks}
for t in l_tasks:
    start, end = parse_event_dates(t['description'])
    tv = {'title': t['content'], 'start': start, 'urls': urls_in(t['description'])}
    eid = own_id(t['description']) or next((e['event_id'] for e in all_events() if same_event(tv, match_view(e), s_listing)), None)
    if eid is None:   # an event only the task knows (found by ChatGPT): tracked from the task
        score = re.search(r'Score:?\s*(\d+)\s*/\s*100', t['description'])
        eid = upsert(dict(source='todoist', key=t['id'], title=clean_title(t['content']),
                          start=start.isoformat() if start else None, end=end.isoformat() if end else None, url=next(iter(tv['urls']), None),
                          reg_url=None, reg_state='unknown', summary=t['description'][:1500]))
        if score: db.execute('UPDATE events SET score=?, score_reason=?, scored_fp=? WHERE event_id=? AND score IS NULL', (int(score[1]), 'from the task (ChatGPT)', 'task', eid))
    prev = db.execute('SELECT task_id FROM events WHERE event_id=?', (eid,)).fetchone()[0]
    db.execute('UPDATE events SET task_id=? WHERE event_id=?', (f'{prev} {t["id"]}' if prev else t['id'], eid))   # two ids = a duplicate

t_min = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(); t_max = (datetime.now(timezone.utc) + timedelta(days=200)).isoformat()
s_ical = set(); n_cal = 0
for d_cal in gws('calendar', 'calendarList', 'list')['items']:
    token = None
    while True:
        d_p = {'calendarId': d_cal['id'], 'timeMin': t_min, 'timeMax': t_max, 'singleEvents': True, 'maxResults': 2500} | ({'pageToken': token} if token else {})
        d_page = gws('calendar', 'events', 'list', '--params', json.dumps(d_p))
        for ce in d_page.get('items', []):
            if ce.get('iCalUID') in s_ical: continue
            s_ical.add(ce.get('iCalUID'))
            s = ce.get('start', {})
            cv = {'title': ce.get('summary', ''), 'start': day(s.get('date') or s.get('dateTime')), 'urls': urls_in(ce.get('description', ''))}
            eid = own_id(ce.get('description')) or next((e['event_id'] for e in all_events() if same_event(cv, match_view(e), s_listing)), None)
            if eid is None: continue
            radar = d_cfg['calendar']['marker'] in (ce.get('description') or '') or ce.get('summary', '').startswith(d_cfg['calendar']['title_prefix'].strip())
            prev = db.execute('SELECT calendar_ids FROM events WHERE event_id=?', (eid,)).fetchone()[0]
            ref = f"{d_cal['id']}|{ce['id']}|{'radar' if radar else 'user'}"
            db.execute('UPDATE events SET calendar_ids=? WHERE event_id=?', (f'{prev} {ref}' if prev else ref, eid)); n_cal += 1
        token = d_page.get('nextPageToken')
        if not token: break

# Luma emails: the user's own registration state, newest email wins
d_list = gws('gmail', 'users', 'messages', 'list', '--params', json.dumps({'userId': 'me', 'q': 'from:(luma.com OR lu.ma OR luma-mail.com) newer_than:120d', 'maxResults': 200}))
l_mail = []
for m in d_list.get('messages', []):
    d_m = gws('gmail', 'users', 'messages', 'get', '--params', json.dumps({'userId': 'me', 'id': m['id'], 'format': 'metadata', 'metadataHeaders': ['Subject']}))
    l_mail.append((int(d_m['internalDate']), next((h['value'] for h in d_m['payload']['headers'] if h['name'] == 'Subject'), '')))
for _, subject in sorted(l_mail):
    s = subject.lower()
    state = ('declined' if re.search(r'declin|not approved|unable to', s) else 'waitlist' if 'waitlist' in s else 'pending' if re.search(r'pending|approval', s)
             else 'registered' if re.search(r'approved|registered|confirmed|you.re in|you.re going|ticket', s) else None)
    if not state: continue
    for e in all_events():
        if e['start'] and day(e['start']) >= TODAY - timedelta(days=1) and similarity(subject, e['title']) >= 0.8:
            db.execute('UPDATE events SET user_state=? WHERE event_id=?', (state, e['event_id']))
log(f'linked: {len(l_tasks)} event tasks, {n_cal} calendar entries, {len(l_mail)} Luma emails')

# ---------- 4. score new or changed events (Claude, in batches) ----------
def fp(e): return json.dumps([e[k] for k in FINGERPRINT + ('user_state',)])   # rescored when the user's own state changes too
l_to_score = [e for e in all_events() if e['start'] and day(e['start']) >= TODAY and e['scored_fp'] != fp(e)
              and (e['rank'] > RANK['todoist'] or e['score'] is None)]   # a task's event: only when the task gave no score
profile_path = Path.home() / 'opt/my-setup/context/snapshot/facts/robotics.md'
profile = profile_path.read_text()[:6000] if profile_path.exists() else ''
rubric = (Path(__file__).resolve().parent.parent / 'REQUIREMENTS.md').read_text().split('## Scoring')[1].split('##')[0].strip()
for i in range(0, len(l_to_score), 20):
    l_batch = l_to_score[i:i + 20]
    l_in = [{'id': e['event_id'], 'title': e['title'], 'start': e['start'], 'venue': e['venue'] or e['city'], 'online': bool(e['online']),
             'organizer': e['organizer'], 'free': e['is_free'], 'price': e['price'], 'registration': e['reg_state'], 'user_already': e['user_state'], 'summary': (e['summary'] or '')[:700]}
            for e in l_batch]
    prompt = f"""Score events for this person, 0-100. Rules:
{rubric}

THE PERSON (their own notes):
{profile}

EVENTS:
{json.dumps(l_in, ensure_ascii=False)}

"user_already" is the person's own state (registered, pending, waitlist): never penalise a full event they are already in.
Answer ONLY a JSON array: [{{"id": int, "score": int, "reason": "max 20 words"}}] with one object per event."""
    try:
        l_out, cost = claude_json(prompt, d_src['models']['score']); l_cost.append(cost)
        d_e = {e['event_id']: e for e in l_batch}
        for o in l_out:
            if o.get('id') in d_e: db.execute('UPDATE events SET score=?, score_reason=?, scored_fp=? WHERE event_id=?', (int(o['score']), o.get('reason', ''), fp(d_e[o['id']]), o['id']))
    except Exception as e: log(f'score: {e}'); l_errors.append(f'score: {e}')
log(f'scored: {len(l_to_score)} events')
# remember the organisers of good Luma events: their calendars are read every run
db.execute("INSERT OR IGNORE INTO organizers SELECT 'luma', org_key, organizer FROM events WHERE org_key LIKE 'cal-%' AND score >= ?", (d_cfg['minimum_task_score'],))

# ---------- 5. plan the writes (dry-run) ----------
def expected_action(e):
    us, rs = e['user_state'], e['reg_state']
    if us == 'registered': return 'confirm attendance'
    if us == 'pending': return 'check application status'
    if us == 'waitlist': return 'check waitlist status'
    return {'open': 'register', 'approval': 'request admission', 'waitlist': 'join waitlist', 'none': 'plan attendance'}.get(rs, 'find registration / register')


def safety_date(e):
    # REQUIREMENTS.md Todoist: published cutoff first; else 7 days local, 12 curated, 3 online, 2 no registration; now if full or close
    start = day(e['start'])
    lead = 2 if e['reg_state'] == 'none' else 3 if e['online'] else 12 if e['reg_state'] == 'approval' else 7
    d = start - timedelta(days=lead)
    if e['deadline']:
        try: d = min(d, date.fromisoformat(e['deadline'][:10]) - timedelta(days=1))
        except ValueError: pass
    if e['reg_state'] in ('waitlist', 'full'): d = TODAY
    return max(d, TODAY)


def closed_to_user(e): return e['reg_state'] in ('full', 'closed') and e['user_state'] not in ('registered', 'pending', 'waitlist')


l_plan = []
def plan(e, action, target, **details): l_plan.append((e, action, target, details))
for e in all_events():
    if not e['start']: continue
    end = day(e['end'] or e['start'])
    l_tid = (e['task_id'] or '').split()
    l_cal = [c.split('|') for c in (e['calendar_ids'] or '').split()]
    if end < TODAY:
        for tid in l_tid: plan(e, 'delete_task', tid, why=f'event ended {end}')
        continue
    if not l_tid and not {r[0] for r in db.execute('SELECT source FROM keys WHERE event_id=?', (e['event_id'],))} - {'todoist'}:
        continue   # made from a task that now matches a better event (or is gone): nothing to plan
    tracked = bool(l_tid) or (e['score'] or 0) >= d_cfg['minimum_task_score']
    if not tracked or (e['other_task_ids'] and not l_tid): continue   # followed by a task of another subsection: the user's
    act = expected_action(e)
    if len(l_tid) > 1: plan(e, 'merge_tasks', ' '.join(l_tid), why='two event tasks for one event')
    if not l_tid and not closed_to_user(e):
        plan(e, 'create_task', f"{e['title']}: {act}", due=str(safety_date(e)), score=e['score'], reg_state=e['reg_state'])
    elif l_tid:
        title = d_task_by_id[l_tid[0]]['content'].lower()
        if ACTION_WORDS[act] not in title and act in ('confirm attendance', 'check application status', 'check waitlist status', 'join waitlist'):
            plan(e, 'update_task', l_tid[0], new_title=f"{e['title']}: {act}", why=f"Luma says {e['user_state'] or e['reg_state']}")
    if not l_cal and not closed_to_user(e) and ((e['score'] or 0) >= d_cfg['minimum_task_score'] or e['user_state'] in ('registered', 'pending', 'waitlist')):
        plan(e, 'add_calendar', 'Couple', title=d_cfg['calendar']['title_prefix'] + e['title'], when=f"{e['start']} → {e['end'] or ''}",
             whole_day=len(e['start']) == 10)
    if closed_to_user(e):
        for cal_id, ev_id, who in l_cal:
            if who == 'radar': plan(e, 'remove_calendar', f'{cal_id}|{ev_id}', why=f"{e['reg_state']}, not registered")
for e, action, target, details in l_plan:
    db.execute('INSERT INTO plans VALUES (?,?,?,?,?,?,?)', (RUN_TS, RUN_DT, RUN_TS, e['event_id'], action, target, json.dumps(details, ensure_ascii=False)))
WRITING = '--write' in sys.argv and d_cfg.get('dry_run') is False
n_written = 0
if WRITING:
    def sources_of(eid): return ', '.join(sorted({r[0] for r in db.execute('SELECT source FROM keys WHERE event_id=?', (eid,))}))
    n_written, l_werr = write.execute(db, l_plan, d_task_by_id, RUN_TS, RUN_DT, sources_of)
    l_errors += l_werr

# ---------- ChatGPT's dry-run log: its latest comment, matched against the radar's events ----------
l_gpt_ev, gpt_date = [], None
log_task = d_cfg['todoist'].get('chatgpt_log_task_id')
if log_task:
    try:
        l_com = [c for c in todoist_get(f'comments?task_id={log_task}&limit=200') if c['content'].startswith('CHATGPT-DRY-RUN')]
        if l_com:
            c = max(l_com, key=lambda c: c['posted_at'])
            m = re.search(r'```(?:json)?\s*(.*?)```', c['content'], re.S)
            d_gpt = json.loads(m[1] if m else c['content'][c['content'].index('{'):])
            gpt_date, l_gpt_ev = d_gpt.get('run_date'), d_gpt.get('events', [])
            db.execute('CREATE TABLE IF NOT EXISTS chatgpt (ts INT, dt TEXT, run_date TEXT, title TEXT, start TEXT, url TEXT, score INT, would_do TEXT, event_id INT, PRIMARY KEY (run_date, title, start))')
    except Exception as e: log(f'chatgpt log: {e}'); l_errors.append(f'chatgpt log: {e}')
d_gpt_match = {}
for g in l_gpt_ev:
    gv = {'title': g.get('title') or '', 'start': day(g.get('start')) if g.get('start') else None,
          'urls': {canon_url(u) for u in (g.get('official_url'), g.get('registration_url')) if u}}
    eid = next((e['event_id'] for e in all_events() if same_event(gv, match_view(e), s_listing)), None)
    d_gpt_match[id(g)] = eid
    db.execute('INSERT OR REPLACE INTO chatgpt VALUES (?,?,?,?,?,?,?,?,?)', (RUN_TS, RUN_DT, gpt_date, gv['title'], g.get('start'), g.get('official_url'),
                                                                           g.get('score'), json.dumps(g.get('would_do')), eid))
cost = round(sum(l_cost), 4)
db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)', (RUN_TS, RUN_DT, int(did_search), len(l_cand), n_new, len(s_changed), cost, json.dumps(l_errors)))

# ---------- 6. the report ----------
def row(*cells): return '| ' + ' | '.join(str(c if c is not None else '').replace('|', '/').replace('\n', ' ') for c in cells) + ' |'
d_count = {}
for _, a, _, _ in l_plan: d_count[a] = d_count.get(a, 0) + 1
phase2_start = int(db.execute("SELECT v FROM meta WHERE k='phase2_start'").fetchone()[0])
L = [f"# Radar run {RUN_DT} ({f'WRITES: {n_written} done, read back' if WRITING else 'DRY-RUN: nothing written'})", '', '| What | Count |', '|---|---|',
     row('candidates read', len(l_cand)), row('new events', n_new), row('changed events', len(s_changed)), row('events scored', len(l_to_score)),
     row('broad web search', 'yes' if did_search else 'no'), row('Claude cost (USD, this run)', cost), row('errors', len(l_errors))]
L += [row(f'planned: {a}', n) for a, n in sorted(d_count.items())]
for action, head in (('create_task', '| Event date | Score | New task | Safety date | Registration |'), ('update_task', '| Event date | Task | New title | Why |'),
                     ('delete_task', '| Event | Task | Why |'), ('merge_tasks', '| Event | Tasks | Why |'),
                     ('add_calendar', '| Event date | Score | Calendar title | Whole day |'), ('remove_calendar', '| Event | Entry | Why |')):
    l_rows = [(e, t, d) for e, a, t, d in l_plan if a == action]
    if not l_rows: continue
    L += ['', f'## Planned: {action} ({len(l_rows)})', '', head, '|' + '---|' * head.count(' | ') + '---|']
    for e, t, d in sorted(l_rows, key=lambda x: x[0]['start']):
        L.append({'create_task': lambda: row(e['start'][:16], e['score'], t, d['due'], d['reg_state']),
                  'update_task': lambda: row(e['start'][:10], d_task_by_id[t]['content'], d['new_title'], d['why']),
                  'delete_task': lambda: row(e['title'], d_task_by_id[t]['content'], d['why']),
                  'merge_tasks': lambda: row(e['title'], t, d['why']),
                  'add_calendar': lambda: row(e['start'][:16], e['score'], d['title'], d['whole_day']),
                  'remove_calendar': lambda: row(e['title'], t, d['why'])}[action]())
# side by side with ChatGPT's dry-run (its latest log comment)
d_ev = {e['event_id']: e for e in all_events()}
s_gpt_eids = {v for v in d_gpt_match.values() if v}
L += ['', f"## ChatGPT vs radar (ChatGPT's run of {gpt_date or 'none yet'})", '', '| Event date | ChatGPT event | ChatGPT score | Radar score | Radar tracks it? |', '|---|---|---|---|---|']
for g in sorted(l_gpt_ev, key=lambda g: g.get('start') or ''):
    e = d_ev.get(d_gpt_match[id(g)])
    tracked = e and (e['task_id'] or (e['score'] or 0) >= d_cfg['minimum_task_score'])
    L.append(row((g.get('start') or '')[:10], g.get('title'), g.get('score'), e['score'] if e else '—', 'yes' if tracked else '**no: ChatGPT only**' if not e else 'found, scored lower'))
l_radar_only = [e for e in d_ev.values() if e['start'] and day(e['start']) >= TODAY and (e['score'] or 0) >= d_cfg['minimum_task_score']
                and e['event_id'] not in s_gpt_eids]
if l_gpt_ev:
    L += ['', f'Radar only ({len(l_radar_only)}): ' + '; '.join(f"{e['start'][:10]} {e['title']} ({e['score']})" for e in sorted(l_radar_only, key=lambda e: e['start']))]
if l_errors: L += ['', '## Errors', ''] + [f'- {x}' for x in l_errors]
text = '\n'.join(L) + '\n'
(STATE / 'runs' / f"{datetime.fromtimestamp(RUN_TS, TZ):%Y-%m-%d_%H%M}.md").write_text(text)
(STATE / 'run_report.md').write_text(text)
log(f'plan: {d_count}; written: {n_written if WRITING else "dry-run"}; cost ${cost}; report {STATE / "run_report.md"}')
sys.exit(1 if WRITING and l_errors else 0)   # a failed or refused write turns the job red
