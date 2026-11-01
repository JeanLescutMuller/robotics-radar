#!/usr/bin/env python3
"""The radar's Chrome through the Chrome kit's launcher (src/stage_b/chrome.py): one real headless start, recorded, closed and
checked. No login, no Luma: a temporary data folder, never ~/opt/robotics-radar/chrome/; a temporary kit record (CHROME_STATE),
never ~/opt/my-setup/state/chrome/; a temporary shots folder.

Reads/writes: temporary folders only (deleted at the end); reads ~/.config/robotics-radar/config.yaml (through common.py)
Run:    .venv/bin/python test/chrome_test.py      (~5 s, no AI call)
Pass:   the tab is recorded open with its purpose while in use, closed after; no Chrome process left on the data folder;
        the user agent is not "HeadlessChrome"; a screenshot is written
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix='radar-chrome-test-')).resolve()
os.environ['CHROME_STATE'] = str(tmp / 'state')   # before the kit is imported: it reads it once
# A test against a scratch record runs as a script run by hand, not as the Claude session that started it: the
# session's authorization (agent-chrome authorize-tab --visibility invisible) lives in the real record (2 Nov 2026).
os.environ.pop('CLAUDE_CODE_SESSION_ID', None)
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / 'src/stage_b'), str(ROOT / 'src')]
import chrome          # noqa: E402
import chrome_kit      # noqa: E402 (on sys.path through chrome.py)

assert chrome_kit.STATE == tmp / 'state', chrome_kit.STATE
chrome.PROFILE, chrome.SHOTS = tmp / 'chrome', tmp / 'shots'


def left(d): return subprocess.run(['pgrep', '-f', f'user-data-dir={d}( |$)'], capture_output=True, text=True).stdout.split()


l_fail = []
with chrome.Chrome() as ch:
    ch.page.goto('data:text/html,<p>hello</p>')
    l_mine = [e for e in chrome_kit.read_open().values() if e['profile'] == f"headless:{tmp / 'chrome'}"]
    if not (len(l_mine) == 1 and l_mine[0]['purpose'] == chrome.PURPOSE): l_fail.append(f'not recorded open: {chrome_kit.read_open()}')
    if 'Headless' in ch.page.evaluate('navigator.userAgent'): l_fail.append('the user agent says headless')
    if not ch.shot('test').exists(): l_fail.append('no screenshot')
if left(tmp / 'chrome'): l_fail.append(f"Chrome left running: {left(tmp / 'chrome')}")
if chrome_kit.read_open(): l_fail.append(f'still recorded open: {chrome_kit.read_open()}')
l_ev = [json.loads(x)['event'] for f in (tmp / 'state/history').glob('*.jsonl') for x in f.read_text().splitlines()]
if l_ev != ['open', 'close']: l_fail.append(f'history: {l_ev}')

subprocess.run(['rm', '-rf', str(tmp)], check=True)   # the test's own temporary folder (mkdtemp above)
print('FAIL\n' + '\n'.join(l_fail) if l_fail else 'PASS: recorded, closed, checked; no Chrome left')
sys.exit(1 if l_fail else 0)
