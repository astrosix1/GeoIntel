"""
The country graph the cascade simulator walks. Built from the CIA World Factbook profiles the app already fetches
(data_sources/factbook.py): for each country, who it exports to and imports from (top partners with their share), what it mainly
exports, and how much gas and oil it produces and consumes. Nothing here is invented: a country the Factbook says nothing about
simply has no edges, and a partner whose name cannot be matched to a country is counted and reported, never guessed.

get_graph() builds it once a day (cached); build_graph() is the pure part, so it can be tested with small fixture profiles.
"""
import json
import logging
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from cache import cache_get, cache_set
from data_sources.factbook import FactbookConnector, _codes

logger = logging.getLogger(__name__)

GRAPH_KEY = 'cascade:graph:v1'
GRAPH_TTL = 24 * 3600
FETCH_WORKERS = 12
SOURCE = 'CIA World Factbook'

# Factbook short names for partners that are not the names in data_sources/country_names.json.
ALIASES = {
    'usa': 'US', 'uae': 'AE', 'korea south': 'KR', 'korea north': 'KP', 'burma': 'MM', 'cote divoire': 'CI',
    'congo democratic republic of the': 'CD', 'congo republic of the': 'CG', 'gambia the': 'GM', 'bahamas the': 'BS',
    'macau': 'MO', 'hong kong': 'HK', 'taiwan': 'TW', 'turkey turkiye': 'TR', 'turkiye': 'TR', 'czechia': 'CZ',
    'eswatini': 'SZ', 'cabo verde': 'CV', 'micronesia federated states of': 'FM', 'holy see vatican city': 'VA',
    'timor leste': 'TL', 'russia': 'RU', 'united kingdom': 'GB', 'uk': 'GB', 'vietnam': 'VN', 'laos': 'LA',
    'syria': 'SY', 'iran': 'IR', 'bolivia': 'BO', 'venezuela': 'VE', 'tanzania': 'TZ', 'moldova': 'MD',
    'bosnia herzegovina': 'BA', 'drc': 'CD', 'nz': 'NZ', 's korea': 'KR', 'st vincent the grenadines': 'VC',
}
# Leftovers of names the Factbook writes with a comma ("Congo, Republic of the", "Gambia, The"), which the share reader splits.
_FRAGMENTS = {'the', 'republic of the'}


def _norm(name):
    text = unicodedata.normalize('NFKD', (name or '').lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', text).split())


_NAME_INDEX = None
_DISPLAY = None


def _names():
    global _NAME_INDEX, _DISPLAY
    if _NAME_INDEX is None:
        raw = json.loads((Path(__file__).resolve().parent.parent / 'data_sources' / 'country_names.json').read_text(encoding='utf-8'))
        _NAME_INDEX = {_norm(n): iso for iso, names in raw.items() for n in names}
        _NAME_INDEX.update(ALIASES)
        # The shortest name of four letters or more reads best ("North Korea", "United Kingdom", not "UK" or the formal name).
        _DISPLAY = {iso: min((n for n in names if len(n) >= 4), key=len, default=names[0]) for iso, names in raw.items() if names}
    return _NAME_INDEX, _DISPLAY


def country_name(iso):
    return _names()[1].get(iso, iso)


def partner_iso(name):
    """The ISO-2 code for a Factbook partner name, or None."""
    return _names()[0].get(_norm(name))


def _partners(block, unmapped):
    """[{'iso', 'name', 'percent', 'under'}] for a Factbook partner list; names that match no country go to `unmapped`."""
    out = []
    for item in (block or {}).get('items') or []:
        iso = partner_iso(item.get('name'))
        if iso is None and _norm(item.get('name')) in _FRAGMENTS:
            continue
        if iso is None:
            unmapped.add(item.get('name'))
            continue
        out.append({'iso': iso, 'name': country_name(iso), 'percent': float(item.get('percent') or 0), 'under': bool(item.get('under'))})
    return out


def build_graph(profiles, built_at=None, allowed=None, population=None):
    """The graph from {iso2: Factbook profile or None}. Pure. With `allowed`, only those countries become nodes (the Factbook also
    describes territories and uninhabited islands, which would only add noise); trade partners may still be anyone."""
    unmapped = set()
    countries = {}
    for iso, profile in sorted(profiles.items()):
        if not profile or (allowed is not None and iso not in allowed):
            continue
        economy = profile.get('economy') or {}
        exports, imports = economy.get('export_partners'), economy.get('import_partners')
        fuels = profile.get('energy_fuels') or {}
        entry = {
            'name': country_name(iso),
            'population': (population or {}).get(iso, [None])[0],
            'export_partners': _partners(exports, unmapped),
            'import_partners': _partners(imports, unmapped),
            'partners_as_of': {'exports': (exports or {}).get('as_of'), 'imports': (imports or {}).get('as_of')},
            'export_commodities': [c.lower() for c in ((economy.get('exports') or {}).get('items') or [])],
            'fuels': fuels,
        }
        if entry['export_partners'] or entry['import_partners'] or fuels or entry['export_commodities']:
            countries[iso] = entry
    return {
        'built_at': built_at or datetime.now(timezone.utc).isoformat(),
        'source': SOURCE,
        'countries': countries,
        'unmapped_partner_names': sorted(n for n in unmapped if n),
    }


_warming = threading.Lock()


def cached_graph():
    """The graph if it is already built, else None (never builds: building takes about a minute)."""
    return cache_get(GRAPH_KEY)


def warm_graph_async():
    """Start building the graph in the background unless a build is already running. Returns immediately."""
    def run():
        try:
            get_graph()
        except Exception as e:  # never matters to the caller
            logger.info('[Cascade] graph warm-up failed: %s', e)
        finally:
            _warming.release()
    if _warming.acquire(blocking=False):
        threading.Thread(target=run, daemon=True).start()


def get_graph(force=False):
    """The cached country graph, built from every Factbook profile the app knows (about 250 files; takes a minute the first time)."""
    if not force:
        cached = cache_get(GRAPH_KEY)
        if cached is not None:
            return cached
    isos = sorted(_codes())
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        profiles = dict(zip(isos, pool.map(FactbookConnector.fetch_profile, isos)))
    from services.country_indicators import real_countries
    allowed = real_countries() | {'TW'}      # Taiwan is not a World Bank country but is a node the cascade needs
    from services.country_indicators import latest_all
    graph = build_graph(profiles, allowed=allowed if len(allowed) > 50 else None, population=latest_all('SP.POP.TOTL'))
    if graph['countries']:
        cache_set(GRAPH_KEY, graph, ttl=GRAPH_TTL)
    logger.info(f"[Cascade] graph built: {len(graph['countries'])} countries, {len(graph['unmapped_partner_names'])} unmapped partner names")
    return graph
