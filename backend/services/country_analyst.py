"""
The analyst read: a short paragraph at the foot of a country tab saying what stands out in that tab's own figures. The model is
given a plain fact sheet built from the tab's data (values with their years, ranks and trends, and the Factbook's key texts)
and is told to use nothing else, to add no numbers, and to name important gaps. It runs only when a viewer asks for it, is
remembered for a week per country, tab and version of the data, and reports "unavailable" without a model rather than inventing
one. Premium, like the tabs themselves.
"""
import hashlib
import logging

from cache import cache_get, cache_set
from services.ai_client import AI_MODEL, anthropic_client

logger = logging.getLogger(__name__)

MAX_FACTS = 7000
CACHE_SECONDS = 7 * 24 * 3600


class AnalystUnavailable(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _num(value):
    if isinstance(value, float) and abs(value) >= 1000:
        return f'{value:,.0f}'
    if isinstance(value, float):
        return f'{value:.3g}'
    return f'{value:,}' if isinstance(value, int) else str(value)


def _trend(series):
    if not series or len(series) < 2:
        return ''
    (y0, v0), (_, v1) = series[0], series[-1]
    if v0 and v0 > 0 and all(p[1] > 0 for p in series):
        return f', {"up" if v1 > v0 else "down"} {abs(v1 - v0) / v0 * 100:.0f}% since {y0}'
    return f', was {_num(v0)} in {y0}'


def _stat_line(s):
    rank = f', rank {s["rank"]} of {s["of"]} (1 is highest)' if s.get('rank') else ''
    return f'{s["label"]}: {_num(s["value"])} {s.get("unit") or ""} ({s["year"]}){rank}{_trend(s.get("series"))}'.replace('  ', ' ')


def _lines(tab, d):
    """The fact sheet for one tab: one fact per line, only what the tab's data contains."""
    out = []
    add = out.append

    def stats(items):
        for s in items or []:
            add(_stat_line(s))

    if tab == 'government':
        g = d.get('government') or {}
        add(f'Government type: {g.get("type")}') if g.get('type') else None
        for key, label in (('chief_of_state', 'Head of state'), ('head_of_government', 'Head of government')):
            if (g.get(key) or {}).get('text'):
                add(f'{label}: {g[key]["text"]}')
        for key, label in (('last_election', 'Last executive election'), ('next_election', 'Next executive election')):
            if g.get(key):
                add(f'{label}: {g[key]}')
        dem = d.get('democracy')
        if dem:
            regime = f', classed as {dem["regime"]["label"]} since {dem["regime"]["since"]}' if dem.get('regime') else ''
            add(f'Electoral democracy index (0 to 1): {dem["value"]} ({dem["year"]}), rank {dem["rank"]} of {dem["of"]}{regime}{_trend(dem["series"])}')
        for c in (g.get('legislature') or {}).get('chambers', []):
            add(f'Legislature ({c.get("label")}): {c.get("name")}; seats {c.get("seats")}; women {c.get("women_percent")}; next election {c.get("next_election")}')
        if (g.get('judiciary') or {}).get('highest_courts'):
            add(f'Highest courts: {g["judiciary"]["highest_courts"]}')
        add(f'Memberships listed: {len(d.get("memberships") or [])}, including ' + ', '.join(m['abbr'] for m in (d.get('memberships') or []) if m['kind'] == 'security')[:200]) if d.get('memberships') else None
    elif tab == 'people':
        stats(d.get('stats'))
        if d.get('hdi'):
            h = d['hdi']
            add(f'Human Development Index: {h["value"]} ({h["year"]}), {h["tier"]}, rank {h["rank"]} of {h["of"]}{_trend(h["series"])}')
        p = d.get('people') or {}
        for key, label in (('religions', 'Religions'), ('ethnic_groups', 'Ethnic groups'), ('language_shares', 'Languages')):
            if p.get(key):
                add(f'{label}: ' + ', '.join(f'{i["name"]} {i["percent"]}%' for i in p[key]['items'][:5]))
        for band in p.get('age_structure') or []:
            add(f'Age {band["band"]}: {band["percent"]}%')
        if p.get('median_age'):
            add(f'Median age: {p["median_age"]}')
    elif tab == 'migration':
        for key, label in (('immigrants', 'Immigrants'), ('emigrants', 'Emigrants (citizens abroad)')):
            f = d.get(key)
            if f:
                add(f'{label}: {_num(f["stock"])} in {f["year"]}, {f.get("share_of_population")}% of the population{_trend(f["series"])}')
                rows = f.get('origins') or f.get('destinations') or []
                add(f'{label} largest partners: ' + ', '.join(f'{r["country_code"]} {_num(r["count"])}' for r in rows[:5]))
        r = d.get('refugees') or {}
        for key, label in (('hosted', 'Refugee and asylum data, hosted here'), ('from_here', 'Refugee and displacement data, people from here')):
            if r.get(key):
                add(f'{label}, {r[key]["latest"]["year"]}: ' + ', '.join(f'{k} {_num(v)}' for k, v in r[key]['latest'].items() if k != 'year'))
        stats(d.get('stats'))
    elif tab == 'economy':
        stats(d.get('stats'))
        stats(d.get('sectors'))
        e = d.get('energy')
        if e:
            add(f'Electricity mix ({e["year"]}): ' + ', '.join(f'{m["name"]} {m["percent"]:.0f}%' for m in e['mix'][:4]) + f'; low-carbon share {e.get("low_carbon_share")}%')
        eco = d.get('economy') or {}
        for key, label in (('exports', 'Main exports'), ('imports', 'Main imports')):
            if eco.get(key):
                add(f'{label}: ' + ', '.join(eco[key]['items'][:5]))
        for m in ((d.get('minerals') or {}).get('items') or [])[:6]:
            if m.get('rank'):
                add(f'Mineral {m["commodity"]}: rank {m["rank"]} of {m["producers"]} producers, {m.get("world_share")}% of world output' + (' (critical mineral)' if m['critical'] else ''))
    elif tab == 'security':
        a = d.get('advisory')
        if a:
            add('UK travel advice: ' + ('; '.join(x['label'] for x in a['alerts']) or 'no warnings in force'))
        c = d.get('conflicts')
        if c:
            add(f'Violent events reported in the news, last {c["days"]} days: {c["total"]} ({c["last_7_days"]} in the last 7 days); weekly counts, oldest first: ' + ', '.join(str(w[1]) for w in c.get('weekly', [])))
            add('Busiest places: ' + ', '.join(f'{h["name"] or "unnamed area"} ({h["count"]})' for h in c.get('hotspots', [])))
        stats(d.get('stats'))
        series = (d.get('displacement') or {}).get('series') or []
        if series:
            add(f'Displacement ({series[-1]["year"]}): ' + ', '.join(f'{k} {_num(v)}' for k, v in series[-1].items() if k in ('refugees', 'idps', 'asylum_seekers')))
        s = d.get('security') or {}
        if s.get('terrorist_groups'):
            add(f'Terrorist groups listed: {s["terrorist_groups"][:300]}')
    elif tab == 'geography':
        stats(d.get('stats'))
        g = d.get('geography') or {}
        for key, label in (('climate', 'Climate'), ('terrain', 'Terrain'), ('natural_hazards', 'Natural hazards'), ('environmental_issues', 'Environmental issues')):
            if g.get(key):
                add(f'{label}: {g[key][:300]}')
        if (g.get('borders') or {}).get('countries'):
            add('Land borders: ' + ', '.join(f'{b["name"]} {_num(b["km"])} km' for b in g['borders']['countries'][:6]))
        if d.get('hazards') is not None:
            hazards = d['hazards'].get('items') or []
            add('Hazards active now: ' + ('; '.join(f'{h["hazard"]} {h.get("alert_level") or ""}' for h in hazards) or 'none'))
    return [line for line in out if line]


PROMPT = """You are writing a short analyst read for the %(tab)s tab of an intelligence briefing on %(country)s.
Use ONLY the facts below. Write 3 to 5 plain sentences: what stands out, how it compares with other countries (use the ranks given),
what has changed (use the trends given), and name one important thing the figures do not tell us or that is missing.
Do not state any number, name or date that is not in the facts. Quote a figure with its year when you use it. No markup, no list.

FACTS:
%(facts)s"""


def read(cc, country_name, tab, data):
    """{'text', 'model'} for the tab. Raises AnalystUnavailable when there is no model or nothing to read."""
    lines = _lines(tab, data or {})
    if not lines:
        raise AnalystUnavailable('no_data')
    facts = '\n'.join(lines)[:MAX_FACTS]
    if not (anthropic_client and anthropic_client.api_key):
        raise AnalystUnavailable('no_model')
    key = f'country_read:{cc}:{tab}:{hashlib.sha1(facts.encode("utf-8")).hexdigest()[:12]}'
    cached = cache_get(key)
    if cached:
        return cached
    try:
        message = anthropic_client.messages.create(
            model=AI_MODEL, max_tokens=500,
            messages=[{'role': 'user', 'content': PROMPT % {'tab': tab, 'country': country_name or cc, 'facts': facts}}])
        text = message.content[0].text.strip()
    except Exception as e:
        logger.info('[CountryAnalyst] %s %s failed: %s', cc, tab, e)
        raise AnalystUnavailable('model_error')
    if not text:
        raise AnalystUnavailable('empty')
    result = {'text': text, 'model': AI_MODEL}
    cache_set(key, result, ttl=CACHE_SECONDS)
    return result
