"""
The premium country tabs, one builder each, so opening a tab loads only that tab's data:

    government, people, migration, economy, security, geography

Every builder returns a dict with `country_code`, `tab`, `sources` (what the tab used) and its own sections; a section the
sources do not give is simply absent and the UI says so. Each tab is cached for 24 hours (the security tab's event counts
for 15 minutes, in services/country_detail.build_conflicts). Shared pieces live in services/country_detail.py and
services/country_indicators.py.
"""
import logging

from cache import cache_get, cache_set
from data_sources.factbook import FactbookConnector
from services import country_indicators as wb
from services.country_detail import _with_counts, build_conflicts, build_migration

logger = logging.getLogger(__name__)

TABS = ('government', 'people', 'migration', 'economy', 'security', 'geography')
CACHE_SECONDS = 24 * 3600
FACTBOOK = 'CIA World Factbook'


def _population(cc):
    """(population, year) from the World Bank series, or (None, None)."""
    points = wb.series(cc, 'SP.POP.TOTL')
    return (points[-1][1], points[-1][0]) if points else (None, None)


def _base(cc, tab):
    return {'country_code': cc, 'tab': tab, 'sources': []}


def _government(cc):
    out = _base(cc, 'government')
    factbook = FactbookConnector.fetch_profile(cc)
    if factbook:
        out['government'] = factbook['government']
        out['sources'].append(FACTBOOK)
    return out if factbook else None


def _people(cc):
    out = _base(cc, 'people')
    factbook = FactbookConnector.fetch_profile(cc)
    out['stats'] = wb.stats(cc, [('SP.POP.TOTL', 'Population', '', 0), ('SP.DYN.CBRT.IN', 'Birth rate', 'per 1,000 people', 1)])
    # The population comes from the same fetch as the figures above, so a hiccup cannot show one and lose the other.
    pop_stat = next((s for s in out['stats'] if s['code'] == 'SP.POP.TOTL'), None)
    population, year = (pop_stat['value'], pop_stat['year']) if pop_stat else _population(cc)
    out['population'], out['population_year'] = population, year
    if out['stats']:
        out['sources'].append(wb.SOURCE)
    if factbook:
        people = dict(factbook['people'])
        people['religions'] = _with_counts(people.get('religions'), population)
        people['ethnic_groups'] = _with_counts(people.get('ethnic_groups'), population)
        out['people'] = people
        out['sources'].append(FACTBOOK)
    return out if (factbook or out['stats']) else None


def _migration(cc):
    out = _base(cc, 'migration')
    population, _ = _population(cc)
    migration = build_migration(cc, population)
    factbook = FactbookConnector.fetch_profile(cc)
    if migration:
        out['migration'] = migration
        out['sources'].append(migration['source'])
    if factbook and factbook['people'].get('net_migration_rate'):
        out['net_migration_rate'] = factbook['people']['net_migration_rate']
        out['sources'].append(FACTBOOK)
    return out if migration else None


def _economy(cc):
    out = _base(cc, 'economy')
    factbook = FactbookConnector.fetch_profile(cc)
    if factbook:
        out['economy'] = factbook['economy']
        out['infrastructure'] = factbook['infrastructure']
        out['sources'].append(FACTBOOK)
    return out if factbook else None


def _security(cc):
    out = _base(cc, 'security')
    factbook = FactbookConnector.fetch_profile(cc)
    if factbook:
        out['security'] = factbook['security']
        out['sources'].append(FACTBOOK)
    return out if factbook else None


def _geography(cc):
    return _base(cc, 'geography')


_BUILDERS = {'government': _government, 'people': _people, 'migration': _migration, 'economy': _economy,
             'security': _security, 'geography': _geography}


def get_country_tab(country_code, tab):
    """The data for one tab, or None if the tab is unknown or nothing real is available for it."""
    cc = (country_code or '').upper()
    if not cc or tab not in _BUILDERS:
        return None
    key = f'country_tab:{cc}:{tab}'
    data = cache_get(key)
    if data is None:
        data = _BUILDERS[tab](cc)
        if data is None and tab != 'security':
            return None
        if data is not None:
            cache_set(key, data, ttl=CACHE_SECONDS)
    if tab == 'security':
        # Event counts change by the minute, so they are added fresh (build_conflicts has its own 15-minute cache).
        conflicts = build_conflicts(cc)
        if not data and not conflicts:
            return None
        data = dict(data or _base(cc, 'security'))
        if conflicts:
            data['conflicts'] = conflicts
            data['sources'] = data['sources'] + [conflicts['source']]
    return data
