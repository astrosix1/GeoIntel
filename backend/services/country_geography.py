"""
The Geography tab (the premium part): the Factbook's geography and environment facts (location, borders with lengths, climate,
terrain, elevation, land use, hazards, water, emissions), land and environment figures from the World Bank with rank and trend,
the hazards active in the country right now (our own GDACS feed), and a short Wikipedia introduction with attribution.
Every group is optional.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from data_sources import wikipedia
from data_sources.factbook import FactbookConnector
from services import country_indicators as wb

LAND_STATS = [
    ('AG.LND.TOTL.K2', 'Land area', 'sq km', 0),
    ('EN.POP.DNST', 'Population density', 'people per sq km', 0),
    ('AG.LND.FRST.ZS', 'Forest cover', '% of land', 1),
    ('AG.LND.ARBL.ZS', 'Arable land', '% of land', 1),
    ('ER.H2O.INTR.PC', 'Renewable fresh water', 'cubic metres per person', 0),
    ('EN.ATM.PM25.MC.M3', 'Air pollution (PM2.5)', 'micrograms per cubic metre', 1),
    ('EN.GHG.CO2.PC.CE.AR5', 'Carbon dioxide emissions', 'tonnes per person', 1),
    ('EG.FEC.RNEW.ZS', 'Renewable energy', '% of final energy use', 1),
]
WARM_INDICATORS = [spec[0] for spec in LAND_STATS]

_NAMES = None


def _country_names(iso2):
    global _NAMES
    if _NAMES is None:
        _NAMES = json.loads((Path(__file__).resolve().parent.parent / 'data_sources' / 'country_names.json').read_text(encoding='utf-8'))
    return {n.lower() for n in _NAMES.get(iso2, [])}


def active_hazards(cc):
    """Hazards affecting the country right now, from the GDACS feed this app already reads (tropical cyclones, floods, wildfires,
    droughts): [{'name', 'hazard', 'alert_level', 'description', 'report_url', 'from_date'}], most serious alert first."""
    from services.weather import get_active_storms
    names = _country_names(cc)
    if not names:
        return None
    try:
        feed = get_active_storms() or {}
    except Exception:
        return None
    rank = {'Red': 0, 'Orange': 1, 'Green': 2}
    hits = []
    for storm in feed.get('storms', []):
        affected = {c.lower() for c in (storm.get('affected_countries') or [])} | {(storm.get('country') or '').lower()}
        if affected & names:
            hits.append({'name': storm.get('name'), 'hazard': storm.get('hazard'), 'alert_level': storm.get('alert_level'),
                         'description': storm.get('description'), 'report_url': storm.get('report_url'), 'from_date': storm.get('from_date')})
    hits.sort(key=lambda h: rank.get(h['alert_level'], 3))
    return {'items': hits, 'source': feed.get('source') or 'GDACS'}


def build_tab(cc):
    """Everything for the premium part of the Geography tab, or None when no source has anything."""
    out = {'country_code': cc, 'tab': 'geography', 'sources': []}
    with ThreadPoolExecutor(max_workers=3) as pool:
        stats_f = pool.submit(wb.stats, cc, LAND_STATS)
        intro_f = pool.submit(wikipedia.geography_intro, cc)
        hazards_f = pool.submit(active_hazards, cc)
        factbook = FactbookConnector.fetch_profile(cc)
        stats, intro, hazards = stats_f.result(), intro_f.result(), hazards_f.result()
    if factbook and factbook.get('geography'):
        out['geography'] = factbook['geography']
        out['sources'].append('CIA World Factbook')
    if stats:
        out['stats'] = stats
        out['sources'].append(wb.SOURCE)
    if hazards is not None:
        out['hazards'] = hazards
        out['sources'].append('GDACS (live hazards)')
    if intro:
        out['intro'] = intro
        out['sources'].append('Wikipedia (' + intro['license'] + ')')
    return out if (factbook or stats or intro) else None
