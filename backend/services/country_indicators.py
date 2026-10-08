"""
World Bank indicators as series with a year, a source and a rank among countries, for the country tabs.

Everything here is real data or nothing: a failed fetch gives None, never a stand-in. Results are cached for 24 hours; the
all-country table behind a rank is one call per indicator, shared by every country.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

try:
    import requests
except Exception:
    requests = None

from cache import cache_get, cache_set

logger = logging.getLogger(__name__)

WORLDBANK_BASE = 'https://api.worldbank.org/v2'
SOURCE = 'World Bank'
CACHE_SECONDS = 24 * 3600
SERIES_YEARS = 35
TIMEOUT = 8


def _get(path, params):
    """The JSON body of a World Bank call, or None on any failure (including the API's own error message)."""
    if not requests:
        return None
    for attempt in (1, 2):  # the API occasionally stalls; one more try is cheap, more would stack up inside a tab
        try:
            resp = requests.get(f'{WORLDBANK_BASE}/{path}', params={'format': 'json', **params}, timeout=TIMEOUT)
            if resp.status_code != 200:
                return None
            body = resp.json()
            if not isinstance(body, list) or len(body) < 2 or not isinstance(body[1], list):
                return None
            return body
        except (requests.Timeout, requests.ConnectionError) as e:
            logger.info('[WorldBank] %s attempt %s failed: %s', path, attempt, e)
        except Exception as e:
            logger.info('[WorldBank] %s failed: %s', path, e)
            return None
    return None


def real_countries():
    """ISO alpha-2 codes of actual countries (the World Bank also lists regions and income groups, which must not be ranked)."""
    cached = cache_get('wb:countries')
    if cached is not None:
        return set(cached)
    body = _get('country', {'per_page': 400})
    if not body:
        return set()
    codes = sorted(c['iso2Code'] for c in body[1] if (c.get('region') or {}).get('id') != 'NA' and len(c.get('iso2Code') or '') == 2)
    cache_set('wb:countries', codes, ttl=7 * 24 * 3600)
    return set(codes)


def series(country_code, indicator, years=SERIES_YEARS):
    """[[year, value], ...] oldest first, years with no value left out; None if nothing could be fetched."""
    key = f'wb:series:{country_code}:{indicator}'
    cached = cache_get(key)
    if cached is not None:
        return cached or None
    body = _get(f'country/{country_code}/indicator/{indicator}', {'mrv': years, 'per_page': years + 5})
    if body is None:
        return None
    points = sorted([int(r['date']), r['value']] for r in body[1] if r.get('value') is not None and str(r.get('date', '')).isdigit())
    cache_set(key, points, ttl=CACHE_SECONDS)
    return points or None


def latest_all(indicator):
    """{iso2: [value, year]} for every real country: its most recent value. One call, cached, shared by all ranks."""
    key = f'wb:all:{indicator}'
    cached = cache_get(key)
    if cached is not None:
        return cached
    body = _get(f'country/all/indicator/{indicator}', {'mrnev': 1, 'per_page': 400})
    countries = real_countries()
    if not body or not countries:
        return {}
    table = {}
    for row in body[1]:
        code = (row.get('country') or {}).get('id')
        if code in countries and row.get('value') is not None and str(row.get('date', '')).isdigit():
            table[code] = [row['value'], int(row['date'])]
    cache_set(key, table, ttl=CACHE_SECONDS)
    return table


def rank_of(country_code, indicator):
    """(rank, of): 1 is the highest value. None when the country or the table is missing."""
    table = latest_all(indicator)
    mine = table.get(country_code)
    if not mine:
        return None
    higher = sum(1 for value, _ in table.values() if value > mine[0])
    return higher + 1, len(table)


def stat(country_code, indicator, label, unit='', decimals=1, with_rank=True):
    """One displayable figure: latest value and year, the series for a trend line, and the rank among countries. None if the
    World Bank has no value for this country."""
    points = series(country_code, indicator)
    if not points:
        return None
    year, value = points[-1]
    out = {
        'code': indicator, 'label': label, 'unit': unit, 'decimals': decimals, 'value': value, 'year': year,
        'series': points[-SERIES_YEARS:], 'source': SOURCE, 'rank': None, 'of': None,
    }
    if with_rank:
        ranked = rank_of(country_code, indicator)
        if ranked:
            out['rank'], out['of'] = ranked
    return out


def stats(country_code, specs):
    """Several stats at once: specs is a list of (indicator, label, unit, decimals). Missing ones are left out, order kept."""
    def one(spec):
        indicator, label, *rest = spec
        return stat(country_code, indicator, label, *rest)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(one, specs))
    return [r for r in results if r]
