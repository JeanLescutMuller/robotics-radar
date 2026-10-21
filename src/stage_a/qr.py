"""The shared calendar's QR code: a PNG people scan to see the calendar on their phone, and subscribe from there ("+ Google Calendar").

Run by hand, once (or after the calendar changes): .venv/bin/python src/stage_a/qr.py [output.png]
Reads:  calendar.target_id in ~/.config/robotics-radar/config.yaml.
Writes: the PNG (default: the Drive folder Professional/Robotics/, skill data-organization) and prints the links.
"""
import sys, urllib.parse
from datetime import date
from pathlib import Path
import segno
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import d_cfg

cal = d_cfg['calendar']['target_id']
view = f"https://calendar.google.com/calendar/embed?src={urllib.parse.quote(cal)}&ctz=Europe%2FZurich&mode=AGENDA"   # agenda: readable on a phone
ics = f"https://calendar.google.com/calendar/ical/{urllib.parse.quote(cal)}/public/basic.ics"                       # Apple Calendar, Outlook
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / f'gdrive/Professional/Robotics/{date.today():%Y_%m_%d}_robotics_events_calendar_QR.png'
segno.make(view, error='m').save(out, scale=16, border=4)
print(f'QR code: {out}\nit opens: {view}\nsubscribe (Google): https://calendar.google.com/calendar/u/0?cid={cal}\nsubscribe (Apple, Outlook): {ics.replace("https://", "webcal://")}')
