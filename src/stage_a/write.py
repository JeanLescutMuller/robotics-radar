"""Stage A: carry out a run's planned writes (Todoist, the shared calendar), each one read back. Called by run.py with --write.

Only these actions write: create_task, update_task, delete_task, add_calendar, update_calendar, remove_calendar. merge_tasks is never automatic.
The shared calendar is public: calendar_body() writes only the event's own facts. The user is a guest of each entry (an invitation in
their own calendar) unless they already have their own entry for it: their "accept" is what stage B registers for.
"""
import json, re
from datetime import date, datetime, timedelta, timezone
from common import TZ, d_cfg, gws, log, todoist

DB_ID = ''   # set by run.py: this state's id, so an event id written in Todoist or Calendar is never read by another state (~/dev vs ~/opt)
CAP = {'create_task': 15, 'add_calendar': 60, 'update_calendar': 60, 'delete_task': 10, 'remove_calendar': 50, 'update_task': 15}   # more = a bug
# remove_calendar 50: the one-off move of the radar's entries out of the Couple calendar (2026-10-21); only radar entries, by marker


def _when(e):
    return f"{e['start']}" + (f" to {e['end']}" if e['end'] else '') + '[Europe/Zurich]'


def task_description(e, act, today, source):
    l = [f"Event: {_when(e)}, {e['venue'] or e['city'] or ('online' if e['online'] else 'venue not published')}. "
              f"Score {e['score']}/100: {e['score_reason'] or ''}",
          f"Organizer: {e['organizer'] or 'unknown'}. Price: {'free' if e['is_free'] else e['price'] or 'unknown'}. Registration: {e['reg_state']}.",
          "This task's due date is the SAFETY DATE to act, not the event date.", '',
          f"**Next step:** {act} on the official page.",
          f"**Done when:** {'attendance planned' if act.startswith(('plan', 'confirm')) else 'registered (confirmation received) or decided not to go'}.", '',
          '**History**', f'- {today}: discovered by Robotics Radar ({source}).', '',
          f"Official / registration: [{e['title']}]({e['reg_url'] or e['url']})" if (e['reg_url'] or e['url']) else 'No official page found yet.',
          f"Robotics Radar event: {DB_ID}-{e['event_id']}", '',
          '<metadata>', 'created_by: job robotics-radar · chan-lescut-macbook-pro', d_cfg['todoist']['description_prefix']]
    if e['deadline']: l.append(f"not_after: {e['deadline'][:10]}[Europe/Zurich]")
    return '\n'.join(l + ['</metadata>'])   # the metadata block, last (skill task-management, 2026-10-21)


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
    today = datetime.now(TZ).date().isoformat(); n_ok = 0; l_err = []

    def done(e, action, target, ok, readback):
        nonlocal n_ok
        db.execute('INSERT INTO writes VALUES (?,?,?,?,?,?,?)', (run_ts, run_dt, e['event_id'], action, target, int(ok), readback[:500]))
        if ok: n_ok += 1
        else: l_err.append(f"{action} {e['title']}: {readback[:200]}")

    for e, action, target, d in sorted(l_plan, key=lambda p: ['delete_task', 'create_task', 'update_task', 'add_calendar', 'update_calendar', 'remove_calendar', 'merge_tasks'].index(p[1])):
        try:
            if action == 'create_task':
                due = date.fromisoformat(d['due']); days = (due - date.fromisoformat(today)).days
                body = {'content': target, 'description': task_description(e, target.split(': ')[-1], today, sources_of(e['event_id'])),
                        'project_id': d_cfg['todoist']['project_id'], 'section_id': d_cfg['todoist']['section_id'],
                        'due_date': d['due'], 'priority': 4 if days <= 1 else 3 if days <= 7 else 2}   # API: 4 = P1
                st, t = todoist('POST', 'tasks', body)
                st2, t2 = todoist('GET', f"tasks/{t['id']}") if t else (st, None)
                ok = bool(t2) and t2['content'] == target and t2['section_id'] == d_cfg['todoist']['section_id']
                if ok: db.execute('UPDATE events SET task_id=? WHERE event_id=?', (t['id'], e['event_id']))
                done(e, action, t['id'] if t else '', ok, f'HTTP {st}/{st2}')
            elif action == 'update_task':
                st0, t0 = todoist('GET', f'tasks/{target}')
                desc = t0['description']
                line = f"- {today}: {d['why']}; title changed by Robotics Radar."
                if '**History**' in desc:   # append to the History list, keep everything else as it is
                    desc = re.sub(r'(\*\*History\*\*\n(?:- [^\n]*\n?)*)', lambda m: m[1].rstrip('\n') + '\n' + line + '\n', desc, count=1)
                else:   # before the metadata block, which stays last
                    body, sep, meta = desc.partition('\n\n<metadata>\n')
                    desc = body.rstrip('\n') + '\n\n**History**\n' + line + (sep + meta if sep else '')
                st, _ = todoist('POST', f'tasks/{target}', {'content': d['new_title'], 'description': desc.rstrip('\n')})
                st2, t2 = todoist('GET', f'tasks/{target}')
                done(e, action, target, bool(t2) and t2['content'] == d['new_title'] and line in t2['description'], f'HTTP {st}/{st2}')
            elif action == 'delete_task':
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
