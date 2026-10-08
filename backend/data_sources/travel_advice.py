"""
UK Foreign, Commonwealth & Development Office travel advice, per country, from the GOV.UK content API (keyless, Open Government
Licence v3.0). It reports the UK government's own warning level and the first lines of its summary; it is one government's view,
not a measure of risk, and the screen says so. Returns None when a country has no page or the API cannot be reached.
"""
import json
import logging
import re
from pathlib import Path

try:
    import requests
except Exception:
    requests = None

from cache import cache_get, cache_set

logger = logging.getLogger(__name__)

BASE = 'https://www.gov.uk/api/content/foreign-travel-advice'
PAGE = 'https://www.gov.uk/foreign-travel-advice'
SOURCE = 'UK FCDO travel advice (Open Government Licence v3.0)'
HEADERS = {'User-Agent': 'GeoIntel/1.0 (geopolitical intelligence platform)'}

ALERTS = {
    'avoid_all_travel_to_whole_country': ('Advises against all travel to the country', 3),
    'avoid_all_but_essential_travel_to_whole_country': ('Advises against all but essential travel to the country', 2),
    'avoid_all_travel_to_parts': ('Advises against all travel to parts of the country', 2),
    'avoid_all_but_essential_travel_to_parts': ('Advises against all but essential travel to parts of the country', 1),
}

_NAMES = None


def squash(name):
    return re.sub(r'[^a-z]', '', (name or '').lower())


def _country_names(iso2):
    global _NAMES
    if _NAMES is None:
        path = Path(__file__).parent / 'country_names.json'
        _NAMES = json.loads(path.read_text(encoding='utf-8'))
    return _NAMES.get(iso2, [])


def _get(url):
    if not requests:
        return None
    for attempt in (1, 2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                return None
            return resp.json()
        except (requests.Timeout, requests.ConnectionError) as e:
            logger.info('[TravelAdvice] %s attempt %s failed: %s', url, attempt, e)
        except Exception as e:
            logger.info('[TravelAdvice] %s failed: %s', url, e)
            return None
    return None


def _slugs():
    """{squashed name or synonym: slug} for every country GOV.UK has advice for (cached a week)."""
    cached = cache_get('traveladvice:slugs')
    if cached is not None:
        return cached
    data = _get(BASE)
    if not data:
        return {}
    table = {}
    for child in (data.get('links') or {}).get('children', []):
        country = (child.get('details') or {}).get('country') or {}
        slug = country.get('slug')
        if not slug:
            continue
        for name in [country.get('name'), *(country.get('synonyms') or [])]:
            if name:
                table[squash(name)] = slug
    cache_set('traveladvice:slugs', table, ttl=7 * 24 * 3600)
    return table


def _lines(body):
    # Block ends become line breaks; inline tags (links, emphasis) are just removed so a sentence stays whole.
    text = re.sub(r'</(?:p|li|h[1-6]|div|ul|ol)>|<br\s*/?>', '\n', body or '')
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&nbsp;', ' ')
    return [re.sub(r'\s+', ' ', line).strip() for line in text.split('\n') if line.strip()]


def advice(iso2):
    """{'level': 0-3, 'alerts': [{'label', 'weight'}], 'summary': [...], 'updated', 'url', 'source'} or None."""
    key = f'traveladvice:{iso2}'
    cached = cache_get(key)
    if cached is not None:
        return cached or None
    slugs = _slugs()
    slug = next((slugs[squash(n)] for n in _country_names(iso2) if squash(n) in slugs), None)
    if not slug:
        return None
    page = _get(f'{BASE}/{slug}')
    if not page:
        return None
    details = page.get('details') or {}
    alerts = [{'label': ALERTS[a][0], 'weight': ALERTS[a][1]} for a in details.get('alert_status') or [] if a in ALERTS]
    first = (details.get('parts') or [{}])[0].get('body')
    summary = [line for line in _lines(first) if 'advises' in line.lower()][:3]
    result = {
        'level': max([a['weight'] for a in alerts], default=0), 'alerts': alerts, 'summary': [s[:320] for s in summary],
        'updated': (details.get('reviewed_at') or details.get('updated_at') or '')[:10] or None,
        'url': f'{PAGE}/{slug}', 'source': SOURCE,
    }
    cache_set(key, result, ttl=12 * 3600)
    return result
