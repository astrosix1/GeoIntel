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
from services import country_data as bundled
from services import country_indicators as wb
from services.country_detail import _with_counts, build_conflicts

logger = logging.getLogger(__name__)

PEOPLE_STATS = [
    ('SP.POP.TOTL', 'Population', '', 0),
    ('SP.DYN.LE00.IN', 'Life expectancy', 'years', 1),
    ('SP.DYN.CBRT.IN', 'Birth rate', 'per 1,000 people', 1),
    ('SP.DYN.TFRT.IN', 'Fertility rate', 'births per woman', 2),
    ('SP.POP.GROW', 'Population growth', '% a year', 2),
    ('SP.URB.TOTL.IN.ZS', 'Urban population', '% of total', 1),
    ('SP.POP.DPND', 'Dependency ratio', 'per 100 of working age', 1),
    ('SP.DYN.IMRT.IN', 'Infant mortality', 'per 1,000 births', 1),
    ('SE.ADT.LITR.ZS', 'Adult literacy', '% of adults', 1),
    ('SE.SEC.ENRR', 'Secondary school enrolment', '% gross', 1),
    ('SH.MED.PHYS.ZS', 'Doctors', 'per 1,000 people', 2),
]

ECONOMY_STATS = [
    ('NY.GDP.MKTP.CD', 'GDP', 'US$', 0, True, True),
    ('NY.GDP.PCAP.CD', 'GDP per person', 'US$', 0),
    ('NY.GDP.MKTP.KD.ZG', 'GDP growth', '% a year', 1),
    ('FP.CPI.TOTL.ZG', 'Inflation', '% a year', 1),
    ('SL.UEM.TOTL.ZS', 'Unemployment', '% of labour force', 1),
    ('GC.DOD.TOTL.GD.ZS', 'Government debt', '% of GDP', 1),
    ('BN.CAB.XOKA.GD.ZS', 'Current account balance', '% of GDP', 1),
    ('BX.KLT.DINV.WD.GD.ZS', 'Foreign investment in', '% of GDP', 1),
    ('SI.POV.GINI', 'Income inequality (Gini)', 'index, 0 to 100', 1),
    ('EG.ELC.ACCS.ZS', 'Access to electricity', '% of people', 1),
]

SECTOR_STATS = [
    ('NV.AGR.TOTL.ZS', 'Agriculture', '% of GDP', 1, False),
    ('NV.IND.TOTL.ZS', 'Industry', '% of GDP', 1, False),
    ('NV.SRV.TOTL.ZS', 'Services', '% of GDP', 1, False),
]

# What the first visitor should not wait for: the all-country tables behind the ranks.
WARM_INDICATORS = [spec[0] for spec in PEOPLE_STATS + ECONOMY_STATS]

TABS = ('government', 'people', 'migration', 'economy', 'security', 'geography')
CACHE_SECONDS = 24 * 3600
# Raise when a tab's data changes shape, so tabs cached by an older version (Redis keeps them across deploys) are not served.
TAB_VERSION = 2
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
    out['stats'] = wb.stats(cc, PEOPLE_STATS)
    # The population comes from the same fetch as the figures above, so a hiccup cannot show one and lose the other.
    pop_stat = next((s for s in out['stats'] if s['code'] == 'SP.POP.TOTL'), None)
    population, year = (pop_stat['value'], pop_stat['year']) if pop_stat else _population(cc)
    out['population'], out['population_year'] = population, year
    if out['stats']:
        out['sources'].append(wb.SOURCE)
    out['hdi'] = bundled.hdi(cc)
    if out['hdi']:
        out['sources'].append(out['hdi']['source'])
    if factbook:
        people = dict(factbook['people'])
        people['religions'] = _with_counts(people.get('religions'), population)
        people['ethnic_groups'] = _with_counts(people.get('ethnic_groups'), population)
        out['people'] = people
        out['sources'].append(FACTBOOK)
    return out if (factbook or out['stats'] or out['hdi']) else None


def _migration(cc):
    from services.country_migration import build_tab
    factbook = FactbookConnector.fetch_profile(cc)
    out = build_tab(cc)
    if out and factbook and factbook['people'].get('net_migration_rate'):
        out['net_migration_rate'] = factbook['people']['net_migration_rate']
        out['sources'].append(FACTBOOK)
    return out


def _economy(cc):
    out = _base(cc, 'economy')
    factbook = FactbookConnector.fetch_profile(cc)
    out['stats'] = wb.stats(cc, ECONOMY_STATS)
    out['sectors'] = wb.stats(cc, SECTOR_STATS)
    if out['stats'] or out['sectors']:
        out['sources'].append(wb.SOURCE)
    out['energy'] = bundled.energy(cc)
    if out['energy']:
        out['sources'].append(out['energy']['source'])
    out['minerals'] = bundled.minerals(cc)
    if out['minerals']:
        out['sources'].append(out['minerals']['source'])
    if factbook:
        out['economy'] = factbook['economy']
        out['infrastructure'] = factbook['infrastructure']
        out['sources'].append(FACTBOOK)
    return out if (factbook or out['stats'] or out['energy'] or out['minerals']) else None


def _security(cc):
    from services.country_security import build_tab
    return build_tab(cc)


def _geography(cc):
    return _base(cc, 'geography')


_BUILDERS = {'government': _government, 'people': _people, 'migration': _migration, 'economy': _economy,
             'security': _security, 'geography': _geography}


def get_country_tab(country_code, tab):
    """The data for one tab, or None if the tab is unknown or nothing real is available for it."""
    cc = (country_code or '').upper()
    if not cc or tab not in _BUILDERS:
        return None
    key = f'country_tab:v{TAB_VERSION}:{cc}:{tab}'
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
