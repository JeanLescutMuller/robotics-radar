"""Luma, in the radar's own Chrome: stay logged in to the user's Luma account (DESIGN.md §5, option A: user, 2026-10-21).

Luma has no password here: it emails a 6-digit code. login() types the account email, gets ONLY that code (from a verified
Luma sender, received after the request, within 3 minutes) from the communication gateway (`incoming-firewall code`, skill
communication-gateway: the code alone, never the message), and types it. Anything else Luma asks for (password, Google,
CAPTCHA, passkey): stop, never bypass. Afterwards the login's emails (the codes, "New sign-in to Luma") are read, labelled and
archived through the gateway (tidy_inbox): kept, out of the user's Inbox (user, 2026-10-21: jobs clean the inbox after they work).
Gmail is never read directly (no `gws gmail`; user, 2026-11-09): every email goes through the gateway, client robotics-radar.
"""
import re, time
from common import d_cfg, firewall, log, mail_search

ACCOUNT = d_cfg['luma']['account_email']   # the user's Luma account (private config)


def logged_in(ch):
    # Luma sends a logged-out visitor of /home to /signin (its session cookie luma.auth-session-key lasts a year: verified
    # 2026-10-21; Luma's API on api.lu.ma cannot see that luma.com cookie, so it is no test)
    ch.page.goto('https://luma.com/home', wait_until='domcontentloaded'); ch.page.wait_for_timeout(1500)
    return '/signin' not in ch.page.url


LABEL = 'Professional/Robotics'   # the Gmail label of the subject (skill tasks, "Linking")
LOGIN_MAIL = r'sign-in code|new sign-in to luma|log-?in code|verification code'


LUMA_MAIL = 'from:(luma.com OR lu.ma OR luma-mail.com)'   # Luma's sending domains (Gmail query)
CODE_FROM = ['luma-mail.com', 'lu.ma', 'luma.com']            # the same, for `incoming-firewall code` (the gateway's scope code_from)


def tidy_inbox(since_ts, wait_s=0):
    """Labels, marks read and archives Luma's login emails received since since_ts (epoch seconds); waits up to wait_s for a late one
    ("New sign-in to Luma" comes a few seconds after the login). Never deletes. Through the gateway: `search` (the code email is a
    security message to it: no subject, a placeholder, firewall_notes['security_message']), then `file` on what it read."""
    n, s_seen, t_end, notice = 0, set(), time.time() + wait_s, False
    while True:
        for ts, subject, mid, d_notes in mail_search(f'{LUMA_MAIL} in:inbox newer_than:1d', limit=20):
            if mid in s_seen: continue
            s_seen.add(mid)
            if ts < since_ts or not (d_notes.get('security_message') or re.search(LOGIN_MAIL, subject, re.I)): continue
            firewall('file', mid, '--label', LABEL, '--archive', '--read')
            n += 1; notice |= 'new sign-in' in subject.lower()
        if notice or time.time() >= t_end: break
        time.sleep(5)
    log(f'luma: {n} login emails labelled {LABEL} and archived')
    return n


def _read_code(since_ts):
    # the gateway waits up to 3 minutes for the code email (a verified Luma sender, received after since_ts) and gives the code alone
    d = firewall('code', *sum([['--from', x] for x in CODE_FROM], []), '--since', str(since_ts), '--wait', '180', timeout=260)
    if not d.get('code'): log(f"luma: {d.get('reason', 'no code')}")
    return d.get('code')


def login(ch):
    """Returns True when logged in (already, or after the email code)."""
    if logged_in(ch): return True
    ch.page.goto('https://luma.com/signin', wait_until='networkidle')
    since_ts = int(time.time()) - 5   # epoch seconds: only an email received after the request
    ch.page.fill('input[type=email]', ACCOUNT)
    ch.page.get_by_role('button', name='Continue with Email').click()
    ch.page.wait_for_timeout(4000)
    l_inputs = ch.page.eval_on_selector_all('input', 'l => l.map(i => [i.type, i.name, i.autocomplete, i.inputMode, i.maxLength])')
    if any(i[0] == 'password' for i in l_inputs):
        ch.shot('luma_password_asked'); log('luma: a password is asked: stop'); return False
    code = _read_code(since_ts)
    if not code: ch.shot('luma_no_code'); log('luma: no code email within 3 min: stop'); return False
    ch.page.locator('input[autocomplete=one-time-code]').first.click(); ch.page.keyboard.type(code, delay=80)
    ch.page.wait_for_timeout(5000)
    if ch.page.get_by_role('button', name='Not Now').count(): ch.page.get_by_role('button', name='Not Now').click()   # never create a passkey
    ok = logged_in(ch)
    if not ok: ch.shot('luma_login_failed'); log(f'luma: still logged out after the code; inputs were {l_inputs}')
    else: log('luma: logged in with the email code')
    try: tidy_inbox(since_ts, wait_s=30 if ok else 0)
    except Exception as e: log(f'luma: inbox not tidied: {e}')   # never fails the run
    return ok
