"""Luma, in the radar's own Chrome: stay logged in to the user's Luma account (DESIGN.md §5, option A: user, 2026-10-21).

Luma has no password here: it emails a 6-digit code. login() types the account email, reads ONLY that code email
(from Luma, received after the request, within 3 minutes) through gws, and types it. Anything else Luma asks for
(password, Google, CAPTCHA, passkey): stop, never bypass.
"""
import json, re, time
from common import d_cfg, gws, log

ACCOUNT = d_cfg['luma']['account_email']   # the user's Luma account (private config)


def logged_in(ch):
    # Luma sends a logged-out visitor of /home to /signin (its session cookie luma.auth-session-key lasts a year: verified
    # 2026-10-21; Luma's API on api.lu.ma cannot see that luma.com cookie, so it is no test)
    ch.page.goto('https://luma.com/home', wait_until='domcontentloaded'); ch.page.wait_for_timeout(1500)
    return '/signin' not in ch.page.url


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
    return ok
