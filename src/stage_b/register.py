"""Stage B, the private registration stage: one Luma registration - read the form's questions, decide the group, draft answers, fill the form, submit.

Groups (DESIGN.md §5), from Luma's own data (the event's registration_questions), never by clicking:
  auto       every required question has a known answer (config form:, terms accepted) → register
  ask first  a required question needs the user's own words (text, dropdown, url, phone…) → Claude drafts, the user says "ok"
  never      paid or closed → the user is told; the radar never pays
Trust ramp: while registration.submit is false, the form is filled but the last click is not made: a screenshot instead.
"""
import json, re
from pathlib import Path
from common import claude_json, d_cfg, d_src, http_get, log

KNOWN = {'linkedin': 'linkedin', 'company': 'company', 'job_title': 'role', 'phone': 'phone'}   # question → config form: key
ACCEPT = {'terms', 'agree-check'}                                                              # agreements: accepted and recorded
# Luma's status block, a whole line each (seen 2026-10-21: "You’re In", "Pending Approval"); a description's "See you there!" never matches
DONE_LINES = {'registered': r"you[’']re (in|going)|you[’']re registered", 'pending': r'pending approval', 'waitlist': r"(you[’']re )?on the waitlist"}


def slug_of(url):
    m = re.search(r'(?:luma\.com|lu\.ma)/([A-Za-z0-9_-]+)', url or '')
    return m[1] if m else None


def luma_data(url):
    return http_get(f'https://api.lu.ma/url?url={slug_of(url)}', as_json=True)['data']


def questions(d):
    """The form's questions, in the form's order: [{key, label, qt, options, required}]. Phone and job title are Luma fields, not questions."""
    l_q = [{'key': 'phone', 'label': 'Phone Number', 'qt': 'phone', 'options': [], 'required': True}] if d.get('phone_number_requirement') == 'required' else []
    for q in d.get('registration_questions') or []:
        l_q.append({'key': q['question_type'], 'label': q.get('label', ''), 'qt': q['question_type'], 'options': q.get('options') or [], 'required': bool(q.get('required'))})
        if q.get('collect_job_title'): l_q.append({'key': 'job_title', 'label': q.get('job_title_label') or 'job title', 'qt': 'job_title', 'options': [], 'required': bool(q.get('required'))})
    return l_q


def known(q):
    if q['qt'] in ACCEPT: return 'accept'
    return d_cfg['form'].get(KNOWN[q['key']]) if q['key'] in KNOWN else None


def classify(d, l_q):
    """(group, why). The user's own state is read on the page (page_state), not here."""
    if not (d.get('ticket_info') or {}).get('is_free'): return 'never', 'not free: the radar never pays'
    if d.get('registration_availability') not in ('open', 'waitlist') and not (d.get('ticket_info') or {}).get('is_sold_out'):
        return 'never', f"registration {d.get('registration_availability')}"
    l_need = [q['label'] for q in l_q if q['required'] and not known(q)]
    return ('ask first', 'needs your answer: ' + '; '.join(l_need)) if l_need else ('auto', 'every required answer is known')


def draft(title, l_q):
    """Answers for every required question: known ones from the config, the others drafted by Claude from the user's facts ('?' = unknown)."""
    l_ans = [known(q) for q in l_q]
    l_todo = [i for i, q in enumerate(l_q) if q['required'] and l_ans[i] is None]
    if not l_todo: return l_ans, 0
    facts = Path.home() / 'opt/my-setup/context/snapshot/facts/robotics.md'
    prompt = f"""Draft answers to an event registration form, in the person's name, for the event "{title}".
Rules: facts only, from THE PERSON below; never invent a memory, a name, a number, a link or a plan. When the answer needs a fact
you do not have (a phone number, a person to recommend, a preference only they know), answer "?". A dropdown: exactly one of its
options. A multi-select: a list of options. Free text: one or two short plain sentences, first person, no buzzwords.

THE PERSON: {json.dumps({k: v for k, v in d_cfg['form'].items() if k != 'phone'}, ensure_ascii=False)}
{facts.read_text()[:5000] if facts.exists() else ''}

QUESTIONS: {json.dumps([{'n': i, 'question': l_q[i]['label'], 'type': l_q[i]['qt'], 'options': l_q[i]['options']} for i in l_todo], ensure_ascii=False)}

Answer ONLY a JSON array: [{{"n": int, "answer": "..." or ["..."]}}]"""
    l_out, cost = claude_json(prompt, d_src['models']['score'])
    for o in l_out:
        if o.get('n') in l_todo: l_ans[o['n']] = o['answer']
    return l_ans, cost


def page_state(ch):
    """The user's state on the event page (logged in): registered, pending, waitlist, or None."""
    s_lines = {x.strip().lower() for x in ch.page.inner_text('body').split('\n')}
    return next((k for k, rx in DONE_LINES.items() if any(re.fullmatch(rx, x) for x in s_lines)), None)


def open_event(ch, url):
    """Opens the event page (logged in); returns the user's state there."""
    ch.page.goto(f'https://luma.com/{slug_of(url)}', wait_until='domcontentloaded'); ch.page.wait_for_timeout(4000)   # networkidle: Luma never idles at times
    return page_state(ch)


def fill(ch, url, l_q, l_ans, submit):
    """Opens the form, fills it, and clicks the last button only if submit. Returns (state after, screenshot path)."""
    p = ch.page
    if (state := open_event(ch, url)): return state, ch.shot(f'already_{slug_of(url)}')
    btn = p.get_by_role('button', name=re.compile(r'^(Request to Join|Register|RSVP|One-Click RSVP|Join Waitlist|Get Ticket)$', re.I)).first
    btn.click(); p.wait_for_timeout(2000)
    form = p.locator('form:has(button[type=submit])').last
    for q, ans in zip(l_q, l_ans):
        if ans in (None, '', '?'): continue
        lab = form.locator('label', has_text=q['label'][:60]).first
        if q['qt'] == 'phone': form.locator('input[type=tel]').first.fill(str(ans)); continue
        if q['qt'] in ACCEPT:
            box = lab.locator('xpath=following::input[@type="checkbox"][1]')
            if not (box.count() and box.is_checked()): lab.click()
            continue
        multi = lab.locator('xpath=ancestor::*[@role="combobox"][1]')   # a multi-select: the label sits inside its combobox
        field = multi if multi.count() else form.locator(f'[id="{lab.get_attribute("for")}"]')
        if field.get_attribute('role') == 'combobox':   # Luma's dropdowns: open, click the option(s)
            field.click(); p.wait_for_timeout(500)    # a multi-select's list stays open over the page until Escape
            for opt in ans if isinstance(ans, list) else [ans]:
                p.locator('[role=option]:visible').filter(has_text=re.compile(rf'^\s*{re.escape(opt)}\s*$')).first.click(); p.wait_for_timeout(400)
            if multi.count(): p.keyboard.press('Escape'); p.wait_for_timeout(400)
        elif not field.input_value():                     # Luma pre-fills some answers from the profile (LinkedIn): kept
            field.fill(str(ans))
    shot = ch.shot(f'filled_{slug_of(url)}')
    if not submit: return 'filled', shot
    form.locator('button[type=submit]').last.click(); p.wait_for_timeout(5000)
    state = page_state(ch)
    log(f'register: {url}: after submit {state}')
    return state or 'unclear', ch.shot(f'submitted_{slug_of(url)}')
