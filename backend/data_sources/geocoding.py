import os
import requests

from ._shared import logger

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

    @staticmethod
    def geocode(place_name):
        """Real (lat, lon, country) for `place_name`, or None if Nominatim
        has nothing for it or the request fails. Cached in-process by exact
        place name — the same landmark (the UN, the Kremlin) recurs across
        many articles over time, and repeating the network call for an
        identical string would just burn the shared rate limit."""
        if not place_name:
            return None
        key = place_name.strip().lower()
        if key in NominatimGeocoder._cache:
            return NominatimGeocoder._cache[key]

        import time
        elapsed = time.monotonic() - NominatimGeocoder._last_request_at
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        NominatimGeocoder._last_request_at = time.monotonic()

        result = None
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
            logger.warning(f"Nominatim geocode failed for '{place_name}': {e}")

        NominatimGeocoder._cache[key] = result
        return result


def _extract_incident_location(text):
    """
    Ask Claude for the single most specific real-world location (a
    building, landmark, city, or region) genuinely associated with the
    EVENT this article describes — not just any place named in passing.
    Returns a location name string, or None when no ANTHROPIC_API_KEY is
    configured, the model finds no clear location, or anything goes wrong.
    None here always means "fall back to LOCATION_MAP city-matching below"
    — never a guessed location.
    """
    if not _geocode_ai_client or not _geocode_ai_client.api_key:
        return None
    try:
        message = _geocode_ai_client.messages.create(
            model="claude-3-5-sonnet-20241022",
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
            return None
        return answer
    except Exception as e:
        logger.warning(f"AI location extraction failed: {e}")
        return None
