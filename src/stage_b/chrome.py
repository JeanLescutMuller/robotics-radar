"""The radar's own headless Chrome (skill chrome; model: ~/dev/marketplace-seller/src/engine_chrome.py).

No window, ever. Its own data folder ~/opt/robotics-radar/chrome/ (logged in to Luma by luma.py, never the user's profiles), started
only through the Chrome kit's launcher (my-setup, ~/opt/my-setup/chrome/launch_headless.py): it records who opened it, when and why
(agent-chrome status), passes `--disable-blink-features=AutomationControlled` and a normal user agent so pages see a normal Chrome, and
quits Chrome at the end of every use, checked: no process left on the data folder; also on an error or a kill (SIGTERM). Never
kept for the next run (Busy keeps two runs apart). Attached with Playwright's connect_over_cdp. Mac only, like stage B.
Screenshots older than KEEP_SHOTS_DAYS are deleted at each start.

Use:    with Chrome() as ch: ch.page.goto(...); ch.shot('name')     (raises Busy when another run has it open)
"""
import contextlib, os, re, signal, subprocess, sys, time
from datetime import datetime
from playwright.sync_api import sync_playwright
from pathlib import Path
from common import STATE, log

sys.path.insert(0, str(Path.home() / 'opt/my-setup/chrome'))   # the Chrome kit (my-setup): standard library only
from launch_headless import headless

# one data folder, one Luma login, for the job and for runs by hand in ~/dev (AGENTS.md): another folder would log in again,
# and every login sends the user sign-in emails. Busy (below) keeps two runs apart.
PROFILE = Path.home() / 'opt/robotics-radar/chrome'
SHOTS = STATE / 'shots'
KEEP_SHOTS_DAYS = 30   # stage B's screenshots: looked at during the trust ramp (2 weeks, DESIGN.md §5), then of no use
PURPOSE = 'stage B: register the events the user accepted, on Luma'


class Busy(Exception):
    """The radar's Chrome is already open (another run)."""


class Chrome:
    def __enter__(self):
        PROFILE.mkdir(parents=True, exist_ok=True); SHOTS.mkdir(parents=True, exist_ok=True)
        for f in SHOTS.glob('*.png'):
            if f.stat().st_mtime < time.time() - KEEP_SHOTS_DAYS * 86400: f.unlink()
        lock = PROFILE / 'SingletonLock'   # Chrome's own lock while it runs: a link to "<host>-<pid>"
        if lock.is_symlink():
            try: os.kill(int(os.readlink(lock).rsplit('-', 1)[-1]), 0); raise Busy("the radar's Chrome is already open")
            except ProcessLookupError: pass   # a stale lock from a crash: Chrome clears it itself
        # a kill (job-runner's timeout, `kill <pid>`) becomes a normal exit, so __exit__ still quits Chrome
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        self.stack = contextlib.ExitStack()
        try: self._attach()
        except BaseException: self._quit(); raise   # __exit__ is not called when __enter__ fails: quit here
        return self

    def _attach(self):
        h = self.stack.enter_context(headless(PROFILE, PURPOSE))
        self.pw = self.stack.enter_context(sync_playwright())
        self.browser = self.pw.chromium.connect_over_cdp(f"http://127.0.0.1:{h['port']}")
        self.ctx = self.browser.contexts[0]
        self.page = next(pg for pg in self.ctx.pages   # the launcher's tab, by its CDP target id
                         if self.ctx.new_cdp_session(pg).send('Target.getTargetInfo')['targetInfo']['targetId'] == h['target_id'])
        self.page.set_default_timeout(20_000)

    def shot(self, name):
        # a screenshot file to look at, instead of a window
        path = SHOTS / f"{datetime.now():%Y-%m-%d_%H%M%S}_{re.sub(r'[^A-Za-z0-9_-]+', '_', name)[:60]}.png"
        self.page.screenshot(path=str(path), full_page=True)
        return path

    def _quit(self):
        try: self.stack.close()   # Playwright detached, then Chrome quit (its tabs closed, else SIGTERM: cookies and logins stay)
        finally:
            left = subprocess.run(['pgrep', '-f', f'user-data-dir={PROFILE}( |$)'], capture_output=True, text=True).stdout.split()
            log(f"chrome: closed{' (checked)' if not left else f', STILL RUNNING: {left}'}")

    def __exit__(self, *exc):
        self._quit()
