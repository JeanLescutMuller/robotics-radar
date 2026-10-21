"""Stage A: carry out a run's planned writes (Todoist, the shared calendar), each one read back. Called by run.py with --write.

Only these actions write: delete_task (an event that is over), add_calendar, update_calendar, remove_calendar. merge_tasks is never automatic.
Event tasks are made by stage B only (user, 2026-10-21).
The shared calendar is public: calendar_body() writes only the event's own facts. The user is a guest of each entry (an invitation in
their own calendar) unless they already have their own entry for it: their "accept" is what stage B registers for.
"""
import json, re
from datetime import date, datetime, timedelta, timezone
from common import TZ, d_cfg, gws, log, todoist

DB_ID = ''   # set by run.py: this state's id, so an event id written in Todoist or Calendar is never read by another state (~/dev vs ~/opt)
CAP = {'add_calendar': 60, 'update_calendar': 60, 'delete_task': 10, 'remove_calendar': 50}   # more = a bug
# remove_calendar 50: the one-off move of the radar's entries out of the Couple calendar (2026-10-21); only radar entries, by marker


FOOTER = 'Updated automatically every day by Robotics Radar. Details change: check the official page before you go.'
REG_WORDS = {'open': 'open', 'approval': 'open, the organiser approves each request', 'waitlist': 'full, waitlist open', 'full': 'full',
             'closed': 'closed', 'none': 'none needed, just come', 'unknown': 'see the official page'}


def calendar_body(e, summary, l_found):
    """The shared calendar's entry: public, so only the event's own facts (no score, no Todoist, nothing about the user)."""
    whole_day = len(e['start']) == 10
    prefix = d_cfg['calendar']['title_prefix']
    title = (prefix if not e['title'].startswith(prefix.strip()) else '') + e['title'] + (' (time not confirmed)' if whole_day else '')
    venue, city = e['venue'] or '', e['city'] or ''
    where = 'online' if e['online'] else (venue + (f', {city}' if city and city.lower() not in venue.lower() else '')).strip(', ') or 'venue not published yet'
    l = ([summary[:1200], ''] if summary else []) + [
        f"Where: {where}", f"Organiser: {e['organizer'] or 'unknown'}", f"Price: {'free' if e['is_free'] else e['price'] or 'unknown'}",
        f"Registration: {REG_WORDS.get(e['reg_state'], e['reg_state'] or 'see the official page')}" + (f"; deadline {e['deadline'][:10]}" if e['deadline'] else '')]
    def link(u): return u if not u or u.startswith('http') else f'https://{u}'   # canonical URLs have no scheme
    if e['reg_url'] and e['reg_url'] != e['url']: l.append(f"Register: {link(e['reg_url'])}")
    l.append(f"Official page: {link(e['url']) or 'not found yet'}")
    if l_found: l.append(f"Found on: {', '.join(l_found)}")
    l += ['', FOOTER, f"Robotics Radar event: {DB_ID}-{e['event_id']} {d_cfg['calendar']['marker']}"]
    desc = '\n'.join(l)
    body = {'summary': title, 'description': desc, 'location': '' if e['online'] else (e['venue'] or e['city'] or '')}
    if whole_day:
        end = date.fromisoformat((e['end'] or e['start'])[:10]) + timedelta(days=1)    # Google's whole-day end is the next day
        body |= {'start': {'date': e['start'][:10]}, 'end': {'date': end.isoformat()}}
    else:
        end = e['end'] if e['end'] and len(e['end']) > 10 else (datetime.fromisoformat(e['start']) + timedelta(hours=2)).isoformat(timespec='minutes')
        def rfc(t): return datetime.fromisoformat(t).isoformat(timespec='seconds')   # Google refuses a time without seconds
        body |= {'start': {'dateTime': rfc(e['start']), 'timeZone': 'Europe/Zurich'}, 'end': {'dateTime': rfc(end), 'timeZone': 'Europe/Zurich'}}
    return body


def entry_diff(ce, body):
    """The fields of a shared-calendar entry that differ from what it should say now."""
    def when(x):
        if 'date' in x: return x['date']
        t = datetime.fromisoformat(x['dateTime']); return (t if t.tzinfo else t.replace(tzinfo=TZ)).astimezone(timezone.utc)
    return ([k for k in ('summary', 'description', 'location') if (ce.get(k) or '').strip() != (body.get(k) or '').strip()]
            + [k for k in ('start', 'end') if when(ce.get(k) or {}) != when(body[k])])


def execute(db, l_plan, d_task_by_id, run_ts, run_dt, sources_of, body_of):
    """l_plan: (event, action, target, details) from run.py. Returns (n_ok, l_errors). Refuses everything above CAP."""
    d_n = {}
    for _, a, _, _ in l_plan: d_n[a] = d_n.get(a, 0) + 1
    over = {a: n for a, n in d_n.items() if a in CAP and n > CAP[a]}
    if over: return 0, [f'write refused: too many planned writes {over} (cap {CAP}): a matching bug?']
    db.execute('CREATE TABLE IF NOT EXISTS writes (ts INT, dt TEXT, event_id INT, action TEXT, target TEXT, ok INT, readback TEXT)')
    n_ok = 0; l_err = []

    def done(e, action, target, ok, readback):
        nonlocal n_ok
        db.execute('INSERT INTO writes VALUES (?,?,?,?,?,?,?)', (run_ts, run_dt, e['event_id'], action, target, int(ok), readback[:500]))
        if ok: n_ok += 1
        else: l_err.append(f"{action} {e['title']}: {readback[:200]}")

    for e, action, target, d in sorted(l_plan, key=lambda p: ['delete_task', 'add_calendar', 'update_calendar', 'remove_calendar', 'merge_tasks'].index(p[1])):
        try:
            if action == 'delete_task':
                st, _ = todoist('DELETE', f'tasks/{target}')
                st2, _ = todoist('GET', f'tasks/{target}')
                done(e, action, target, st2 == 404, f'HTTP {st}, readback {st2}')
            elif action == 'add_calendar':
                cal = d_cfg['calendar']['target_id']
                body = body_of(e)
                if d['invite']: body |= {'attendees': [{'email': d_cfg['calendar']['invite_email']}], 'guestsCanSeeOtherGuests': False, 'guestsCanInviteOthers': False}
                ce = gws('calendar', 'events', 'insert', '--params', json.dumps({'calendarId': cal, 'sendUpdates': 'none'}), '--json', json.dumps(body))
                ce2 = gws('calendar', 'events', 'get', '--params', json.dumps({'calendarId': cal, 'eventId': ce['id']}))
                done(e, action, f"{cal}|{ce['id']}", ce2.get('summary') == body['summary'] and d_cfg['calendar']['marker'] in ce2.get('description', ''), ce2.get('htmlLink', ''))
            elif action == 'update_calendar':   # never the guest list: the user's answer stays (a new time makes Google ask again)
                cal, ev_id = target.split('|')
                body = {k: v for k, v in body_of(e).items() if k in d['fields']}
                for k in ('start', 'end'):   # a patch merges: clear the other kind, or whole day → timed fails "Invalid start time"
                    if k in body: body[k] = ({'date': None} | body[k]) if 'dateTime' in body[k] else ({'dateTime': None, 'timeZone': None} | body[k])
                gws('calendar', 'events', 'patch', '--params', json.dumps({'calendarId': cal, 'eventId': ev_id, 'sendUpdates': 'none'}), '--json', json.dumps(body))
                ce2 = gws('calendar', 'events', 'get', '--params', json.dumps({'calendarId': cal, 'eventId': ev_id}))
                done(e, action, target, not entry_diff(ce2, body_of(e)), ','.join(d['fields']))
            elif action == 'remove_calendar':
                cal, ev_id = target.split('|')
                ce = gws('calendar', 'events', 'get', '--params', json.dumps({'calendarId': cal, 'eventId': ev_id}))
                if d_cfg['calendar']['marker'] not in ce.get('description', ''):   # never a user's own event
                    done(e, action, target, False, 'refused: not a radar entry'); continue
                deleted = gws_delete(cal, ev_id)
                try: status = gws('calendar', 'events', 'get', '--params', json.dumps({'calendarId': cal, 'eventId': ev_id})).get('status')
                except RuntimeError as ex: status = 'gone' if re.search(r'404|410|deleted|not found', str(ex), re.I) else f'error {ex}'
                done(e, action, target, deleted and status in ('cancelled', 'gone'), f'status {status}')
        except Exception as ex:
            done(e, action, target, False, f'error: {ex}')
    log(f'writes: {n_ok} ok, {len(l_err)} failed')
    return n_ok, l_err


def gws_delete(cal, ev_id):
    # events.delete answers with an empty body: gws() would fail to parse it
    import subprocess
    out = subprocess.run(['gws', 'calendar', 'events', 'delete', '--params', json.dumps({'calendarId': cal, 'eventId': ev_id, 'sendUpdates': 'none'})],
                         capture_output=True, text=True, timeout=120)
    return out.returncode == 0
