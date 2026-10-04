"""Place-name search for the watchlist, from Open-Meteo's geocoding API (same
provider, licence and commercial-key switch as services/forecast.py)."""
import logging

import requests

from cache import cache_get, cache_set
from services.forecast import ForecastUnavailable, provider_params, provider_url

logger = logging.getLogger(__name__)

MIN_QUERY = 2
MAX_QUERY = 80
MAX_RESULTS = 8
CACHE_TTL = 24 * 60 * 60
TIMEOUT = 8


class InvalidQuery(ValueError):
    pass


def search_places(query):
    """[{name, country, admin1, lat, lon}, ...], best match first (possibly
    empty). Raises InvalidQuery for a too-short/long query, ForecastUnavailable
    if the provider fails."""
    q = ' '.join((query or '').split())
    if not MIN_QUERY <= len(q) <= MAX_QUERY:
        raise InvalidQuery(f'query must be {MIN_QUERY}-{MAX_QUERY} characters')

    cache_key = f'geocode:{q.lower()}'
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            f"{provider_url('geocoding')}/v1/search",
            params=provider_params({'name': q, 'count': MAX_RESULTS, 'language': 'en', 'format': 'json'}),
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        raw = response.json().get('results') or []
    except Exception as e:
        logger.error(f"Geocoding failed for {q!r}: {e}")
        raise ForecastUnavailable(str(e))

    results = [
        {
            'name': item['name'],
            'country': item.get('country'),
            'admin1': item.get('admin1'),
            'lat': item['latitude'],
            'lon': item['longitude'],
        }
        for item in raw
        if isinstance(item.get('name'), str)
        and isinstance(item.get('latitude'), (int, float))
        and isinstance(item.get('longitude'), (int, float))
    ]
    cache_set(cache_key, results, ttl=CACHE_TTL)
    return results
