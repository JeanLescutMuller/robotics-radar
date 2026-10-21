"""Step 1 of a run: discover. Each collector returns candidates: dicts with the fields of REQUIREMENTS.md Normalize.

A candidate: source, key (stable id at the source), title, start/end (ISO with offset, or a date for a whole day),
venue, city, online, organizer, url, reg_url, is_free (True/False/None), price, reg_state, deadline, summary, org_key.
reg_state: open | approval | waitlist | full | closed | not_open | none (no registration) | unknown.
"""
import json, re, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from common import TZ, claude_json, d_cfg, d_src, html_to_text, http_get, log, sha

LUMA = 'https://api.lu.ma'
HORIZON = datetime.now(timezone.utc) + timedelta(days=d_cfg['lookahead_days'])


def luma(db, l_slugs=()):
    """Luma: categories near Zürich, the Zürich page, every watched organiser calendar, and the events linked from event tasks
    (l_slugs); details cached by api_id."""
    d_src_l = d_src['luma']; s_ids = set()

    def page_all(params):
        cursor = None
        while True:
            d = http_get(f'{LUMA}/discover/get-paginated-events?{urllib.parse.urlencode(params | ({"pagination_cursor": cursor} if cursor else {}))}', as_json=True)
            for e in d.get('entries', []):
                if e['event']['start_at'] < HORIZON.isoformat(): yield e
            cursor = d.get('next_cursor')
            if not d.get('has_more') or not cursor: return

    l_feed = []   # (entry, broad): a broad feed's event must match the keywords
    for slug in d_src_l['categories']:
        try:
            cat_id = http_get(f'{LUMA}/url?url={slug}', as_json=True)['data']['category']['api_id']
            l_feed += [(e, True) for e in page_all({'discover_category_api_id': cat_id, 'latitude': d_src_l['latitude'],
                                                    'longitude': d_src_l['longitude'], 'pagination_limit': 50})]
        except Exception as e: log(f'luma category {slug}: {e}')
    place_id = http_get(f'{LUMA}/url?url={d_src_l["place"]}', as_json=True)['data']['place']['api_id']
    l_feed += [(e, True) for e in page_all({'discover_place_api_id': place_id, 'pagination_limit': 50})]
    # watched organisers: the config's slugs, plus the calendars of good events seen before (table organizers)
    s_cal = {_try(lambda s: http_get(f'{LUMA}/url?url={s}', as_json=True)['data']['calendar']['api_id'], s) for s in d_src_l['calendars']} - {None}
    s_cal |= {r[0] for r in db.execute("SELECT org_key FROM organizers WHERE source='luma'")}
    for slug in l_slugs:   # an event task's Luma link: read like any Luma event, so its times and state are Luma's
        d = _try(lambda s: http_get(f'{LUMA}/url?url={s}', as_json=True), slug)
        if d and d.get('kind') == 'event': l_feed.append(({'event': d['data']['event'], 'ticket_info': d['data'].get('ticket_info'),
                                                            'registration_availability': d['data'].get('registration_availability')}, False))
    for cal in s_cal:
        try:
            d = http_get(f'{LUMA}/calendar/get-items?calendar_api_id={cal}&period=future&pagination_limit=50', as_json=True)
            l_feed += [(e, False) for e in d.get('entries', [])]
        except Exception as e: log(f'luma calendar {cal}: {e}')

    def stamp(entry): return json.dumps([entry['event'].get('start_at'), entry.get('ticket_info'), entry.get('registration_availability'), entry.get('waitlist_active')])

    def text_of(n): return (n.get('text', '') + ' ' + ' '.join(text_of(c) for c in n.get('content', []))) if isinstance(n, dict) else ''
    l_out = []
    d_feed = {}
    for e, broad in l_feed: d_feed[e['event']['api_id']] = (e, broad and d_feed.get(e['event']['api_id'], (e, True))[1])
    # one GET per event, only when Luma's list says it changed since the cached copy (the database stays in this thread)
    d_cached = {}
    for api_id, (entry, _) in d_feed.items():
        row = db.execute('SELECT stamp, body FROM luma_cache WHERE api_id=?', (api_id,)).fetchone()
        if row and row[0] == stamp(entry): d_cached[api_id] = json.loads(row[1])
    def fetch(api_id): return _try(lambda: http_get(f'{LUMA}/event/get?event_api_id={api_id}', as_json=True))
    l_todo = [a for a in d_feed if a not in d_cached]
    with ThreadPoolExecutor(8) as ex: d_fetched = dict(zip(l_todo, ex.map(fetch, l_todo)))
    for api_id, d in d_fetched.items():
        if d: db.execute('INSERT OR REPLACE INTO luma_cache VALUES (?,?,?)', (api_id, stamp(d_feed[api_id][0]), json.dumps(d)))
    l_det = [(t, d_cached.get(a) or d_fetched.get(a)) for a, t in d_feed.items()]
    for (entry, broad), d in l_det:
        if not d: continue
        ev, ti = d['event'], d.get('ticket_info') or {}
        geo = ev.get('geo_address_info') or {}
        online = ev.get('location_type') == 'online'
        summary = text_of(d.get('description_mirror') or {}).strip()
        if not online and geo.get('country') and geo['country'] not in d_src_l['countries']: continue
        if broad and not re.search(d_src['keywords'], ev['name'] + ' ' + summary): continue
        avail = d.get('registration_availability') or ''
        reg_state = ('waitlist' if (ti.get('is_sold_out') or avail == 'sold-out') and (entry.get('waitlist_active') or d.get('waitlist_active'))
                     else 'full' if ti.get('is_sold_out') or avail == 'sold-out' else 'closed' if avail == 'closed'
                     else 'not_open' if avail == 'not-open-yet' else 'approval' if ti.get('require_approval') else 'open')
        price = None if ti.get('is_free') else (f"{ti.get('price', {}).get('cents', 0) / 100:.0f} {ti.get('price', {}).get('currency', '').upper()}"
                                               if isinstance(ti.get('price'), dict) else str(ti.get('price')))
        l_out.append(dict(source='luma', key=ev['api_id'], title=ev['name'], start=_local(ev['start_at']), end=_local(ev.get('end_at')),
                          venue=geo.get('full_address') or geo.get('address') or ('online' if online else ''), city=geo.get('city') or '',
                          online=online, organizer=(d.get('calendar') or {}).get('name') or ', '.join(h.get('name', '') for h in d.get('hosts', [])),
                          url=f"https://luma.com/{ev['url']}", reg_url=f"https://luma.com/{ev['url']}", is_free=ti.get('is_free'),
                          price=price, reg_state=reg_state, deadline=None, summary=summary[:1500],
                          org_key=(d.get('calendar') or {}).get('api_id')))
    log(f'luma: {len(d_feed)} events read, {len(l_out)} kept')
    return l_out


def voxel51(db):
    """Voxel51's public CMS (Sanity): upcoming events, online or in Switzerland."""
    q = ('*[_type=="event" && status=="public" && eventDate >= $today]{title, "slug": slug.current, eventDate, timeString, locationText,'
         ' isExternal, externalUrl, "summary": pt::text(eventSummary), "region": region->title, "format": formats[0]->title}')
    url = f"{d_src['voxel51']['sanity_url']}?query={urllib.parse.quote(q)}&%24today=%22{datetime.now(TZ).date()}%22"
    l_out = []
    for e in http_get(url, as_json=True)['result']:
        if not re.search(d_src['voxel51']['keep_if'], f"{e.get('locationText')} {e.get('region')} {e.get('format')}"): continue
        start, end = _voxel_time(e['eventDate'], e.get('timeString') or '')
        page = f"https://voxel51.com/events/{e['slug']}"
        l_out.append(dict(source='voxel51', key=e['slug'], title=e['title'], start=start, end=end, venue=e.get('locationText') or '',
                          city='', online=bool(re.search(r'(?i)online|zoom|virtual', e.get('locationText') or '')), organizer='Voxel51',
                          url=page, reg_url=e.get('externalUrl') or page, is_free=True, price=None, reg_state='open', deadline=None,
                          summary=(e.get('summary') or '')[:1500], org_key='voxel51'))
    log(f'voxel51: {len(l_out)} kept')
    return l_out


def pages(db, l_cost):
    """Listing pages (ETH, UZH, DARE…): Claude reads a page only when its text changed; otherwise its last events are reused."""
    l_out = []
    today = datetime.now(TZ).date().isoformat()
    for url in d_src['pages']:
        try: text = html_to_text(http_get(url))[:40_000]
        except Exception as e: log(f'page {url}: {e}'); continue
        h = sha(text)
        row = db.execute('SELECT hash, events FROM pages WHERE url=?', (url,)).fetchone()
        if row and row[0] == h: l_ev = json.loads(row[1])
        else:
            prompt = f"""Today is {today}, timezone Europe/Zurich. Below is the text of the web page {url}.
List every event on it that takes place between today and {HORIZON.date()}: talks, seminars, meetups, workshops, hackathons, conferences, courses.
Answer ONLY a JSON array, no prose. One object per event:
{{"title": "Speaker Name: talk title" when the page names a speaker, else the event's name, "start": "YYYY-MM-DDTHH:MM" local time or "YYYY-MM-DD" if no time, "end": same format or null,
"venue": str or "", "city": str or "", "online": bool, "organizer": str or "", "url": the event's own link from the page (absolute) or null,
"registration": "open" | "approval" | "waitlist" | "full" | "closed" | "not_open" | "none" (no registration needed) | "unknown",
"price": str or null, "free": true | false | null, "deadline": "YYYY-MM-DD" or null, "summary": one sentence}}
Copy facts from the page only; never guess. An empty array if there is none.

PAGE TEXT:
{text}"""
            try:
                l_ev, cost = claude_json(prompt, d_src['models']['extract']); l_cost.append(cost)
            except Exception as e: log(f'page {url}: claude: {e}'); continue
            db.execute('INSERT OR REPLACE INTO pages VALUES (?,?,?,?)', (url, h, json.dumps(l_ev), datetime.now(timezone.utc).isoformat()))
            log(f'page {url}: changed, {len(l_ev)} events read')
        for e in l_ev:
            if not e.get('title') or not e.get('start'): continue
            l_out.append(dict(source='page', key=f"{url}#{e['title']}#{e['start']}", title=e['title'], start=_with_tz(e['start']),
                              end=_with_tz(e.get('end')), venue=e.get('venue') or '', city=e.get('city') or '', online=bool(e.get('online')),
                              organizer=e.get('organizer') or '', url=e.get('url') or url, reg_url=e.get('url') or url, is_free=e.get('free'),
                              price=e.get('price'), reg_state=e.get('registration') or 'unknown', deadline=e.get('deadline'),
                              summary=e.get('summary') or '', org_key=None))
    log(f'pages: {len(l_out)} events')
    return l_out


def broad_search(db, l_known_titles, l_cost):
    """At most every broad_search_days: Claude searches the web for events no source above knows."""
    row = db.execute("SELECT max(ts) FROM runs WHERE broad_search=1").fetchone()
    if row[0] and datetime.now(timezone.utc).timestamp() - row[0] < d_src['broad_search_days'] * 86400: return [], False
    today = datetime.now(TZ).date()
    prompt = f"""Today is {today}. Search the web for upcoming events between {today} and {HORIZON.date()} in Zürich or elsewhere in
Switzerland (or online, if strongly about robotics) about: robotics, embodied / Physical AI, humanoids, robot learning, manipulation,
autonomous systems, computer vision for robotics, VLM evaluation, autonomous manufacturing, robotics startups, hardware / deep tech.
Look at organisers such as Swiss Robotics Association, ETH RobotX, ETH and UZH robotics labs, EPFL, DARE Campus, Zürich AI ecosystem,
Women in Robotics Switzerland, Switzerland Innovation Park Zürich, Founderful, ANYbotics, ABB Robotics, Hexagon, RIVR, Ascento,
Google Zürich (Founder's Stories, TEDx Europaallee), Meetup, Eventbrite, and others you find.
SKIP these already known events: {json.dumps(l_known_titles, ensure_ascii=False)}
Confirm each event on its official page. Answer ONLY a JSON array (max 20) of objects:
{{"title", "start": "YYYY-MM-DDTHH:MM" local or "YYYY-MM-DD", "end", "venue", "city", "online": bool, "organizer", "url": official page,
"registration": "open|approval|waitlist|full|closed|not_open|none|unknown", "price", "free": bool or null, "deadline", "summary"}}"""
    try: l_ev, cost = claude_json(prompt, d_src['models']['search'], tools='WebSearch,WebFetch', max_turns=40, timeout=1800); l_cost.append(cost)
    except Exception as e: log(f'broad search: {e}'); return [], False
    log(f'broad search: {len(l_ev)} events')
    return [dict(source='search', key=f"{e.get('url')}#{e.get('start')}", title=e['title'], start=_with_tz(e['start']), end=_with_tz(e.get('end')),
                 venue=e.get('venue') or '', city=e.get('city') or '', online=bool(e.get('online')), organizer=e.get('organizer') or '',
                 url=e.get('url'), reg_url=e.get('url'), is_free=e.get('free'), price=e.get('price'), reg_state=e.get('registration') or 'unknown',
                 deadline=e.get('deadline'), summary=e.get('summary') or '', org_key=None)
            for e in l_ev if e.get('title') and e.get('start')], True


# ---------- small helpers ----------
def _try(f, *a):
    try: return f(*a)
    except Exception as e: log(f'{f.__name__}: {e}'); return None


def _local(iso_utc):
    if not iso_utc: return None
    return datetime.fromisoformat(iso_utc.replace('Z', '+00:00')).astimezone(TZ).isoformat(timespec='minutes')


def _with_tz(s):
    # "YYYY-MM-DD" stays a whole day; a local time gets Zürich's offset (summer or winter time of that day)
    if not s: return None
    if len(s) == 10: return s
    return datetime.fromisoformat(s[:16]).replace(tzinfo=TZ).isoformat(timespec='minutes')


def _voxel_time(day, time_string):
    # "9:00 AM - 10:00 AM PST" → Zürich time; no time → a whole day
    d_tz = {'PST': 'America/Los_Angeles', 'PDT': 'America/Los_Angeles', 'PT': 'America/Los_Angeles', 'EST': 'America/New_York',
            'EDT': 'America/New_York', 'ET': 'America/New_York', 'CET': 'Europe/Zurich', 'CEST': 'Europe/Zurich', 'GMT': 'UTC', 'UTC': 'UTC',
            'IST': 'Asia/Kolkata', 'BST': 'Europe/London'}
    from zoneinfo import ZoneInfo
    m = re.findall(r'(\d{1,2}):(\d{2})\s*([AP]M)', time_string, re.I)
    z = re.search(r'\b(' + '|'.join(d_tz) + r')\b', time_string)
    if not m or not z: return day, None
    def at(h, mi, ap):
        h = int(h) % 12 + (12 if ap.upper() == 'PM' else 0)
        return datetime.fromisoformat(f'{day}T{h:02d}:{mi}').replace(tzinfo=ZoneInfo(d_tz[z[1]])).astimezone(TZ).isoformat(timespec='minutes')
    return at(*m[0]), at(*m[-1]) if len(m) > 1 else None
