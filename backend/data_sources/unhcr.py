"""
UNHCR Refugee Statistics API: refugees, asylum seekers, displaced and stateless people by country of origin and of asylum.
Open data (CC BY 4.0), no key. https://api.unhcr.org/population/v1

The API's own country codes are not ISO (Algeria is ALG, Germany is GFR), so the countries endpoint is read once to translate
from ISO alpha-2. Every function returns None when the API cannot be reached; nothing is ever filled in.
"""
import logging

try:
    import requests
except Exception:
    requests = None

from cache import cache_get, cache_set

logger = logging.getLogger(__name__)

BASE = 'https://api.unhcr.org/population/v1'
SOURCE = 'UNHCR Refugee Statistics'
CACHE_SECONDS = 24 * 3600
TIMEOUT = 12
FIRST_YEAR = 2015


def _items(path, params):
    """The list of rows of one UNHCR call, or None on failure. Cached for a day."""
    if not requests:
        return None
    key = 'unhcr:' + path + ':' + '&'.join(f'{k}={params[k]}' for k in sorted(params))
    cached = cache_get(key)
    if cached is not None:
        return cached
    for attempt in (1, 2):
        try:
            resp = requests.get(f'{BASE}/{path}', params=params, timeout=TIMEOUT, headers={'User-Agent': 'GeoIntel'})
            if resp.status_code != 200:
                return None
            items = resp.json().get('items')
            if not isinstance(items, list):
                return None
            cache_set(key, items, ttl=CACHE_SECONDS)
            return items
        except (requests.Timeout, requests.ConnectionError) as e:
            logger.info('[UNHCR] %s attempt %s failed: %s', path, attempt, e)
        except Exception as e:
            logger.info('[UNHCR] %s failed: %s', path, e)
            return None
    return None


def _codes():
    """({iso2: unhcr code}, {iso3: iso2}) from the countries endpoint, cached a week."""
    cached = cache_get('unhcr:codes')
    if cached is not None:
        return cached['to_unhcr'], cached['iso3_to_iso2']
    items = _items('countries/', {'limit': 400})
    if not items:
        return {}, {}
    to_unhcr = {c['iso2']: c['code'] for c in items if c.get('iso2') and c.get('code')}
    iso3 = {c['iso']: c['iso2'] for c in items if c.get('iso') and c.get('iso2')}
    cache_set('unhcr:codes', {'to_unhcr': to_unhcr, 'iso3_to_iso2': iso3}, ttl=7 * 24 * 3600)
    return to_unhcr, iso3


def _clean(row, fields):
    return {f: int(row[f]) for f in fields if isinstance(row.get(f), (int, float)) and row[f]}


FIELDS = ('refugees', 'asylum_seekers', 'idps', 'stateless', 'returned_refugees', 'returned_idps', 'ooc', 'hst')


def _series(role, iso2):
    """[{year, refugees, ...}] oldest first for a country as host ('coa') or as origin ('coo')."""
    to_unhcr, _ = _codes()
    code = to_unhcr.get(iso2)
    if not code:
        return None
    items = _items('population/', {role: code, 'yearFrom': FIRST_YEAR, 'yearTo': 2100, 'limit': 100})
    if not items:
        return None
    rows = [{'year': r['year'], **_clean(r, FIELDS)} for r in items if isinstance(r.get('year'), int)]
    return sorted(rows, key=lambda r: r['year']) or None


def hosted_series(iso2):
    """People of concern living in the country, by year."""
    return _series('coa', iso2)


def origin_series(iso2):
    """People of concern who come from the country (refugees abroad, asylum seekers, displaced at home, stateless), by year."""
    return _series('coo', iso2)


def _breakdown(role, other, iso2, year, limit_rows=12):
    to_unhcr, iso3_to_iso2 = _codes()
    code = to_unhcr.get(iso2)
    if not code:
        return None
    items = _items('population/', {role: code, 'year': year, f'{other}_all': 'true', 'limit': 500})
    if not items:
        return None
    rows = []
    for r in items:
        partner = iso3_to_iso2.get(r.get(f'{other}_iso'))
        counts = _clean(r, ('refugees', 'asylum_seekers'))
        if partner and counts:
            rows.append({'country_code': partner, **counts, 'total': sum(counts.values())})
    rows.sort(key=lambda r: -r['total'])
    return rows[:limit_rows] or None


def hosted_by_origin(iso2, year):
    """Where the refugees and asylum seekers living in this country come from."""
    return _breakdown('coa', 'coo', iso2, year)


def abroad_by_destination(iso2, year):
    """Where this country's refugees and asylum seekers now live."""
    return _breakdown('coo', 'coa', iso2, year)
