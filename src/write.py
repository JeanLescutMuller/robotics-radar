"""Phase 3: carry out a run's planned writes (Todoist, Couple calendar), each one read back. Called by run.py with --write.

Only these actions write: create_task, update_task, delete_task, add_calendar, remove_calendar. merge_tasks is never automatic.
"""
import json, re, urllib.error, urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from common import TZ, d_cfg, gws, log

API = 'https://api.todoist.com/api/v1'
DB_ID = ''   # set by run.py: this state's id, so an event id written in Todoist or Calendar is never read by another state (~/dev vs ~/opt)
CAP = {'create_task': 15, 'add_calendar': 40, 'delete_task': 10, 'remove_calendar': 10, 'update_task': 15}   # more = a matching bug


def _todoist(method, path, body=None):
    token = re.search(r'TODOIST_API_TOKEN="?([^"\n]+)', (Path.home() / '.config/task-management/todoist_token.env').read_text())[1]
    req = urllib.request.Request(f'{API}/{path}', method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None


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


def calendar_body(e, task_id):
    whole_day = len(e['start']) == 10
    title = d_cfg['calendar']['title_prefix'] + e['title'] + (' (time not confirmed)' if whole_day else '')
    desc = '\n'.join([f"Score {e['score']}/100: {e['score_reason'] or ''}", f"Organizer: {e['organizer'] or 'unknown'}",
                      f"Price: {'free' if e['is_free'] else e['price'] or 'unknown'}",
                      f"Registration: {e['reg_state']}" + (f", deadline {e['deadline']}" if e['deadline'] else '') + (f"; you: {e['user_state']}" if e['user_state'] else ''),
                      f"Registration page: {e['reg_url'] or 'unknown'}", f"Official page: {e['url'] or 'unknown'}", '',
                      (e['summary'] or '')[:600], '',
                      f"Todoist: https://app.todoist.com/app/task/{task_id}" if task_id else '',
                      f"Discovered: {e['first_seen'][:10]}", f"Robotics Radar event: {DB_ID}-{e['event_id']}", d_cfg['calendar']['marker']])
    body = {'summary': title, 'description': desc, 'colorId': d_cfg['calendar']['color_id'], 'location': '' if e['online'] else (e['venue'] or e['city'] or '')}
    if whole_day:
        end = date.fromisoformat((e['end'] or e['start'])[:10]) + timedelta(days=1)    # Google's whole-day end is the next day
        body |= {'start': {'date': e['start'][:10]}, 'end': {'date': end.isoformat()}}
    else:
        end = e['end'] if e['end'] and len(e['end']) > 10 else (datetime.fromisoformat(e['start']) + timedelta(hours=2)).isoformat(timespec='minutes')
        def rfc(t): return datetime.fromisoformat(t).isoformat(timespec='seconds')   # Google refuses a time without seconds
        body |= {'start': {'dateTime': rfc(e['start']), 'timeZone': 'Europe/Zurich'}, 'end': {'dateTime': rfc(end), 'timeZone': 'Europe/Zurich'}}
    return body


def execute(db, l_plan, d_task_by_id, run_ts, run_dt, sources_of):
    """l_plan: (event, action, target, details) from run.py. Returns (n_ok, l_errors). Refuses everything above CAP."""
    d_n = {}
    for _, a, _, _ in l_plan: d_n[a] = d_n.get(a, 0) + 1
    over = {a: n for a, n in d_n.items() if a in CAP and n > CAP[a]}
    if over: return 0, [f'write refused: too many planned writes {over} (cap {CAP}): a matching bug?']
    db.execute('CREATE TABLE IF NOT EXISTS writes (ts INT, dt TEXT, event_id INT, action TEXT, target TEXT, ok INT, readback TEXT)')
    today = datetime.now(TZ).date().isoformat(); n_ok = 0; l_err = []
    d_new_task = {}   # event_id → task id created this run, for the calendar entry's link

    def done(e, action, target, ok, readback):
        nonlocal n_ok
        db.execute('INSERT INTO writes VALUES (?,?,?,?,?,?,?)', (run_ts, run_dt, e['event_id'], action, target, int(ok), readback[:500]))
        if ok: n_ok += 1
        else: l_err.append(f"{action} {e['title']}: {readback[:200]}")

    for e, action, target, d in sorted(l_plan, key=lambda p: ['delete_task', 'create_task', 'update_task', 'add_calendar', 'remove_calendar', 'merge_tasks'].index(p[1])):
        try:
            if action == 'create_task':
                due = date.fromisoformat(d['due']); days = (due - date.fromisoformat(today)).days
                body = {'content': target, 'description': task_description(e, target.split(': ')[-1], today, sources_of(e['event_id'])),
                        'project_id': d_cfg['todoist']['project_id'], 'section_id': d_cfg['todoist']['section_id'],
                        'due_date': d['due'], 'priority': 4 if days <= 1 else 3 if days <= 7 else 2}   # API: 4 = P1
                st, t = _todoist('POST', 'tasks', body)
                st2, t2 = _todoist('GET', f"tasks/{t['id']}") if t else (st, None)
                ok = bool(t2) and t2['content'] == target and t2['section_id'] == d_cfg['todoist']['section_id']
                if ok: d_new_task[e['event_id']] = t['id']; db.execute('UPDATE events SET task_id=? WHERE event_id=?', (t['id'], e['event_id']))
                done(e, action, t['id'] if t else '', ok, f'HTTP {st}/{st2}')
            elif action == 'update_task':
                st0, t0 = _todoist('GET', f'tasks/{target}')
                desc = t0['description']
                line = f"- {today}: {d['why']}; title changed by Robotics Radar."
                if '**History**' in desc:   # append to the History list, keep everything else as it is
                    desc = re.sub(r'(\*\*History\*\*\n(?:- [^\n]*\n?)*)', lambda m: m[1].rstrip('\n') + '\n' + line + '\n', desc, count=1)
                else:   # before the metadata block, which stays last
                    body, sep, meta = desc.partition('\n\n<metadata>\n')
                    desc = body.rstrip('\n') + '\n\n**History**\n' + line + (sep + meta if sep else '')
                st, _ = _todoist('POST', f'tasks/{target}', {'content': d['new_title'], 'description': desc.rstrip('\n')})
                st2, t2 = _todoist('GET', f'tasks/{target}')
                done(e, action, target, bool(t2) and t2['content'] == d['new_title'] and line in t2['description'], f'HTTP {st}/{st2}')
            elif action == 'delete_task':
                st, _ = _todoist('DELETE', f'tasks/{target}')
                st2, _ = _todoist('GET', f'tasks/{target}')
                done(e, action, target, st2 == 404, f'HTTP {st}, readback {st2}')
            elif action == 'add_calendar':
                cal = d_cfg['calendar']['target_id']
                body = calendar_body(e, d_new_task.get(e['event_id']) or (e['task_id'] or '').split(' ')[0] or None)
                ce = gws('calendar', 'events', 'insert', '--params', json.dumps({'calendarId': cal}), '--json', json.dumps(body))
                ce2 = gws('calendar', 'events', 'get', '--params', json.dumps({'calendarId': cal, 'eventId': ce['id']}))
                done(e, action, f"{cal}|{ce['id']}", ce2.get('summary') == body['summary'] and d_cfg['calendar']['marker'] in ce2.get('description', ''), ce2.get('htmlLink', ''))
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
    out = subprocess.run(['gws', 'calendar', 'events', 'delete', '--params', json.dumps({'calendarId': cal, 'eventId': ev_id})],
                         capture_output=True, text=True, timeout=120)
    return out.returncode == 0
