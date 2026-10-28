"""Stage B, the private registration stage, one run (DESIGN.md §5): register the user for the events they accepted in the shared calendar,
and show how it went in the title of their copy of the entry, in their private calendar (never in the shared calendar: public).

The trigger is the user's answer only (user, 2026-10-21): "Yes" on the invitation stage A puts in their private calendar.
  accepted, Luma, free, every answer known      → the form is filled and sent                       (group auto)
  accepted, Luma, free, a question needs them   → Claude drafts, a comment on the event task, the user's "ok" sends it (ask first)
  accepted, not Luma / paid / closed            → a comment: register yourself, here                (by hand)
  declined after the radar registered them      → a comment: cancel it on Luma
  Luma says pending or waitlist                 → read Luma's page again every run, until the host approves
Reads:  the shared calendar (gws), Luma's public API and the event page in the radar's Chrome (logged in to the user's Luma
        account), stage A's state/radar.sqlite (read-only: which Todoist task is the event's), Todoist comments (the user's "ok").
Writes: state/register.sqlite, state/register_report.md, Todoist (comments on the event task; the task itself if there is none),
        the private calendar: the title of the user's copy of each accepted (or declined) entry, `🤖 <status> <title>` (STATUS).
        Writes to Todoist only with --write and dry_run: false; Luma's last click also needs registration.submit: true (trust ramp:
        until then the form is filled, a screenshot saved in state/shots/, nothing sent).
Run:    .venv/bin/python src/stage_b/run.py [--write] > state/register.log 2>&1
"""
import json, re, sqlite3, sys, time
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # src/: common.py, shared with stage A
import register
from chrome import Chrome
from luma import login
from common import STATE, TZ, d_cfg, gws, log, todoist, todoist_get

WRITING = '--write' in sys.argv and d_cfg.get('dry_run') is False
SUBMIT = WRITING and d_cfg['registration'].get('submit') is True
SHARED, ME, MARKER = d_cfg['calendar']['target_id'], d_cfg['calendar']['invite_email'].lower(), d_cfg['calendar']['marker']
PREFIX = d_cfg['calendar']['title_prefix']
DONE = ('registered', 'pending', 'waitlist')        # on Luma: nothing left to fill; pending and waitlist are read again until registered
# state → the status in the title of the user's copy (user, 2026-10-28); a state not here (new): the shared entry's own title
STATUS = {'registered': '✅', 'pending': '⏳ pending:', 'waitlist': '⏳ waitlist:', 'waiting': '❓ your ok:', 'filled': '📝 not sent:',
          'by hand': '✋ register yourself:', 'failed': '⚠️ failed:', 'told to cancel': '✋ cancel on Luma:'}
RUN_TS = int(time.time()); RUN_DT = datetime.fromtimestamp(RUN_TS, timezone.utc).isoformat(timespec='seconds')
NOW = datetime.now(TZ).strftime('%Y-%m-%d %H:%M')

STATE.mkdir(exist_ok=True)
db = sqlite3.connect(STATE / 'register.sqlite', isolation_level=None)
db.row_factory = sqlite3.Row
# state: new · waiting (asked the user) · filled (trust ramp) · registered/pending/waitlist · by hand · failed · told to cancel
db.execute('''CREATE TABLE IF NOT EXISTS registrations (ts INT, dt TEXT, entry_id TEXT PRIMARY KEY, event_ref TEXT, title TEXT, start TEXT,
  url TEXT, grp TEXT, state TEXT, why TEXT, questions TEXT, answers TEXT, task_id TEXT, asked_at TEXT, shot TEXT, by_radar INT)''')
l_errors, l_done = [], []   # l_done: (title, what happened) for the report


def entries():
    """The shared calendar's radar entries from now on, with the user's answer."""
    l, token = [], None
    t_min = datetime.now(timezone.utc).isoformat(); t_max = (datetime.now(timezone.utc) + timedelta(days=200)).isoformat()
    while True:
        d = gws('calendar', 'events', 'list', '--params', json.dumps({'calendarId': SHARED, 'timeMin': t_min, 'timeMax': t_max, 'singleEvents': True,
                                                                      'maxResults': 250} | ({'pageToken': token} if token else {})))
        l += [ce for ce in d.get('items', []) if MARKER in (ce.get('description') or '')]
        token = d.get('nextPageToken')
        if not token: return l


def line(desc, label):
    m = re.search(rf'^{label}: (\S+)', desc or '', re.M)
    return m[1] if m else None


def save(entry_id, **d):
    d |= {'ts': RUN_TS, 'dt': RUN_DT}
    db.execute(f"UPDATE registrations SET {', '.join(f'{k}=?' for k in d)} WHERE entry_id=?", (*d.values(), entry_id))


def event_task(r, todo):
    """The event's Todoist task, made here when the user must act (todo: what, for the title): the only place event tasks are made
    (user, 2026-10-21: a task only for an event the user accepted and the radar could not register). An older task of the event (from
    before, found in stage A's state by the event id) is used instead; stage A finds a task made here by the same id."""
    if r['task_id']: return r['task_id']
    db_id, n = r['event_ref'].rsplit('-', 1)
    try:
        a = sqlite3.connect(f"file:{STATE / 'radar.sqlite'}?mode=ro", uri=True)
        if a.execute("SELECT v FROM meta WHERE k='db_id'").fetchone()[0] == db_id:
            row = a.execute('SELECT task_id FROM events WHERE event_id=?', (int(n),)).fetchone()
            if row and row[0]: return row[0].split()[0]
    except sqlite3.Error as e: log(f'radar.sqlite: {e}')
    if not WRITING: return None
    desc = '\n'.join([f"Event: {r['start']}[Europe/Zurich]", '', "You accepted this event in the robotics calendar; the radar could not register you by itself.", '',
                      f"**Next step:** {todo} (the radar's comment below says how).", '**Done when:** registered (confirmation received) or decided not to go.', '',
                      '**History**', f'- {NOW[:10]}: accepted in the calendar; task made by Robotics Radar (stage B).', '',
                      f"Official / registration: [{r['title']}]({r['url']})", f"Robotics Radar event: {r['event_ref']}", '',
                      '<metadata>', 'created_by: job robotics-radar.register · chan-lescut-macbook-pro', d_cfg['todoist']['description_prefix'], '</metadata>'])
    st, t = todoist('POST', 'tasks', {'content': f"{r['title']}: {todo}", 'description': desc, 'project_id': d_cfg['todoist']['project_id'],
                                      'section_id': d_cfg['todoist']['section_id'], 'due_date': datetime.now(TZ).date().isoformat(), 'priority': 4})
    if not t: l_errors.append(f"task for {r['title']}: HTTP {st}"); return None
    save(r['entry_id'], task_id=t['id'])
    return t['id']


def tell(r, text, todo='register'):
    """A comment on the event task (made if needed, titled "<event>: <todo>"). Returns its posted_at, or None (dry-run or failed)."""
    tid = event_task(r, todo)
    if not WRITING or not tid: log(f"would comment on {r['title']}: {text[:200]}"); return None
    st, c = todoist('POST', 'comments', {'task_id': tid, 'content': text})
    if not c: l_errors.append(f"comment on {r['title']}: HTTP {st}"); return None
    return c['posted_at']


def approval(r):
    """The user's reply after the radar's question: {question number: answer} when it says "ok", else None."""
    tid = r['task_id'] or event_task(r, 'approve the answers')
    if not tid or not r['asked_at']: return None
    l = sorted((c for c in todoist_get(f'comments?task_id={tid}&limit=200') if c['posted_at'] > r['asked_at']
                and not c['content'].startswith(('RECOMMENDATION', 'RESULT', 'robotics-radar'))), key=lambda c: c['posted_at'])
    for c in l:
        if re.search(r'^\s*ok\b', c['content'], re.I | re.M):
            return {int(m[1]): m[2].strip() for m in re.finditer(r'^\s*(\d+)\s*[:.)]\s*(.+?)\s*$', c['content'], re.M)}
    return None


def numbered(l_q, l_ans):
    return '\n'.join(f"{i + 1}. {q['label']}{'' if q['required'] else ' (optional)'}: "
                     + ('; '.join(a) if isinstance(a, list) else 'accepted' if a == 'accept' else a if a not in (None, '') else '(left empty)')
                     for i, (q, a) in enumerate(zip(l_q, l_ans)))


stack = ExitStack(); ch = None
def chrome():
    # the radar's Chrome, opened once, only when a page is needed; logged in to Luma (email code) if it is not
    global ch
    if ch is None:
        ch = stack.enter_context(Chrome())
        if not login(ch): raise RuntimeError('Luma login failed (state/shots/)')
    return ch


def step(r, answer):
    """Moves one accepted (or declined) event one step on. r: its row."""
    eid, url = r['entry_id'], r['url']
    if answer == 'declined':
        if r['state'] in DONE and r['by_radar']:
            tell(r, f"robotics-radar {NOW}: you declined \"{r['title']}\" in the calendar, but the radar registered you on Luma ({r['state']}). Cancel it there if you won't go: {url}", 'cancel the registration')
            save(eid, state='told to cancel'); l_done.append((r, 'told to cancel'))
        return
    if r['state'] in ('registered', 'by hand', 'told to cancel') or (r['state'] == 'filled' and not SUBMIT): return
    if r['state'] in ('pending', 'waitlist'):   # the host may approve later (Forgis, approved the next day, 2026-10-24): read Luma again
        state = register.open_event(chrome(), url)
        if state and state != r['state']:
            save(eid, state=state, why=f'Luma now says {state}'); l_done.append((r, f'now {state} on Luma'))
            if r['task_id']: tell(r, f"RESULT robotics-radar {NOW}: Luma now says {state} for \"{r['title']}\".")
        return
    if not register.slug_of(url):
        tell(r, f"robotics-radar {NOW}: you accepted \"{r['title']}\". The radar registers only on Luma: register yourself here: {url}")
        save(eid, state='by hand', grp='by hand', why='not a Luma event'); l_done.append((r, 'by hand: not Luma')); return
    d_over = approval(r) if r['state'] == 'waiting' else None
    if r['state'] == 'waiting' and d_over is None: return   # asked, no "ok" yet: nothing to open
    d = register.luma_data(url); l_q = register.questions(d)
    grp, why = register.classify(d, l_q)
    state = register.open_event(chrome(), url)
    if state:
        save(eid, state=state, grp=grp, why=f'Luma already says {state}'); l_done.append((r, f'already {state} on Luma')); return
    if grp == 'never':
        tell(r, f"robotics-radar {NOW}: you accepted \"{r['title']}\", but the radar can't register you: {why}. Here: {url}")
        save(eid, state='by hand', grp=grp, why=why); l_done.append((r, f'by hand: {why}')); return
    if grp == 'ask first':
        if r['state'] != 'waiting':   # first time: draft, ask
            l_ans, _ = register.draft(r['title'], l_q)
            asked = tell(r, f"RECOMMENDATION robotics-radar {NOW}: you accepted \"{r['title']}\" ({r['start'][:16].replace('T', ' ')}). Its Luma form asks:\n\n"
                            f"{numbered(l_q, l_ans)}\n\nReply \"ok\" in a comment to send it. To change an answer, add lines like \"2: your answer\" "
                            f"to the same comment. \"?\" = only you know it: give it, or the radar can't send. {url}", 'approve the answers')
            save(eid, state='waiting', grp=grp, why=why, questions=json.dumps(l_q, ensure_ascii=False), answers=json.dumps(l_ans, ensure_ascii=False), asked_at=asked)
            l_done.append((r, 'asked you (Todoist comment)')); return
        l_q, l_ans = json.loads(r['questions']), json.loads(r['answers'])
        for n, a in d_over.items():
            if 1 <= n <= len(l_q): l_ans[n - 1] = [x.strip() for x in re.split(r'[;,]', a)] if l_q[n - 1]['qt'] == 'multi-select' else a
        l_miss = [str(i + 1) for i, (q, a) in enumerate(zip(l_q, l_ans)) if q['required'] and a in (None, '', '?')]
        if l_miss:
            asked = tell(r, f"robotics-radar {NOW}: still missing for \"{r['title']}\": answer {', '.join(l_miss)}. Reply \"ok\" with lines like \"{l_miss[0]}: your answer\".", 'approve the answers')
            save(eid, answers=json.dumps(l_ans, ensure_ascii=False), asked_at=asked or r['asked_at']); return
    else:
        l_ans = [register.known(q) for q in l_q]
    state, shot = register.fill(chrome(), url, l_q, l_ans, SUBMIT)
    save(eid, state=state if state in DONE + ('filled',) else 'failed', grp=grp, why=why, answers=json.dumps(l_ans, ensure_ascii=False), shot=str(shot), by_radar=int(SUBMIT))   # the radar clicked submit, even when Luma showed no state yet
    if state in DONE:
        if r['state'] == 'waiting':   # a task exists only when the user was asked: none for an autonomous registration
            tell(r, f"RESULT robotics-radar {NOW}: registration sent on Luma for \"{r['title']}\"; Luma says: {state}. Answers:\n\n{numbered(l_q, l_ans)}", 'approve the answers')
    elif state == 'filled':
        tell(r, f"robotics-radar {NOW}: form filled for \"{r['title']}\" but not sent (trust ramp: registration.submit is false). Screenshot on the Mac: {shot}", 'check the filled form')
    else:
        tell(r, f"robotics-radar {NOW}: the radar sent the form for \"{r['title']}\" but Luma shows no confirmation. Check here: {url}", 'check the registration')
        l_errors.append(f"{r['title']}: no confirmation after submit ({shot})")
    l_done.append((r, state))


def show_status(ce, state):
    """The status in the title of the user's copy of the entry (same event id, in their private calendar); the shared entry keeps its title.
    Tested 2026-10-28: a guest's title change stays in their copy, and a later change of the shared title does not overwrite it, so the
    title is rebuilt from the shared one on every run."""
    title = ce.get('summary', '')
    if state in STATUS: title = f"{PREFIX}{STATUS[state]} {title.removeprefix(PREFIX)}"
    mine = gws('calendar', 'events', 'get', '--params', json.dumps({'calendarId': ME, 'eventId': ce['id']}))
    if mine.get('summary') == title: return
    if not WRITING: log(f"would rename in the private calendar: {mine.get('summary')} → {title}"); return
    gws('calendar', 'events', 'patch', '--params', json.dumps({'calendarId': ME, 'eventId': ce['id'], 'sendUpdates': 'none'}), '--json', json.dumps({'summary': title}))
    after = gws('calendar', 'events', 'get', '--params', json.dumps({'calendarId': ME, 'eventId': ce['id']})).get('summary')
    shared = gws('calendar', 'events', 'get', '--params', json.dumps({'calendarId': SHARED, 'eventId': ce['id']})).get('summary')
    if after != title or shared != ce.get('summary'): l_errors.append(f"title of {title}: reads back {after!r}, shared {shared!r}")
    else: log(f'renamed in the private calendar: {title}')


# ---------- the accepted (and declined) events ----------
l_ce = entries()
d_answer, d_ce = {}, {ce['id']: ce for ce in l_ce}
for ce in l_ce:
    answer = next((a.get('responseStatus') for a in ce.get('attendees') or [] if a['email'].lower() == ME), None)
    desc = ce.get('description') or ''
    if answer not in ('accepted', 'declined'): continue
    if answer == 'declined' and not db.execute('SELECT 1 FROM registrations WHERE entry_id=?', (ce['id'],)).fetchone(): continue
    start = (ce['start'].get('dateTime') or ce['start'].get('date'))
    db.execute('INSERT OR IGNORE INTO registrations (ts, dt, entry_id, event_ref, title, start, url, state) VALUES (?,?,?,?,?,?,?,?)',
               (RUN_TS, RUN_DT, ce['id'], re.search(r'Robotics Radar event: (\S+)', desc)[1], re.sub(r'^\W+\s*', '', ce.get('summary', '')).replace(' (time not confirmed)', ''),
                start, line(desc, 'Register') or line(desc, 'Official page'), 'new'))
    d_answer[ce['id']] = answer
log(f"{len(l_ce)} entries in the shared calendar; accepted {sum(a == 'accepted' for a in d_answer.values())}, declined {sum(a == 'declined' for a in d_answer.values())}")
with stack:
    for eid, answer in d_answer.items():
        r = db.execute('SELECT * FROM registrations WHERE entry_id=?', (eid,)).fetchone()
        try: step(r, answer)
        except Exception as e:
            log(f"{r['title']}: {e}"); l_errors.append(f"{r['title']}: {str(e)[:200]}")
            if r['state'] in DONE: continue   # only the check again failed (2026-10-28: Chrome held by another run): Luma's state stands
            if r['state'] == 'failed':   # the second failure: the user takes it
                tell(r, f"robotics-radar {NOW}: the radar could not register you for \"{r['title']}\" ({str(e)[:150]}). Register here: {r['url']}")
                save(eid, state='by hand', why=f'failed twice: {str(e)[:150]}')
            else: save(eid, state='failed', why=str(e)[:200])
    for eid in d_answer:
        try: show_status(d_ce[eid], db.execute('SELECT state FROM registrations WHERE entry_id=?', (eid,)).fetchone()[0])
        except Exception as e: l_errors.append(f"title of {d_ce[eid].get('summary')}: {str(e)[:200]}")

# ---------- the report ----------
def row(*cells): return '| ' + ' | '.join(str(c if c is not None else '').replace('|', '/').replace('\n', ' ') for c in cells) + ' |'
L = [f"# Registration run {RUN_DT} ({'WRITES' + (', SUBMIT on' if SUBMIT else ', submit off: forms filled, not sent') if WRITING else 'DRY-RUN: nothing written'})", '',
     '| Event date | Event | Your answer | Group | State | Why |', '|---|---|---|---|---|---|']
for r in db.execute('SELECT * FROM registrations ORDER BY start'):
    if r['start'][:10] >= datetime.now(TZ).date().isoformat(): L.append(row(r['start'][:16], r['title'], d_answer.get(r['entry_id'], '—'), r['grp'], r['state'], r['why']))
L += ['', '## This run', ''] + [f"- {r['title']}: {what}" for r, what in l_done] + (['', '## Errors', ''] + [f'- {x}' for x in l_errors] if l_errors else [])
(STATE / 'register_report.md').write_text('\n'.join(L) + '\n')
log(f"registration: {len(l_done)} steps, {len(l_errors)} errors; report {STATE / 'register_report.md'}")
sys.exit(1 if l_errors else 0)
