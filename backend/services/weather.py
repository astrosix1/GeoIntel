"""
Weather-mode assembly — real active tropical-cyclone/storm data from GDACS
for the globe's Weather mode (step 5 of the rewrite plan). A thin service
layer (mirrors services/country_profile.py's shape) so the blueprint stays
a pure HTTP wrapper and the caching/shaping logic is unit-testable on its
own.
"""
import logging
from datetime import datetime

from cache import cache_get, cache_set
from data_sources import GDACSConnector

logger = logging.getLogger(__name__)

_CACHE_KEY = 'weather:storms'
_CACHE_TTL = 300  # 5 minutes — GDACS's own feed updates on a similar cadence


def get_active_storms():
    """
    Returns {'storms': [...], 'count': N, 'source': 'gdacs.org',
    'generated_at': iso timestamp} on success (storms may legitimately be
    an empty list when GDACS currently reports zero active tropical
    cyclones), or None if the live GDACS feed itself could not be reached —
    never a fabricated storm list.
    """
    cached = cache_get(_CACHE_KEY)
    if cached is not None:
        return cached

    storms = GDACSConnector.fetch_active_storms()
    if storms is None:
        logger.info("[weather] GDACS feed unavailable — returning None, not a fabricated fallback")
        return None

    result = {
        'storms': storms,
        'count': len(storms),
        'source': 'gdacs.org',
        'generated_at': datetime.utcnow().isoformat(),
    }
    cache_set(_CACHE_KEY, result, ttl=_CACHE_TTL)
    return result
