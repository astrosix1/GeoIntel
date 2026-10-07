"""
Premium country detail: government, people, economy, infrastructure, security and migration, from the World Factbook
(public domain) and the bundled UN DESA migrant-stock table. Every group carries its own "as of" year; anything the
sources do not give is simply absent, and the UI says so rather than filling it in.

Head counts for religions and ethnic groups are the Factbook's percentage applied to the World Bank population, and are
marked as estimates. Age bands carry the Factbook's own counts.
"""
import json
import logging
from pathlib import Path

from cache import cache_get, cache_set
from data_sources import WorldBankConnector
from data_sources.factbook import FactbookConnector

logger = logging.getLogger(__name__)

_MIGRATION = None
_POPULATION_INDICATOR = 'SP.POP.TOTL'
_MIGRANT_STOCK_INDICATOR = 'SM.POP.TOTL'


def _migration_table():
    global _MIGRATION
    if _MIGRATION is None:
        path = Path(__file__).resolve().parent.parent / 'data_sources' / 'migration_origins.json'
        _MIGRATION = json.loads(path.read_text(encoding='utf-8'))
    return _MIGRATION


def _with_counts(shares, population):
    """Copy of a shares block with an estimated head count on every item (and sub-item) when the population is known."""
    if not shares:
        return None

    def convert(items):
        out = []
        for item in items:
            row = dict(item)
            if population:
                row['estimated_count'] = round(population * item['percent'] / 100)
            if item.get('children'):
                row['children'] = convert(item['children'])
            out.append(row)
        return out

    return {**shares, 'items': convert(shares['items'])}


def build_migration(iso2, population=None):
    """Where the country's immigrants come from, with counts. Origins are the largest sources (UN DESA, 2024); the total
    is the World Bank's migrant stock when it has one."""
    table = _migration_table()
    row = (table.get('countries') or {}).get(iso2)
    if not row:
        return None
    total, year = WorldBankConnector.fetch_latest_indicator(iso2, _MIGRANT_STOCK_INDICATOR)
    stock = int(total) if total else row['total']
    listed = sum(count for _, count in row['origins'])
    return {
        'year': table.get('year'),
        'source': table.get('source'),
        'migrant_stock': stock,
        'migrant_stock_year': year if total else table.get('year'),
        'share_of_population': round(stock / population * 100, 1) if population and stock else None,
        'origins': [{'country_code': code, 'count': count, 'percent_of_migrants': round(count / stock * 100, 1) if stock else None}
                    for code, count in row['origins']],
        'other_count': max(stock - listed, 0) if stock else None,
    }


def get_country_detail(country_code):
    country_code = (country_code or '').upper()
    if not country_code:
        return None
    cache_key = f'country_detail:{country_code}'
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    factbook = FactbookConnector.fetch_profile(country_code)
    population, population_year = WorldBankConnector.fetch_latest_indicator(country_code, _POPULATION_INDICATOR)
    migration = build_migration(country_code, population)
    if not factbook and not migration:
        return None  # nothing real to show; the caller answers 404 rather than an empty shell

    detail = {'country_code': country_code, 'sources': [], 'population': population, 'population_year': population_year}
    if factbook:
        people = dict(factbook['people'])
        people['religions'] = _with_counts(people.get('religions'), population)
        people['ethnic_groups'] = _with_counts(people.get('ethnic_groups'), population)
        detail.update(government=factbook['government'], people=people, economy=factbook['economy'],
                      infrastructure=factbook['infrastructure'], security=factbook['security'])
        detail['sources'].append('CIA World Factbook')
    if population:
        detail['sources'].append('World Bank (population)')
    if migration:
        detail['migration'] = migration
        detail['sources'].append(migration['source'])

    cache_set(cache_key, detail, ttl=24 * 3600)
    return detail
