"""The radar's own headless Chrome (skill chrome-headless; model: ~/dev/marketplace-seller/src/engine_chrome.py).

No window, ever. Its own data folder <root>/chrome/ (logged in to Luma by luma.py, never the user's profiles), attached
with Playwright's connect_over_cdp; `--disable-blink-features=AutomationControlled` and a normal user agent so pages see a
normal Chrome. Quit at the end of every use, and checked: no process left on the data folder.

Use:    with Chrome() as ch: ch.page.goto(...); ch.shot('name')     (raises Busy when another run has it open)
"""
import os, re, subprocess, time
from datetime import datetime
from playwright.sync_api import sync_playwright
from common import ROOT, STATE, log

PROFILE = ROOT / 'chrome'
SHOTS = STATE / 'shots'
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


class Busy(Exception):
    """The radar's Chrome is already open (another run)."""


class Chrome:
    def __enter__(self):
        PROFILE.mkdir(exist_ok=True); SHOTS.mkdir(parents=True, exist_ok=True)
        lock = PROFILE / 'SingletonLock'   # Chrome's own lock while it runs: a link to "<host>-<pid>"
        if lock.is_symlink():
            try: os.kill(int(os.readlink(lock).rsplit('-', 1)[-1]), 0); raise Busy("the radar's Chrome is already open")
            except ProcessLookupError: pass   # a stale lock from a crash: Chrome clears it itself
        port_file = PROFILE / 'DevToolsActivePort'
        port_file.unlink(missing_ok=True)
        major = re.search(r'(\d+)\.', subprocess.run([CHROME, '--version'], capture_output=True, text=True).stdout)[1]
        ua = f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36'
        self.proc = subprocess.Popen([CHROME, '--headless', f'--user-data-dir={PROFILE}', '--remote-debugging-port=0', '--no-first-run',
                                      '--no-default-browser-check', f'--user-agent={ua}', '--lang=en-US', '--window-size=1440,900',
                                      '--disable-blink-features=AutomationControlled', 'about:blank'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):   # Chrome writes its random local debugging port here once it listens
            if port_file.exists() and port_file.read_text().strip(): break
            time.sleep(0.25)
        else: self._quit(); raise RuntimeError('Chrome did not start')
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.connect_over_cdp(f'http://127.0.0.1:{port_file.read_text().split()[0]}')
        self.ctx = self.browser.contexts[0]
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self.page.set_default_timeout(20_000)
        return self

    def shot(self, name):
        # a screenshot file to look at, instead of a window
        path = SHOTS / f"{datetime.now():%Y-%m-%d_%H%M%S}_{re.sub(r'[^A-Za-z0-9_-]+', '_', name)[:60]}.png"
        self.page.screenshot(path=str(path), full_page=True)
        return path

    def _quit(self):
        self.proc.terminate()   # SIGTERM = a normal quit: cookies and logins stay
        try: self.proc.wait(30)
        except subprocess.TimeoutExpired: self.proc.kill()
        left = subprocess.run(['pgrep', '-f', f'user-data-dir={PROFILE}'], capture_output=True, text=True).stdout.split()
        log(f"chrome: closed{' (checked)' if not left else f', STILL RUNNING: {left}'}")

    def __exit__(self, *exc):
        try: self.browser.close(); self.pw.stop()
        except Exception: pass
        self._quit()
