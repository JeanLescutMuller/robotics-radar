"""Phase 1 (DESIGN.md §7): read-only reconcile of event tasks, calendars, Gmail confirmations and ChatGPT's leads.

Reads:  Todoist Professional › Robotics (token: ~/.config/task-management/todoist_token.env, never printed),
        all visible Google calendars and Luma emails in Gmail (gws CLI), data/historical-events.json,
        the events' web pages (one GET each), ~/.config/robotics-radar/config.yaml.
Writes: state/radar.sqlite and state/phase1_report.md (git-ignored: they hold personal data). Nothing external.

Run:    python3 src/reconcile.py > state/phase1.log 2>&1
"""
import json, re, sqlite3, subprocess, sys, time, unicodedata, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / 'state'
TODAY = date.today()
d_cfg = yaml.safe_load((Path.home() / '.config/robotics-radar/config.yaml').read_text())
MONTHS = {m: i + 1 for i, m in enumerate('jan feb mar apr may jun jul aug sep oct nov dec'.split())}
# words that say what to do, not which event: removed before comparing titles
STOP = set('''a an and the of for at in on to by with if or x vs register registration request admission check application
status join waitlist confirm attendance plan find decide whether attend visit follow up eligibility cost worthwhile
radar bobi robotics_radar event events session meetup
buy ticket tickets apply summit conference
robotics robot zurich ai physical 2026 2027 seminar workshop talk night day
approved confirmed pending you re your is has been next week weeks starting tomorrow today reminder'''.split())
# last two lines: words in most titles, and in Luma's email subjects, that say nothing about which event


def log(*args): print(datetime.now().strftime('%H:%M:%S'), *args, flush=True)


def gws(*args):
    # gws prints a keyring line on stderr: keep stdout only
    out = subprocess.run(['gws', *args], capture_output=True, text=True, timeout=120)
    if out.returncode: raise RuntimeError(f'gws {args[:3]} failed: {out.stderr[-300:]}')
    return json.loads(out.stdout)


def canon_url(url):
    # same event, different spellings: lu.ma = luma.com, no query, no trailing slash, no www
    url = re.sub(r'[)\]>.,;]+$', '', url.strip()).split('?')[0].split('#')[0].rstrip('/').lower()
    url = re.sub(r'^https?://(www\.)?', '', url)
    return url.replace('lu.ma/', 'luma.com/')


def urls_in(text):
    return {canon_url(u) for u in re.findall(r'https?://[^\s)\]<>"]+', text or '')
            if not re.search(r'mail\.google|google\.com/calendar|todoist\.com', u)}


def norm_tokens(title):
    title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode().lower()
    title = re.sub(r'\[robotics radar\]|^robotics - |^professional/robotics', ' ', title)
    return [w for w in re.findall(r'[a-z0-9]+', title) if w not in STOP and (len(w) > 1 or w.isdigit())]


def similarity(t1, t2):
    l1, l2 = norm_tokens(t1), norm_tokens(t2)
    if not l1 or not l2: return 0.0
    # share of the shorter title's words found in the other; a one-word title only by spelling (else "roundtable" matches every roundtable)
    # (spelling only for one-word titles: on longer ones it matched "cleaning" with "learning")
    if min(len(set(l1)), len(set(l2))) > 1: return len(set(l1) & set(l2)) / min(len(set(l1)), len(set(l2)))
    return SequenceMatcher(None, ' '.join(l1), ' '.join(l2)).ratio()


def parse_event_dates(desc):
    # the "Event:" line ChatGPT writes: ISO dates, or "Thu 22 Oct 2026", "28–29 Oct 2026", "Friday 23 October 2026"
    m = re.search(r'Event:\s*(.*)', desc or '')
    if not m: return None, None
    line = m.group(1)
    l_iso = re.findall(r'(\d{4}-\d{2}-\d{2})', line)
    if l_iso: return date.fromisoformat(l_iso[0]), date.fromisoformat(l_iso[-1])
    m = re.search(r'(\d{1,2})(?:\s*[–-]\s*(\d{1,2}))?\s+([A-Za-z]{3})[a-z]*\.?,?\s+(\d{4})', line)
    if not m or m[3].lower() not in MONTHS: return None, None
    start = date(int(m[4]), MONTHS[m[3].lower()], int(m[1]))
    return start, start.replace(day=int(m[2])) if m[2] else start


# ---------- 1. read every source into one list of items ----------
l_items = []   # dicts: kind, ext_id, title, start, end, urls, extra

def read_todoist():
    token = re.search(r'TODOIST_API_TOKEN="?([^"\n]+)', (Path.home() / '.config/task-management/todoist_token.env').read_text())[1]
    l_tasks, cursor = [], None
    while True:
        url = f"https://api.todoist.com/api/v1/tasks?section_id={d_cfg['todoist']['section_id']}&limit=200" + (f'&cursor={cursor}' if cursor else '')
        req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
        d_page = json.load(urllib.request.urlopen(req, timeout=30))
        l_tasks += d_page['results']; cursor = d_page.get('next_cursor')
        if not cursor: break
    for d_t in l_tasks:
        if not d_t['description'].startswith(d_cfg['todoist']['description_prefix']): continue   # other subsections: not event tasks
        start, end = parse_event_dates(d_t['description'])
        l_items.append(dict(kind='task', ext_id=d_t['id'], title=d_t['content'], start=start, end=end,
                            urls=urls_in(d_t['description']), extra={'due': (d_t.get('due') or {}).get('date')}))
    log(f'todoist: {len(l_tasks)} tasks in the section, {sum(i["kind"] == "task" for i in l_items)} event tasks')


s_ical = set()   # an event of a shared calendar also shows in the primary one, same iCalUID: count it once
def read_calendars():
    t_min = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    t_max = (datetime.now(timezone.utc) + timedelta(days=200)).isoformat()
    for d_cal in gws('calendar', 'calendarList', 'list')['items']:
        l_ev, token = [], None
        while True:
            d_p = {'calendarId': d_cal['id'], 'timeMin': t_min, 'timeMax': t_max, 'singleEvents': True, 'maxResults': 2500}
            if token: d_p['pageToken'] = token
            d_page = gws('calendar', 'events', 'list', '--params', json.dumps(d_p))
            l_ev += d_page.get('items', []); token = d_page.get('nextPageToken')
            if not token: break
        for d_e in l_ev:
            if d_e.get('iCalUID') in s_ical: continue
            s_ical.add(d_e.get('iCalUID'))
            s, e = d_e.get('start', {}), d_e.get('end', {})
            start = date.fromisoformat((s.get('date') or s.get('dateTime', ''))[:10]) if s else None
            end = date.fromisoformat((e.get('date') or e.get('dateTime', ''))[:10]) if e else start
            if s.get('date') and end: end -= timedelta(days=1)   # all-day end is exclusive
            text = (d_e.get('summary', '') + ' ' + d_e.get('description', ''))
            l_items.append(dict(kind='calendar', ext_id=d_e['id'], title=d_e.get('summary', ''), start=start, end=end,
                                urls=urls_in(d_e.get('description', '')) | urls_in(d_e.get('location', '')),
                                extra={'calendar': d_cal.get('summary'), 'link': d_e.get('htmlLink'),
                                       'radar': d_cfg['calendar']['marker'] in text or '[Robotics Radar]' in text,
                                       'robotics_hint': bool(re.search(r'robot|🤖|physical ai', text, re.I))}))
        log(f'calendar {d_cal.get("summary")}: {len(l_ev)} events')


def read_gmail():
    # Luma's mails say the registration state: confirmed, pending approval, waitlist, declined
    d_list = gws('gmail', 'users', 'messages', 'list', '--params', json.dumps(
        {'userId': 'me', 'q': 'from:(luma.com OR lu.ma OR luma-mail.com) newer_than:120d', 'maxResults': 200}))
    for d_m in d_list.get('messages', []):
        d_full = gws('gmail', 'users', 'messages', 'get', '--params', json.dumps(
            {'userId': 'me', 'id': d_m['id'], 'format': 'metadata', 'metadataHeaders': ['Subject', 'Date']}))
        subject = next((h['value'] for h in d_full['payload']['headers'] if h['name'] == 'Subject'), '')
        s = subject.lower()
        state = ('declined' if re.search(r'declin|not approved|unable to', s) else 'waitlist' if 'waitlist' in s
                 else 'pending' if re.search(r'pending|request|approval', s) else 'approved' if 'approved' in s
                 else 'registered' if re.search(r'registered|confirmed|you.re in|ticket|you.re going', s)
                 else 'reminder' if re.search(r'starting|tomorrow|reminder|today', s) else 'other')
        l_items.append(dict(kind='gmail', ext_id=d_m['id'], title=subject, start=None, end=None, urls=set(),
                            extra={'state': state, 'sent': datetime.fromtimestamp(int(d_full['internalDate']) / 1000).date().isoformat()}))
    log(f'gmail: {len(d_list.get("messages", []))} Luma emails')


def read_leads():
    for i, d_l in enumerate(json.loads((ROOT / 'data/historical-events.json').read_text())['events']):
        start = date.fromisoformat(d_l['date'])
        end_m = re.search(r'through (\w{3}) (\d{1,2})', d_l.get('notes') or '')
        end = date(start.year, MONTHS[end_m[1].lower()], int(end_m[2])) if end_m else start
        l_items.append(dict(kind='lead', ext_id=f'lead{i}', title=d_l['title'], start=start, end=end,
                            urls={canon_url(d_l['url'])} if d_l['url'] else set(), extra={'score': d_l['score'], 'notes': d_l['notes']}))


for f in (read_todoist, read_calendars, read_gmail, read_leads):
    try: f()
    except Exception as e: log(f'ERROR {f.__name__}: {e}'); sys.exit(1)

# ---------- 2. match: same URL, or close dates and similar titles ----------
def same_event(a, b):
    # a page linked from several event tasks is a listing (ETH seminar list, DARE calendar), not one event's page
    if (a['urls'] & b['urls']) - s_listing_urls:
        close = not (a['start'] and b['start']) or abs((a['start'] - b['start']).days) <= 1
        if close and similarity(a['title'], b['title']) >= 0.3: return True   # a source page can list two events
    sim = similarity(a['title'], b['title'])
    if a['start'] and b['start']:
        return abs((a['start'] - b['start']).days) <= 1 and sim >= 0.6
    return sim >= 0.8 and 'gmail' in (a['kind'], b['kind'])   # an email has no event date: needs a very close title

d_url_tasks = {}
for it in l_items:
    if it['kind'] == 'task':
        for u in it['urls']: d_url_tasks.setdefault(u, set()).add(it['ext_id'])
s_listing_urls = {u for u, s_t in d_url_tasks.items() if len(s_t) > 1}
parent = list(range(len(l_items)))
def find(i):
    while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
    return i
for i in range(len(l_items)):
    for j in range(i + 1, len(l_items)):
        a, b = l_items[i], l_items[j]
        if a['kind'] == b['kind'] == 'calendar': continue            # two calendar copies are linked through a task or lead
        if a['kind'] == 'gmail' and b['kind'] == 'gmail': continue
        if same_event(a, b): parent[find(i)] = find(j)

d_clusters = {}
for i, it in enumerate(l_items): d_clusters.setdefault(find(i), []).append(it)
# keep only clusters about the radar's events: a task or a lead, or a calendar event the radar wrote
l_clusters = [l for l in d_clusters.values()
              if any(it['kind'] in ('task', 'lead') or (it['kind'] == 'calendar' and it['extra']['radar']) for it in l)]
log(f'{len(l_items)} items → {len(l_clusters)} events')

# ---------- 3. check each event's pages (status, title) ----------
def check(url):
    try:
        req = urllib.request.Request('https://' + url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh) Chrome/141.0 Safari/537.36'})
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read(400_000).decode('utf-8', 'ignore')
            title = re.search(r'<title[^>]*>(.*?)</title>', html, re.S)
            flags = [w for w in ('Event Full', 'Join Waitlist', 'Approval Required', 'Sold Out', 'Registration Closed', 'This event has ended')
                     if w.lower() in html.lower()]
            return url, r.status, (title[1].strip()[:100] if title else ''), ','.join(flags)
    except Exception as e:
        return url, getattr(e, 'code', 0) or str(e)[:60], '', ''
s_urls = {u for l in l_clusters for it in l for u in it['urls']}
with ThreadPoolExecutor(8) as ex: l_checks = list(ex.map(check, sorted(s_urls)))
d_check = {c[0]: c for c in l_checks}
log(f'web: {len(l_checks)} pages checked, {sum(c[1] != 200 for c in l_checks)} not 200')

# ---------- 4. state: one SQLite file ----------
STATE.mkdir(exist_ok=True)
ts = int(time.time()); dt = datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec='seconds')
db = sqlite3.connect(STATE / 'radar.sqlite')
with db:
    db.executescript('''
      DROP TABLE IF EXISTS events; DROP TABLE IF EXISTS items; DROP TABLE IF EXISTS url_checks;
      CREATE TABLE events (ts INT, dt TEXT, event_id INT PRIMARY KEY, title TEXT, start TEXT, end TEXT, urls TEXT);
      CREATE TABLE items (ts INT, dt TEXT, event_id INT, kind TEXT, ext_id TEXT, title TEXT, start TEXT, end TEXT, extra TEXT);
      CREATE TABLE url_checks (ts INT, dt TEXT, url TEXT PRIMARY KEY, status TEXT, page_title TEXT, flags TEXT);''')
    for n, l in enumerate(l_clusters):
        best = next((it for k in ('task', 'lead', 'calendar') for it in l if it['kind'] == k))
        l_dates = [it for it in l if it['start'] and it['kind'] != 'gmail']
        start = min((it['start'] for it in l_dates), default=None); end = max((it['end'] or it['start'] for it in l_dates), default=None)
        l[:] = [dict(it, event_id=n, ev_title=best['title'], ev_start=start, ev_end=end) for it in l]
        db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?)', (ts, dt, n, best['title'], str(start), str(end), ' '.join(sorted({u for it in l for u in it['urls']}))))
        for it in l:
            db.execute('INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?)', (ts, dt, n, it['kind'], it['ext_id'], it['title'], str(it['start']), str(it['end']), json.dumps(it['extra'])))
    db.executemany('INSERT INTO url_checks VALUES (?,?,?,?,?,?)', [(ts, dt, *map(str, c)) for c in l_checks])
db.close()

# ---------- 5. the report ----------
def kinds(l, k): return [it for it in l if it['kind'] == k]
def row(*cells): return '| ' + ' | '.join(str(c).replace('|', '/') for c in cells) + ' |'
def gstate(l): return ', '.join(sorted({g['extra']['state'] for g in kinds(l, 'gmail')})) or '—'
past = [l for l in l_clusters if l[0]['ev_end'] and l[0]['ev_end'] < TODAY]
upcoming = [l for l in l_clusters if l not in past]
L = [f'# Phase 1 report ({dt})', '', 'Read-only: nothing was written to Todoist, Calendar or Gmail.', '',
     '| What | Count |', '|---|---|',
     row('events found', len(l_clusters)), row('… already over', len(past)), row('… upcoming or no date', len(upcoming)),
     row('event tasks', sum(len(kinds(l, 'task')) for l in l_clusters)), row('Couple/other calendar entries matched', sum(len(kinds(l, 'calendar')) for l in l_clusters)),
     row('Luma emails matched', sum(len(kinds(l, 'gmail')) for l in l_clusters)), '']

L += ['## A. Event tasks of events that are over → to delete', '', '| Task id | Task | Event ended |', '|---|---|---|']
L += [row(t['ext_id'], t['title'], l[0]['ev_end']) for l in past for t in kinds(l, 'task')]
L += ['', '## B. Duplicate event tasks (two tasks, one event)', '', '| Event | Task ids | Titles |', '|---|---|---|']
L += [row(l[0]['ev_start'], ' '.join(t['ext_id'] for t in kinds(l, 'task')), ' / '.join(t['title'] for t in kinds(l, 'task')))
      for l in l_clusters if len(kinds(l, 'task')) > 1]
L += ['', '## B2. The same event twice in one calendar', '', '| Event | Calendar | Title | Copies |', '|---|---|---|---|']
for l in l_clusters:
    d_n = {}
    for c in kinds(l, 'calendar'): d_n.setdefault((c['extra']['calendar'], c['title']), []).append(c)
    L += [row(l[0]['ev_start'], cal, title, len(l_c)) for (cal, title), l_c in d_n.items() if len(l_c) > 1]
L += ['', '## B3. Radar entries copied in several calendars (upcoming)', '', '| Event | Calendars |', '|---|---|']
L += [row(l[0]['ev_start'], ', '.join(sorted(c['extra']['calendar'] for c in kinds(l, 'calendar') if c['extra']['radar']))) for l in upcoming
      if len({c['extra']['calendar'] for c in kinds(l, 'calendar') if c['extra']['radar']}) > 1]
L += ['', '## C. Luma emails vs the task title (upcoming)', '', '| Event date | Task | Luma says |', '|---|---|---|']
L += [row(l[0]['ev_start'], ' / '.join(t['title'] for t in kinds(l, 'task')) or '(no task)', gstate(l))
      for l in upcoming if kinds(l, 'gmail')]
L += ['', '## D. ChatGPT leads with no task and no calendar entry (upcoming)', '', '| Date | Lead | Score | Notes |', '|---|---|---|---|']
L += [row(ld['start'], ld['title'], ld['extra']['score'], ld['extra']['notes']) for l in upcoming
      if not kinds(l, 'task') and not kinds(l, 'calendar') for ld in kinds(l, 'lead')]
L += ['', '## E. Upcoming events not on any calendar (phase 3 adds those still open to you)', '', '| Date | Event | Page |', '|---|---|---|']
for l in sorted(upcoming, key=lambda l: str(l[0]['ev_start'])):
    if kinds(l, 'calendar'): continue
    l_c = [d_check[u] for it in l for u in it['urls'] if u in d_check]
    L.append(row(l[0]['ev_start'], l[0]['ev_title'], '; '.join(f'{c[1]} {c[3]}'.strip() for c in l_c[:2]) or 'no URL'))
L += ['', '## F. Event tasks with no event date found', '', '| Task id | Task |', '|---|---|']
L += [row(t['ext_id'], t['title']) for l in l_clusters for t in kinds(l, 'task') if not t['start']]
L += ['', '## G. Pages that did not answer 200', '', '| Status | URL |', '|---|---|']
L += [row(c[1], c[0]) for c in l_checks if c[1] != 200]
L += ['', '## H. Calendar entries the radar wrote, with no event task', '', '| Date | Calendar | Title |', '|---|---|---|']
L += [row(c['start'], c['extra']['calendar'], c['title']) for l in l_clusters if not kinds(l, 'task') for c in kinds(l, 'calendar') if c['extra']['radar']]
(STATE / 'phase1_report.md').write_text('\n'.join(L) + '\n')
log(f'report: {STATE / "phase1_report.md"}')
