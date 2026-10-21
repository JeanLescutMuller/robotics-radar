"""Helpers shared by stage A (src/stage_a/) and stage B (src/stage_b/): config, external reads and writes, matching, Claude calls."""
import hashlib, html, json, re, subprocess, unicodedata, urllib.error, urllib.request
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo
import yaml

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / 'state'
d_cfg = yaml.safe_load((Path.home() / '.config/robotics-radar/config.yaml').read_text())   # personal values: never in the repo
d_src = yaml.safe_load((ROOT / 'config/sources.yaml').read_text())                         # public: where events come from
TZ = ZoneInfo(d_cfg['timezone'])
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
MONTHS = {m: i + 1 for i, m in enumerate('jan feb mar apr may jun jul aug sep oct nov dec'.split())}
# words that say what to do, not which event: removed before comparing titles
STOP = set('''a an and the of for at in on to by with if or x vs register registration request admission check application
status join waitlist confirm attendance plan find decide whether attend visit follow up eligibility cost worthwhile
radar bobi robotics_radar event events session meetup buy ticket tickets apply summit conference
robotics robot zurich ai physical 2026 2027 seminar workshop talk night day prof dr
approved confirmed pending you re your is has been next week weeks starting tomorrow today reminder'''.split())
# last two lines: words in most titles, and in Luma's email subjects, that say nothing about which event


def log(*args): print(datetime.now().strftime('%H:%M:%S'), *args, flush=True)


def gws(*args):
    # gws prints a keyring line on stderr: keep stdout only
    out = subprocess.run(['gws', *args], capture_output=True, text=True, timeout=120)
    if out.returncode: raise RuntimeError(f'gws {args[:3]} failed: {out.stderr[-300:]}')
    return json.loads(out.stdout)


def todoist_get(path):
    # token: task-management's file (skill task-management, references/todoist_api.md); read, never printed
    token = re.search(r'TODOIST_API_TOKEN="?([^"\n]+)', (Path.home() / '.config/task-management/todoist_token.env').read_text())[1]
    l_res, cursor = [], None
    while True:
        url = f'https://api.todoist.com/api/v1/{path}' + (f'&cursor={cursor}' if cursor else '')
        d_page = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'}), timeout=30))
        l_res += d_page['results']; cursor = d_page.get('next_cursor')
        if not cursor: return l_res



def todoist(method, path, body=None):
    """One Todoist API v1 write (or read): (HTTP status, parsed answer or None). Token as in todoist_get."""
    token = re.search(r'TODOIST_API_TOKEN="?([^"\n]+)', (Path.home() / '.config/task-management/todoist_token.env').read_text())[1]
    req = urllib.request.Request(f'https://api.todoist.com/api/v1/{path}', method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def http_get(url, timeout=25, as_json=False):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en,de;q=0.8'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(3_000_000).decode('utf-8', 'ignore')
    return json.loads(body) if as_json else body


def html_to_text(page):
    # visible text only, links kept as "text <url>" so Claude can return them
    page = re.sub(r'(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>', ' ', page)
    page = re.sub(r'(?is)<a [^>]*href="([^"#]+)"[^>]*>(.*?)</a>', r'\2 <\1>', page)
    page = re.sub(r'(?i)<(br|/p|/div|/li|/h\d|/tr)[^>]*>', '\n', page)
    page = html.unescape(re.sub(r'<[^>]+>', ' ', page))
    return re.sub(r'\n\s*\n+', '\n', re.sub(r'[ \t]+', ' ', page)).strip()


def sha(text): return hashlib.sha256(text.encode()).hexdigest()[:16]


def canon_url(url):
    # same event, different spellings: lu.ma = luma.com, no query, no trailing slash, no www
    url = re.sub(r'[)\]>.,;]+$', '', url.strip()).split('?')[0].split('#')[0].rstrip('/').lower()
    url = re.sub(r'^https?://(www\.)?', '', url)
    return url.replace('lu.ma/', 'luma.com/')


def urls_in(text):
    return {canon_url(u) for u in re.findall(r'https?://[^\s)\]<>"]+', text or '')
            if not re.search(r'mail\.google|google\.com/calendar|todoist\.com', u)}


def norm_tokens(title):
    title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode().lower()
    title = re.sub(r'\[robotics radar\]|^robotics - |^professional/robotics|\(time not confirmed\)', ' ', title)
    return [w for w in re.findall(r'[a-z0-9]+', title) if w not in STOP and (len(w) > 1 or w.isdigit())]


def similarity(t1, t2):
    l1, l2 = norm_tokens(t1), norm_tokens(t2)
    if not l1 or not l2: return 0.0
    # share of the shorter title's words found in the other; spelling only for one-word titles
    # (on longer ones it matched "cleaning" with "learning", and "roundtable" matched every roundtable)
    if min(len(set(l1)), len(set(l2))) > 1: return len(set(l1) & set(l2)) / min(len(set(l1)), len(set(l2)))
    return SequenceMatcher(None, ' '.join(l1), ' '.join(l2)).ratio()


def same_event(a, b, s_listing_urls=frozenset()):
    """a, b: dicts with title, start (date or None), urls (set). A page linked from several events is a listing, not one event's page."""
    close = not (a['start'] and b['start']) or abs((a['start'] - b['start']).days) <= 1
    shared = (a['urls'] & b['urls']) - s_listing_urls
    # one event's own page and the same day: the same event, however the titles differ (2026-10-21: ChatGPT's task "Voxel51 Dec 10
    # Physical AI/CV meetup" vs Voxel51's "AI, ML and Computer Vision Meetup - December 10, 2026" made a duplicate calendar entry)
    if shared and a['start'] and a['start'] == b['start']: return True
    if shared and close and similarity(a['title'], b['title']) >= 0.3: return True
    if a['start'] and b['start']:
        # same day and two shared words is enough: a talk's title vs a task named after its speaker ("UZH aerial manipulation colloquium")
        if a['start'] == b['start'] and len(set(norm_tokens(a['title'])) & set(norm_tokens(b['title']))) >= 2 and similarity(a['title'], b['title']) >= 0.4: return True
        return close and similarity(a['title'], b['title']) >= 0.6
    return similarity(a['title'], b['title']) >= 0.8


def parse_event_dates(desc):
    # the "Event:" line of an event task: ISO dates, or "Thu 22 Oct 2026", "28–29 Oct 2026", "Friday 23 October 2026"
    m = re.search(r'Event:\s*(.*)', desc or '')
    if not m: return None, None
    line = m.group(1)
    l_iso = re.findall(r'(\d{4}-\d{2}-\d{2})', line)
    if l_iso: return date.fromisoformat(l_iso[0]), date.fromisoformat(l_iso[-1])
    m = re.search(r'(\d{1,2})(?:\s*[–-]\s*(\d{1,2}))?\s+([A-Za-z]{3})[a-z]*\.?,?\s+(\d{4})', line)
    if not m or m[3].lower() not in MONTHS: return None, None
    start = date(int(m[4]), MONTHS[m[3].lower()], int(m[1]))
    return start, start.replace(day=int(m[2])) if m[2] else start


def claude_json(prompt, model, tools='', max_turns=None, timeout=900):
    """One `claude -p` call that must answer with JSON. Returns (parsed answer, cost in USD). No project context, no tools unless given."""
    cmd = ['claude', '-p', '--model', model, '--setting-sources', '', '--output-format', 'json', '--tools', tools]
    if tools: cmd += ['--allowedTools', tools]
    if max_turns: cmd += ['--max-turns', str(max_turns)]
    out = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=STATE)
    d_out = json.loads(out.stdout or '{}')
    if out.returncode or d_out.get('is_error'): raise RuntimeError(f'claude failed: {(d_out.get("result") or out.stderr)[-300:]}')
    text = d_out['result']
    m = re.search(r'```(?:json)?\s*(.*?)```', text, re.S)                 # the answer may be fenced
    text = m[1] if m else text[min([i for i in (text.find('['), text.find('{')) if i >= 0], default=0):]
    return json.loads(text), d_out.get('total_cost_usd', 0)
