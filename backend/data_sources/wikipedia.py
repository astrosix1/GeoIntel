"""
A short Wikipedia introduction to how a country is governed, with the attribution Wikipedia's licence (CC BY-SA 4.0) asks for:
the title, a link to the article and the licence. Tries "Politics of X" under the country's common names; a missing or
disambiguation page leaves the intro out rather than showing something unrelated.
"""
import json
import logging
import re
import urllib.parse
from pathlib import Path

try:
    import requests
except Exception:
    requests = None

from cache import cache_get, cache_set

logger = logging.getLogger(__name__)

SUMMARY = 'https://en.wikipedia.org/api/rest_v1/page/summary/'
HEADERS = {'User-Agent': 'GeoIntel/1.0 (https://github.com/astrosix1/GeoIntel)', 'Accept': 'application/json'}
LICENSE = 'CC BY-SA 4.0'
LICENSE_URL = 'https://creativecommons.org/licenses/by-sa/4.0/'
MAX_CHARS = 900

_NAMES = None


def _names(iso2):
    global _NAMES
    if _NAMES is None:
        _NAMES = json.loads((Path(__file__).parent / 'country_names.json').read_text(encoding='utf-8'))
    return sorted(_NAMES.get(iso2, []), key=len)


def _cut(text):
    """The extract cut to whole sentences within MAX_CHARS."""
    if len(text) <= MAX_CHARS:
        return text
    cut = text[:MAX_CHARS]
    end = max(cut.rfind('. '), cut.rfind('.'))
    return cut[:end + 1] if end > 200 else cut.rstrip() + '...'


def _summary(title):
    if not requests:
        return None
    try:
        resp = requests.get(SUMMARY + urllib.parse.quote(title.replace(' ', '_'), safe=''), headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        page = resp.json()
    except Exception as e:
        logger.info('[Wikipedia] %s failed: %s', title, e)
        return None
    if page.get('type') != 'standard' or not page.get('extract'):
        return None
    return page


def politics_intro(iso2):
    """{'title', 'extract', 'url', 'license', 'license_url', 'source'} or None."""
    key = f'wikipedia:politics:{iso2}'
    cached = cache_get(key)
    if cached is not None:
        return cached or None
    for name in _names(iso2):
        for title in (f'Politics of {name}', f'Politics of the {name}'):
            page = _summary(title)
            if page:
                result = {
                    'title': page.get('title') or title, 'extract': _cut(re.sub(r'\s+', ' ', page['extract']).strip()),
                    'url': ((page.get('content_urls') or {}).get('desktop') or {}).get('page') or f'https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(" ", "_"))}',
                    'license': LICENSE, 'license_url': LICENSE_URL, 'source': 'Wikipedia',
                }
                cache_set(key, result, ttl=7 * 24 * 3600)
                return result
    cache_set(key, {}, ttl=24 * 3600)  # remembered as "none" for a day so it is not looked up on every visit
    return None
