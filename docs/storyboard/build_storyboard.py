"""Builds docs/storyboard/storyboard.html: one self-contained page (the screenshots are embedded) that sequences the captured frames as a
storyboard, with the shot, what is on screen and a line of narration for each. Run: python docs/storyboard/build_storyboard.py

The frames in images/ are real screenshots of the app running on sample data (live news events, live hazard feeds, the bundled datasets),
captured in a scratch copy with the premium features switched on for the capture. Edit FRAMES to change the order or the words."""
import base64
import html
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (file, act, title, on screen, narration, seconds, phone)
FRAMES = [
    ('01-globe.jpg', 'See what is happening', 'The live globe',
     'Events from the news feed as pins on a globe, with the ranked list beside it. Filters for time, scope and severity sit above the list.',
     'Every event the news is reporting, placed on the map and ranked by how serious it is.', 6, False),
    ('02-event-opens.jpg', 'See what is happening', 'Open an event',
     'Clicking an event opens its analysis: severity, scope, country and type at a glance, with a link to the country.',
     'Pick any event and its analysis opens beside the map.', 5, False),
    ('03-situation.jpg', 'See what is happening', 'One development, many stories',
     'Twelve stories from twelve outlets about the same development are grouped into one. The most reported headline leads, the other angles are listed, and casualty figures are quoted as whole sentences with their sources.',
     'Duplicate coverage is folded into one situation, so you read the development once, with every source named.', 8, False),
    ('04-country-economy.jpg', 'Understand the place', 'A country, in numbers',
     'The country analysis has six tabs. Economy shows each figure with its year, its rank among 214 countries and its long-run trend.',
     'Click a country for the numbers behind it: where it ranks, and how it has changed since 1991.', 7, False),
    ('05-weather-layers.jpg', 'Weather and time', 'Weather layers',
     'Weather mode with the Layers menu open: live radar and clouds, and forecast maps for temperature, pressure, rain and wind, each labelled as a model, not observed.',
     'Switch to Weather for live radar and satellite clouds, and forecast layers clearly marked as forecasts.', 6, False),
    ('06-weather-hazard.jpg', 'Weather and time', 'A storm, with its forecast',
     'A cyclone selected from the live hazard list: its alert level, intensity, dates and track, with the temperature forecast drawn underneath and its legend.',
     'Hazards come with their alert level and track, on top of the forecast you chose.', 6, False),
    ('07-timezone.jpg', 'Weather and time', 'Time zones, honestly',
     'Time Zone mode: a zone clicked on the globe shows its clock changes, the sun at that point and the rules; a city is pinned to the world clock.',
     'Click anywhere to see the local time, when the clocks last and next change, and where the sun is.', 6, False),
    ('09-cascade-hormuz-map.jpg', 'What it could mean', 'Cascade: who is exposed',
     'A closure of the Strait of Hormuz, run from the Cascade button in Events mode: countries coloured by exposure (red High, orange Moderate, yellow Low), with a key and a way back to the result.',
     'Ask what happens if a route closes, and see who is exposed, coloured on the map.', 8, False),
    ('08-cascade-evidence.jpg', 'What it could mean', 'Every colour shows its evidence',
     'The result lists each country with its mechanism and how soon it bites. Opening Why shows the figures and their source, for example how much of its gas a country imports and how much comes from the trigger country.',
     'Nothing is a guess: each country opens to the figures and sources behind its colour.', 8, False),
    ('10-watchlist-alerts.jpg', 'Stay informed', 'Choose your own alerts',
     'A watched place with its alert choices: which hazards, a minimum level, situations or serious events inside the radius, weather limits and clock changes.',
     'Watch the places you care about and choose exactly which alerts each one raises.', 7, False),
    ('11-dashboard-settings.jpg', 'Stay informed', 'Settings in one place',
     'The Dashboard holds Saved, Sources, Watchlist, Alerts and Settings: units, clocks, map style, alert emails and sign out. Choices are remembered on the device.',
     'Display choices, alert emails and sign out live together in the dashboard.', 5, False),
    ('14-mobile-menu.jpg', 'On the go', 'On a phone: the menu',
     'The three modes sit in a menu; Draw, Layers and the Dashboard stay in the top bar.',
     'On a phone the modes fold into a menu, and the tools stay one tap away.', 4, True),
    ('13-mobile-map.jpg', 'On the go', 'On a phone: the map',
     'The same Cascade result on a phone: the key moves to the top so it never covers the List and Details buttons.',
     'The map and its key are laid out for a thumb.', 5, True),
    ('12-mobile-cascade.jpg', 'On the go', 'On a phone: Cascade',
     'The Cascade panel full width: pick what happens and where, run it, save it or ask for a written summary, all from a phone.',
     'And the full Cascade workspace fits in your hand.', 5, True),
]

CSS = """
:root { --bg:#0b0e14; --panel:#131824; --line:#263042; --text:#e8ecf4; --muted:#9aa6ba; --accent:#5aa0ff; }
@media (prefers-color-scheme: light) { :root { --bg:#f5f7fb; --panel:#ffffff; --line:#d5dbe6; --text:#151a24; --muted:#5a6578; --accent:#1d6fe0; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:16px/1.5 system-ui, sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { margin: 0 0 4px; font-size: 28px; }
.lede { margin: 0 0 8px; color: var(--muted); }
.total { margin: 0 0 32px; color: var(--muted); font-size: 14px; }
h2.act { margin: 40px 0 12px; padding-top: 8px; border-top: 1px solid var(--line); font-size: 14px; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); }
.shot { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 20px; margin: 0 0 24px; padding: 16px; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; }
.shot.phone { grid-template-columns: minmax(0, 260px) minmax(0, 1fr); }
.shot img { width: 100%; height: auto; display: block; border: 1px solid var(--line); border-radius: 6px; }
.num { font-size: 12px; color: var(--muted); }
.shot h3 { margin: 2px 0 8px; font-size: 20px; }
.label { margin: 12px 0 2px; font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.shot p { margin: 0; }
.say { font-style: italic; }
@media (max-width: 760px) { .shot, .shot.phone { grid-template-columns: 1fr; } .shot.phone img { max-width: 260px; } }
"""


def uri(name):
    return 'data:image/jpeg;base64,' + base64.b64encode((HERE / 'images' / name).read_bytes()).decode('ascii')


def main():
    total = sum(f[5] for f in FRAMES)
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
             '<title>GeoIntel Storyboard</title><style>', CSS, '</style></head><body><main>',
             '<h1>GeoIntel: storyboard</h1>',
             '<p class="lede">The app in fourteen frames, from the live globe to a phone. Each frame is a real screenshot of the running app on sample data.</p>',
             f'<p class="total">{len(FRAMES)} frames, about {total} seconds at the timings given.</p>']
    act = None
    for i, (file, act_name, title, on_screen, say, seconds, phone) in enumerate(FRAMES, 1):
        if act_name != act:
            parts.append(f'<h2 class="act">{html.escape(act_name)}</h2>')
            act = act_name
        parts.append(
            f'<section class="shot{" phone" if phone else ""}"><img src="{uri(file)}" alt="{html.escape(title)}: {html.escape(on_screen)}">'
            f'<div><div class="num">Frame {i} of {len(FRAMES)} &middot; {seconds} s</div><h3>{html.escape(title)}</h3>'
            f'<div class="label">On screen</div><p>{html.escape(on_screen)}</p>'
            f'<div class="label">Narration</div><p class="say">&ldquo;{html.escape(say)}&rdquo;</p></div></section>')
    parts.append('</main></body></html>')
    out = HERE / 'storyboard.html'
    out.write_text(''.join(parts), encoding='utf-8')
    print(f'wrote {out} ({out.stat().st_size // 1024} KB), {len(FRAMES)} frames, {total} s')


if __name__ == '__main__':
    main()
