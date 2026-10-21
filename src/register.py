"""Step 5 of a run (phase 4, DESIGN.md §5): registration for free Luma events, score >= minimum_registration_score.

Groups, from Luma's own data (event's registration_questions), never by clicking:
  auto       every required question has a known answer (config form:, terms accepted) → register
  ask first  a required question needs the user's own words (text, dropdown, url…) → Claude drafts, the user approves
  never      paid, closed, full without waitlist, already registered or pending → nothing
Trust ramp: while registration.submit is false, nothing is clicked: a screenshot of the event page is saved instead.
"""
import json
from datetime import timedelta
from common import d_cfg, http_get, log

KNOWN = {'linkedin': 'linkedin', 'company': 'company', 'job-title': 'role', 'name': None, 'email': None}   # question type → form: key
ACCEPT = {'terms', 'agree-check'}   # agreements: accepted and recorded


def luma_data(e):
    slug = (e['reg_url'] or e['url'] or '').split('luma.com/')[-1].split('/')[0] if 'luma.com/' in (e['reg_url'] or e['url'] or '') else None
    return http_get(f'https://api.lu.ma/url?url={slug}', as_json=True)['data'] if slug else None


def classify(e, d):
    """Returns (group, why, l_answers): l_answers = [(question label, answer)] for auto."""
    if e['user_state'] in ('registered', 'pending', 'waitlist'): return 'never', f"already {e['user_state']}", []
    if not (d.get('ticket_info') or {}).get('is_free'): return 'never', 'not free', []
    if e['reg_state'] not in ('open', 'approval', 'waitlist'): return 'never', f"registration {e['reg_state']}", []
    l_ans, l_need = [], []
    for q in d.get('registration_questions') or []:
        qt, label = q.get('question_type'), q.get('label', '')
        if qt in KNOWN and KNOWN[qt]: l_ans.append((label, d_cfg['form'][KNOWN[qt]]))
        elif qt in ACCEPT: l_ans.append((label, 'accepted'))
        elif q.get('required'): l_need.append(f'{qt}: {label}')
    if l_need: return 'ask first', '; '.join(l_need), l_ans
    return 'auto', 'all required answers known', l_ans


def candidates(db, d_ev, today):
    """Upcoming free-looking Luma events worth registering for, with their group."""
    l_out = []
    for e in d_ev.values():
        if not e['start'] or e['start'][:10] < (today + timedelta(days=1)).isoformat(): continue   # not on the day itself
        if (e['score'] or 0) < d_cfg['minimum_registration_score'] or 'luma.com/' not in (e['reg_url'] or e['url'] or ''): continue
        try: d = luma_data(e)
        except Exception as ex: log(f"register: luma data {e['title']}: {ex}"); continue
        if not d: continue
        group, why, l_ans = classify(e, d)
        l_out.append(dict(event=e, group=group, why=why, answers=l_ans, url=f"https://luma.com/{d['event']['url']}"))
    return l_out
