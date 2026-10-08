"""Point forecast for Weather mode: current conditions, the next hours and the next days at any latitude/longitude.

Two providers, one shape. MET Norway (services/forecast_met.py) is the default: its data is licensed for commercial use with
attribution. Open-Meteo is used only when OPEN_METEO_API_KEY is set, because its free API is for non-commercial use only and
this is a subscription product; the key switches to Open-Meteo's commercial endpoint with no other change, and brings back the
fields MET Norway does not publish for a global point (wind gusts, chance of rain, visibility, a UV index beyond 2.7 days).

Nothing is ever invented: any upstream failure raises ForecastUnavailable, and a field the provider lacks is None.
"""
import logging
import os
from datetime import datetime, timezone

import requests

from cache import cache_get, cache_set
from services import forecast_met
from services.forecast_errors import ForecastUnavailable, InvalidCoordinates  # noqa: F401  (re-exported for callers)

logger = logging.getLogger(__name__)

FREE_BASE = 'https://api.open-meteo.com'
COMMERCIAL_BASE = 'https://customer-api.open-meteo.com'
GEOCODING_FREE_BASE = 'https://geocoding-api.open-meteo.com'
GEOCODING_COMMERCIAL_BASE = 'https://customer-geocoding-api.open-meteo.com'

CACHE_TTL = 15 * 60
RECENT_HOURS = 24      # the hours just gone, for "what just happened here"
HOURS_SHOWN = 168   # the whole 7 days, for the timeline scrubber
TIMEOUT = 8

CURRENT_FIELDS = [
    'temperature_2m', 'apparent_temperature', 'relative_humidity_2m', 'precipitation',
    'weather_code', 'wind_speed_10m', 'wind_gusts_10m', 'wind_direction_10m',
    'pressure_msl', 'cloud_cover', 'visibility',
]
HOURLY_FIELDS = [
    'temperature_2m', 'precipitation_probability', 'precipitation',
    'wind_speed_10m', 'wind_gusts_10m', 'weather_code',
]
RECENT_FIELDS = ['temperature_2m', 'precipitation']
DAILY_FIELDS = [
    'weather_code', 'temperature_2m_max', 'temperature_2m_min', 'precipitation_sum',
    'precipitation_probability_max', 'wind_gusts_10m_max', 'uv_index_max',
]


def _api_key():
    return os.getenv('OPEN_METEO_API_KEY', '').strip()


def provider():
    """'open-meteo' when a commercial key is configured, otherwise 'met-norway'."""
    return 'open-meteo' if _api_key() else 'met-norway'


def provider_url(kind='forecast'):
    """Base URL for the forecast or geocoding API: the commercial host when a
    key is configured, the free host otherwise."""
    if kind == 'geocoding':
        return GEOCODING_COMMERCIAL_BASE if _api_key() else GEOCODING_FREE_BASE
    return COMMERCIAL_BASE if _api_key() else FREE_BASE


def provider_params(params):
    """Adds the API key (commercial plan only) to a request's params."""
    key = _api_key()
    return {**params, 'apikey': key} if key else params


def check_coordinates(lat, lon):
    """Floats (rounded to 0.1 degree) or InvalidCoordinates. Rounding matches
    the weather models' grid and makes the cache effective."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise InvalidCoordinates('lat and lon must be numbers')
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180) or lat != lat or lon != lon:
        raise InvalidCoordinates('lat must be within -90..90 and lon within -180..180')
    return round(lat, 1) + 0.0, round(lon, 1) + 0.0


def _slice(block, fields, start=0, end=None):
    """{field: list} for the fields present, trimmed to [start:end]."""
    return {f: block[f][start:end] for f in fields if isinstance(block.get(f), list)}


def _first_hour_index(times, now_iso):
    """Index of the first hourly slot at or after the current local hour."""
    for i, t in enumerate(times):
        if t >= now_iso[:13] + ':00':
            return i
    return 0


def get_forecast(lat, lon):
    lat, lon = check_coordinates(lat, lon)
    cache_key = f'forecast:{lat}:{lon}'
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    if provider() == 'met-norway':
        result = forecast_met.build(lat, lon)
        cache_set(cache_key, result, ttl=CACHE_TTL)
        return result

    try:
        response = requests.get(
            f'{provider_url()}/v1/forecast',
            params=provider_params({
                'latitude': lat,
                'longitude': lon,
                'current': ','.join(CURRENT_FIELDS),
                'hourly': ','.join(HOURLY_FIELDS),
                'daily': ','.join(DAILY_FIELDS),
                'forecast_days': 7,
                'past_hours': RECENT_HOURS,
                'timezone': 'auto',
            }),
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
        current = body['current']
        hourly = body['hourly']
        daily = body['daily']
        hourly_times = hourly['time']
    except Exception as e:
        logger.error(f"Forecast lookup failed for {lat},{lon}: {e}")
        raise ForecastUnavailable(str(e))

    start = _first_hour_index(hourly_times, current.get('time', ''))
    end = start + HOURS_SHOWN
    recent_start = max(0, start - RECENT_HOURS)
    result = {
        'lat': body.get('latitude', lat),
        'lon': body.get('longitude', lon),
        'timezone': body.get('timezone'),
        'elevation_m': body.get('elevation'),
        'utc_offset_seconds': body.get('utc_offset_seconds'),
        'current': {'time': current.get('time'), **{k: current.get(k) for k in CURRENT_FIELDS}},
        'hourly': {'time': hourly_times[start:end], **_slice(hourly, HOURLY_FIELDS, start, end)},
        'daily': {'time': daily.get('time', []), **_slice(daily, DAILY_FIELDS)},
        # The model's own values for the hours just gone (analysis, not station readings).
        'recent': {'time': hourly_times[recent_start:start], **_slice(hourly, RECENT_FIELDS, recent_start, start)},
        'units': {
            'current': body.get('current_units', {}),
            'hourly': body.get('hourly_units', {}),
            'daily': body.get('daily_units', {}),
        },
        'source': 'open-meteo.com',
        'attribution': {'name': 'Open-Meteo', 'url': 'https://open-meteo.com/', 'license': 'CC BY 4.0',
                        'license_url': 'https://creativecommons.org/licenses/by/4.0/'},
        'capabilities': {'wind_gusts': True, 'precipitation_probability': True, 'visibility': True, 'uv_hours': 168},
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
    cache_set(cache_key, result, ttl=CACHE_TTL)
    return result
