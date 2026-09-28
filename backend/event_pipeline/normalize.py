"""
Field normalization and stable identifiers.

The old NewsAPI crisis id was f"news_{source}_{published[:10]}", so every
article one outlet published on a given day collided on a single id: the main
sync overwrote them one after another and the multilingual sync kept only the
first. Ids now derive from the article's canonical URL, which is unique per
article and identical across the queries and languages that return it.
"""
import hashlib
import math
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Crisis column limits (models.py) — writing past these fails on Postgres.
MAX_ID_LEN = 50
MAX_TITLE_LEN = 200
MAX_SOURCE_ID_LEN = 100
MAX_COUNTRY_LEN = 100

_TRACKING_PARAMS = {'fbclid', 'gclid', 'dclid', 'msclkid', 'mc_cid', 'mc_eid', 'ref', 'ref_src', 'cmpid', 'ocid'}

# Title is not required here — the titles stage supplies or rejects it.
REQUIRED_FIELDS = ('id', 'type', 'country', 'latitude', 'longitude')


def canonical_url(url):
    """Lowercase scheme/host, drop 'www.', tracking query params, AMP
    variants, the fragment and any trailing slash — so the same article
    shared with different tracking tails maps to one identity."""
    if not url:
        return ''
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    host = (parts.hostname or '').lower()
    if host.startswith('www.'):
        host = host[4:]
    if host.startswith('amp.'):
        host = host[4:]
    path = parts.path or ''
    for amp_suffix in ('/amp', '/amp/'):
        if path.endswith(amp_suffix):
            path = path[: -len(amp_suffix)]
    path = path.rstrip('/')
    query = urlencode(sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith('utm_') and k.lower() not in _TRACKING_PARAMS and k.lower() != 'amp'
    ))
    return urlunsplit(((parts.scheme or 'https').lower(), host, path, query, ''))


def stable_news_id(url, prefix='news'):
    """Deterministic, collision-resistant crisis id for a news article."""
    digest = hashlib.sha1(canonical_url(url).encode('utf-8')).hexdigest()[:16]
    return f"{prefix}_{digest}"


def truncate_words(text, limit):
    text = ' '.join(str(text).split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if ' ' in cut:
        cut = cut.rsplit(' ', 1)[0]
    return cut.rstrip(' ,;:-') + '…'


def normalize_candidate(candidate):
    """Validate and clamp one candidate crisis dict in place.

    Returns None when the candidate is usable, or a reject reason code:
    missing_fields, invalid_coordinates.
    """
    for field in REQUIRED_FIELDS:
        value = candidate.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            return 'missing_fields'

    try:
        lat = float(candidate['latitude'])
        lon = float(candidate['longitude'])
    except (TypeError, ValueError):
        return 'invalid_coordinates'
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return 'invalid_coordinates'
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return 'invalid_coordinates'
    if lat == 0 and lon == 0:  # the "no geo resolved" placeholder, never a real pin
        return 'invalid_coordinates'
    candidate['latitude'], candidate['longitude'] = lat, lon

    # Timezone-aware datetimes (NewsAPI's "...Z") -> naive UTC, like every
    # other date in the database, so they compare with stored rows.
    for field in ('date_start', 'date_scheduled'):
        value = candidate.get(field)
        if isinstance(value, datetime) and value.tzinfo is not None:
            candidate[field] = value.astimezone(timezone.utc).replace(tzinfo=None)

    candidate['id'] = str(candidate['id'])[:MAX_ID_LEN]
    if candidate.get('title'):
        candidate['title'] = truncate_words(candidate['title'], MAX_TITLE_LEN)
    candidate['country'] = ' '.join(str(candidate['country']).split())[:MAX_COUNTRY_LEN]
    if candidate.get('source_id') is not None:
        candidate['source_id'] = str(candidate['source_id'])[:MAX_SOURCE_ID_LEN]
    for score in ('severity', 'confidence', 'location_confidence'):
        if candidate.get(score) is not None:
            candidate[score] = max(0, min(100, int(round(float(candidate[score])))))
    return None
