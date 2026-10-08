import os
import requests

from ._shared import logger
from services.ai_client import AI_LOCATION_MODEL

NOMINATIM_BASE = "https://nominatim.openstreetmap.org/search"

# Optional: same AI-primary/static-fallback pattern app.py's anthropic_client
# already uses for briefings/history — here it drives real incident-level
# geocoding (see NominatimGeocoder / _extract_incident_location) instead of
# text generation. A separate client instance because this module has no
# dependency on app.py today and geocoding needs to keep working even if
# app.py's own client init ever changes.
try:
    from anthropic import Anthropic
    _geocode_ai_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY', ''))
except Exception:
    _geocode_ai_client = None


class NominatimGeocoder:
    """
    Thin client for OpenStreetMap's free Nominatim geocoding API — resolves
    an arbitrary place name (a landmark, a national capital, an ad-hoc
    incident location) to real coordinates, no API key required. This is
    what makes precise pins possible for things the curated LOCATION_MAP
    below was never going to cover (the UN, the White House, a specific
    neighborhood a missile was heard over) without hand-maintaining an
    ever-growing landmark table.

    Nominatim's usage policy caps free use at 1 request/second and requires
    a real, descriptive User-Agent identifying the calling application —
    both enforced here, the same courtesy fetch_wikipedia_bilateral() (see
    app.py) already extends to Wikipedia's API.
    """
    _last_request_at = 0.0
    _cache = {}  # place name -> {'lat', 'lon', 'country'} or None, in-process
    _reverse_cache = {}  # (lat, lon) rounded to 2 places -> place name, in-process

    @staticmethod
    def geocode(place_name):
        """Real (lat, lon, country) for `place_name`, or None if Nominatim
        has nothing for it or the request fails. See geocode_status() when
        the caller must tell those two apart."""
        return NominatimGeocoder.geocode_status(place_name)[0]

    @staticmethod
    def reverse(lat, lon):
        """The name of the place at a point (town or city, then region), or None. For labelling clusters of events; a failed
        lookup is not remembered, so a later try can succeed. Uses the same one-request-a-second limit as geocode()."""
        key = (round(lat, 2), round(lon, 2))
        if key in NominatimGeocoder._reverse_cache:
            return NominatimGeocoder._reverse_cache[key]
        import time
        elapsed = time.monotonic() - NominatimGeocoder._last_request_at
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        NominatimGeocoder._last_request_at = time.monotonic()
        try:
            response = requests.get(
                NOMINATIM_BASE.replace('/search', '/reverse'),
                params={'lat': lat, 'lon': lon, 'format': 'json', 'zoom': 10, 'addressdetails': 1, 'accept-language': 'en'},
                headers={'User-Agent': 'GeoIntel/1.0 (geopolitical intelligence platform)'},
                timeout=10,
            )
            response.raise_for_status()
            address = (response.json() or {}).get('address') or {}
        except Exception as e:
            logger.warning(f"Nominatim reverse failed for {lat},{lon}: {e}")
            return None
        local = next((address[k] for k in ('city', 'town', 'village', 'municipality', 'county', 'state_district') if address.get(k)), None)
        region = address.get('state') or address.get('region')
        name = ', '.join(p for p in (local, region if region != local else None) if p) or None
        NominatimGeocoder._reverse_cache[key] = name
        return name

    @staticmethod
    def geocode_status(place_name):
        """(result, failed): like geocode(), but `failed` is True when the
        request itself failed (network error, bad status) rather than
        Nominatim having no match. A failure is NOT cached, so a transient
        outage doesn't poison later lookups of the same name.

        Real (lat, lon, country) for `place_name`, or None if Nominatim
        has nothing for it or the request fails. Cached in-process by exact
        place name — the same landmark (the UN, the Kremlin) recurs across
        many articles over time, and repeating the network call for an
        identical string would just burn the shared rate limit."""
        if not place_name:
            return None, False
        key = place_name.strip().lower()
        if key in NominatimGeocoder._cache:
            return NominatimGeocoder._cache[key], False

        import time
        elapsed = time.monotonic() - NominatimGeocoder._last_request_at
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        NominatimGeocoder._last_request_at = time.monotonic()

        result = None
        failed = False
        try:
            response = requests.get(
                NOMINATIM_BASE,
                # accept-language=en: Nominatim otherwise replies in the
                # location's local language by default (e.g. country
                # "Россия" for Russia) — every other country name in this
                # app (the Actor roster, LOCATION_MAP) is English, and
                # analyze_cascade()'s initial-actor lookup matches
                # Crisis.country against Actor.name by exact string, so a
                # non-English country name here would silently never match.
                params={'q': place_name, 'format': 'json', 'addressdetails': 1, 'limit': 1, 'accept-language': 'en'},
                headers={'User-Agent': 'GeoIntel/1.0 (geopolitical intelligence platform)'},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if data:
                match = data[0]
                result = {
                    'lat': float(match['lat']),
                    'lon': float(match['lon']),
                    'country': (match.get('address') or {}).get('country'),
                }
        except Exception as e:
            failed = True
            logger.warning(f"Nominatim geocode failed for '{place_name}': {e}")

        if not failed:
            NominatimGeocoder._cache[key] = result
        return result, failed


def ai_location_available():
    """True when an Anthropic key is configured for incident-location extraction."""
    return bool(_geocode_ai_client and _geocode_ai_client.api_key)


def _extract_incident_location(text):
    """The location name from extract_incident_location_status(), or None.
    None here always means "fall back", whatever the reason."""
    return extract_incident_location_status(text)[0]


def extract_incident_location_status(text):
    """(name, failed): `failed` is True when the model call itself errored
    (outage, rate limit) as opposed to the model finding no clear location,
    so callers can retry the former and not the latter.

    Ask Claude (a small, cheap model) for the single most specific
    real-world location (a building, landmark, city, or region) genuinely
    associated with the EVENT this article describes, not just any place
    named in passing. The name is None when no ANTHROPIC_API_KEY is
    configured, the model finds no clear location, or anything goes wrong.
    None here always means "fall back to LOCATION_MAP city-matching" and
    never a guessed location.
    """
    if not _geocode_ai_client or not _geocode_ai_client.api_key:
        return None, False
    try:
        message = _geocode_ai_client.messages.create(
            model=AI_LOCATION_MODEL,
            max_tokens=40,
            messages=[{
                "role": "user",
                "content": (
                    "What is the single most specific real-world location "
                    "(a building, landmark, city, or region) genuinely "
                    "associated with the main event in this news text — not "
                    "just any place mentioned in passing? Reply with ONLY "
                    "the location name (e.g. \"United Nations Headquarters, "
                    "New York\" or \"the Kremlin, Moscow\"), or reply with "
                    "exactly NONE if there is no clear location.\n\n"
                    f"Text: {text[:1000]}"
                ),
            }],
        )
        answer = message.content[0].text.strip()
        if not answer or answer.upper() == 'NONE':
            return None, False
        return answer, False
    except Exception as e:
        logger.warning(f"AI location extraction failed: {e}")
        return None, True
