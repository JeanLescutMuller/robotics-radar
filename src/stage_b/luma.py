"""Luma, in the radar's own Chrome: stay logged in to the user's Luma account (DESIGN.md §5, option A: user, 2026-10-21).

Luma has no password here: it emails a 6-digit code. login() types the account email, reads ONLY that code email
(from Luma, received after the request, within 3 minutes) through gws, and types it. Anything else Luma asks for
(password, Google, CAPTCHA, passkey): stop, never bypass. Afterwards the login's emails (the codes, "New sign-in to Luma") are
read, labelled and archived (tidy_inbox): kept, out of the user's Inbox (user, 2026-10-21: jobs clean the inbox after they work).
"""
import json, re, time
from common import d_cfg, gws, log

ACCOUNT = d_cfg['luma']['account_email']   # the user's Luma account (private config)


def logged_in(ch):
    # Luma sends a logged-out visitor of /home to /signin (its session cookie luma.auth-session-key lasts a year: verified
    # 2026-10-21; Luma's API on api.lu.ma cannot see that luma.com cookie, so it is no test)
    ch.page.goto('https://luma.com/home', wait_until='domcontentloaded'); ch.page.wait_for_timeout(1500)
    return '/signin' not in ch.page.url


LABEL = 'Professional/Robotics'   # the Gmail label of the subject (skill task-management, "Linking")
LOGIN_MAIL = r'sign-in code|new sign-in to luma|log-?in code|verification code'


def tidy_inbox(since_ms, wait_s=0):
    """Labels, marks read and archives Luma's login emails received since since_ms; waits up to wait_s for a late one
    ("New sign-in to Luma" comes a few seconds after the login). Never deletes. Gmail scope gmail.modify (gws's login)."""
    label = next(l['id'] for l in gws('gmail', 'users', 'labels', 'list', '--params', json.dumps({'userId': 'me'}))['labels'] if l['name'] == LABEL)
    n, s_seen, t_end, notice = 0, set(), time.time() + wait_s, False
    while True:
        l = gws('gmail', 'users', 'messages', 'list', '--params', json.dumps(
            {'userId': 'me', 'q': 'from:(luma.com OR lu.ma OR luma-mail.com) in:inbox newer_than:1d', 'maxResults': 20})).get('messages', [])
        for m in l:
            if m['id'] in s_seen: continue
            s_seen.add(m['id'])
            d = gws('gmail', 'users', 'messages', 'get', '--params', json.dumps({'userId': 'me', 'id': m['id'], 'format': 'metadata', 'metadataHeaders': ['Subject']}))
            subject = next((h['value'] for h in d['payload']['headers'] if h['name'] == 'Subject'), '')
            if int(d['internalDate']) < since_ms or not re.search(LOGIN_MAIL, subject, re.I): continue
            gws('gmail', 'users', 'messages', 'modify', '--params', json.dumps({'userId': 'me', 'id': m['id']}),
                '--json', json.dumps({'addLabelIds': [label], 'removeLabelIds': ['INBOX', 'UNREAD']}))
            n += 1; notice |= 'new sign-in' in subject.lower()
        if notice or time.time() >= t_end: break
        time.sleep(5)
    log(f'luma: {n} login emails labelled {LABEL} and archived')
    return n


def _read_code(since_ms):
    for _ in range(36):   # 3 minutes
        l = gws('gmail', 'users', 'messages', 'list', '--params', json.dumps(
            {'userId': 'me', 'q': 'from:(luma.com OR lu.ma OR luma-mail.com) newer_than:1h', 'maxResults': 5})).get('messages', [])
        for m in l:
            d = gws('gmail', 'users', 'messages', 'get', '--params', json.dumps({'userId': 'me', 'id': m['id'], 'format': 'metadata', 'metadataHeaders': ['Subject']}))
            if int(d['internalDate']) < since_ms: continue
            subject = next((h['value'] for h in d['payload']['headers'] if h['name'] == 'Subject'), '')
            code = re.search(r'\b(\d{6})\b', subject + ' ' + d.get('snippet', ''))
            if code and re.search(r'code|sign|log', subject + d.get('snippet', ''), re.I): return code[1]
        time.sleep(5)
    return None


def login(ch):
    """Returns True when logged in (already, or after the email code)."""
    if logged_in(ch): return True
    ch.page.goto('https://luma.com/signin', wait_until='networkidle')
    since_ms = int(time.time() * 1000) - 5000
    ch.page.fill('input[type=email]', ACCOUNT)
    ch.page.get_by_role('button', name='Continue with Email').click()
    ch.page.wait_for_timeout(4000)
    l_inputs = ch.page.eval_on_selector_all('input', 'l => l.map(i => [i.type, i.name, i.autocomplete, i.inputMode, i.maxLength])')
    if any(i[0] == 'password' for i in l_inputs):
        ch.shot('luma_password_asked'); log('luma: a password is asked: stop'); return False
    code = _read_code(since_ms)
    if not code: ch.shot('luma_no_code'); log('luma: no code email within 3 min: stop'); return False
    ch.page.locator('input[autocomplete=one-time-code]').first.click(); ch.page.keyboard.type(code, delay=80)
    ch.page.wait_for_timeout(5000)
    if ch.page.get_by_role('button', name='Not Now').count(): ch.page.get_by_role('button', name='Not Now').click()   # never create a passkey
    ok = logged_in(ch)
    if not ok: ch.shot('luma_login_failed'); log(f'luma: still logged out after the code; inputs were {l_inputs}')
    else: log('luma: logged in with the email code')
    try: tidy_inbox(since_ms, wait_s=30 if ok else 0)
    except Exception as e: log(f'luma: inbox not tidied: {e}')   # never fails the run
    return ok
