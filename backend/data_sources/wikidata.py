"""
Wikidata: who has held a country's top offices, with dates (CC0). Two small SPARQL queries per country, remembered for a day.
Wikidata's coverage is uneven, so the list is shown as "recent holders per Wikidata" next to the Factbook's current names, and
any failure simply leaves it out.
"""
import logging
import re

try:
    import requests
except Exception:
    requests = None

from cache import cache_get, cache_set

logger = logging.getLogger(__name__)

ENDPOINT = 'https://query.wikidata.org/sparql'
HEADERS = {'User-Agent': 'GeoIntel/1.0 (https://github.com/astrosix1/GeoIntel)', 'Accept': 'application/sparql-results+json'}
SOURCE = 'Wikidata (CC0)'
OFFICES = {'head_of_government': 'P6', 'head_of_state': 'P35'}
HOLDERS = 8

QUERY = '''SELECT ?l ?start ?end WHERE {
  ?c wdt:P297 "%(iso)s"; p:%(prop)s ?st. ?st ps:%(prop)s ?p. ?p rdfs:label ?l. FILTER(LANG(?l) = "en")
  OPTIONAL { ?st pq:P580 ?start } OPTIONAL { ?st pq:P582 ?end }
} ORDER BY DESC(?start) LIMIT %(limit)d'''


def _date(value):
    match = re.match(r'(\d{4}-\d{2}-\d{2})', value or '')
    return match.group(1) if match else None


def _holders(iso2, prop):
    if not requests or not re.fullmatch(r'[A-Z]{2}', iso2 or ''):
        return None
    for attempt in (1, 2):
        try:
            resp = requests.get(ENDPOINT, params={'query': QUERY % {'iso': iso2, 'prop': prop, 'limit': HOLDERS}, 'format': 'json'},
                                headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                return None
            rows = resp.json()['results']['bindings']
            seen, out = set(), []
            for r in rows:
                name = r['l']['value']
                start = _date(r.get('start', {}).get('value'))
                if (name, start) in seen or name.startswith('Q'):
                    continue
                seen.add((name, start))
                out.append({'name': name, 'start': start, 'end': _date(r.get('end', {}).get('value'))})
            return out or None
        except (requests.Timeout, requests.ConnectionError) as e:
            logger.info('[Wikidata] %s %s attempt %s failed: %s', iso2, prop, attempt, e)
        except Exception as e:
            logger.info('[Wikidata] %s %s failed: %s', iso2, prop, e)
            return None
    return None


def leaders(iso2):
    """{'head_of_government': [{'name','start','end'}...], 'head_of_state': [...], 'source'} newest first, or None."""
    key = f'wikidata:leaders:{iso2}'
    cached = cache_get(key)
    if cached is not None:
        return cached or None
    out = {}
    for office, prop in OFFICES.items():
        holders = _holders(iso2, prop)
        if holders:
            out[office] = holders
    if not out:
        return None
    out['source'] = SOURCE
    cache_set(key, out, ttl=24 * 3600)
    return out
