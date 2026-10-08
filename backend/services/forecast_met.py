"""
Point forecast from MET Norway's Locationforecast API (api.met.no, licensed CC BY 4.0 and NLOD 2.0: commercial use allowed with
attribution), shaped like the Open-Meteo forecast the rest of the app already reads, so the panels and alerts need no change.

What MET Norway gives for a global point, and what it does not (checked 2026-10-08): temperature, feels-like, humidity, pressure,
cloud, wind speed and direction, hourly rain amounts for about 2.7 days then 6-hourly out to about 9.5 days, and a weather symbol.
It does **not** give wind gusts, chance of rain or visibility outside the Nordic model, and the clear-sky UV index covers only the
first 2.7 days. Those fields are returned as None, never estimated, and `capabilities` says so, so the screens can hide them.

MET Norway's rules, all followed here: identify the app in the User-Agent, cache and revalidate with If-Modified-Since, round the
coordinates (4 decimals at most; ours are 0.1 degree), stay far below 20 requests a second, and show the attribution.
Times in the result are the place's local clock (zone from services/timezone_lookup.py), like Open-Meteo's `timezone=auto`.
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

from cache import cache_get, cache_set
from services.forecast_errors import ForecastUnavailable
from services.timezone_lookup import zone_at

logger = logging.getLogger(__name__)

URL = 'https://api.met.no/weatherapi/locationforecast/2.0/complete'
USER_AGENT = os.getenv('MET_USER_AGENT') or 'GeoIntel/1.0 (+https://github.com/astrosix1/GeoIntel)'
TIMEOUT = 8
RAW_TTL = 24 * 3600          # how long the last response is kept, to revalidate with If-Modified-Since
FRESH_SECONDS = 10 * 60      # a response this young is used without asking again
STALE_OK_SECONDS = 3 * 3600  # if the API is down, a response up to this old is still shown (with its real age)
DAYS = 7

ATTRIBUTION = {
    'name': 'MET Norway', 'url': 'https://api.met.no/', 'license': 'CC BY 4.0 / NLOD 2.0',
    'license_url': 'https://api.met.no/doc/License',
}

CAPABILITIES = {'wind_gusts': False, 'precipitation_probability': False, 'visibility': False, 'uv_hours': 66}

# MET symbol (day/night suffix removed) -> the WMO code the frontend's icons and labels use.
SYMBOL_TO_WMO = {
    'clearsky': 0, 'fair': 1, 'partlycloudy': 2, 'cloudy': 3, 'fog': 45,
    'lightrain': 61, 'rain': 63, 'heavyrain': 65, 'lightrainshowers': 80, 'rainshowers': 81, 'heavyrainshowers': 82,
    'lightsleet': 66, 'sleet': 67, 'heavysleet': 67, 'lightsleetshowers': 66, 'sleetshowers': 67, 'heavysleetshowers': 67,
    'lightsnow': 71, 'snow': 73, 'heavysnow': 75, 'lightsnowshowers': 85, 'snowshowers': 85, 'heavysnowshowers': 86,
    'lightrainandthunder': 95, 'rainandthunder': 95, 'heavyrainandthunder': 99,
    'lightrainshowersandthunder': 95, 'rainshowersandthunder': 95, 'heavyrainshowersandthunder': 99,
    'lightsleetandthunder': 96, 'sleetandthunder': 96, 'heavysleetandthunder': 99,
    'lightsleetshowersandthunder': 96, 'sleetshowersandthunder': 96, 'heavysleetshowersandthunder': 99,
    'lightsnowandthunder': 95, 'snowandthunder': 95, 'heavysnowandthunder': 99,
    'lightsnowshowersandthunder': 95, 'snowshowersandthunder': 95, 'heavysnowshowersandthunder': 99,
}


def wmo_code(symbol):
    """The WMO weather code for a MET symbol code such as 'partlycloudy_night', or None for one we do not know."""
    if not symbol:
        return None
    return SYMBOL_TO_WMO.get(symbol.split('_')[0])


def _get_raw(lat, lon):
    """(body, fetched_at) for the point: the cached response while it is fresh, a revalidated or new one otherwise, an older one
    if the API is down. Raises ForecastUnavailable when there is nothing to show."""
    key = f'met:raw:{lat}:{lon}'
    cached = cache_get(key)
    now = time.time()
    if cached and now - cached['fetched'] < FRESH_SECONDS:
        return cached['body'], cached['fetched']
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
    if cached and cached.get('last_modified'):
        headers['If-Modified-Since'] = cached['last_modified']
    try:
        response = requests.get(URL, params={'lat': lat, 'lon': lon}, headers=headers, timeout=TIMEOUT)
        if response.status_code == 304 and cached:
            cached['fetched'] = now
            cache_set(key, cached, ttl=RAW_TTL)
            return cached['body'], now
        response.raise_for_status()
        body = response.json()
        cache_set(key, {'body': body, 'fetched': now, 'last_modified': response.headers.get('Last-Modified')}, ttl=RAW_TTL)
        return body, now
    except Exception as e:
        logger.error(f'MET Norway forecast failed for {lat},{lon}: {e}')
        if cached and now - cached['fetched'] < STALE_OK_SECONDS:
            return cached['body'], cached['fetched']
        raise ForecastUnavailable(str(e))


def _symbol(data):
    for window in ('next_1_hours', 'next_6_hours', 'next_12_hours'):
        symbol = ((data.get(window) or {}).get('summary') or {}).get('symbol_code')
        if symbol:
            return symbol
    return None


def _kmh(ms):
    return round(ms * 3.6, 1) if isinstance(ms, (int, float)) else None


def _rain_per_hour(data):
    """Millimetres in that hour: the hourly amount where MET gives one, otherwise the 6-hour amount spread evenly (an average)."""
    one = (data.get('next_1_hours') or {}).get('details', {}).get('precipitation_amount')
    if isinstance(one, (int, float)):
        return one
    six = (data.get('next_6_hours') or {}).get('details', {}).get('precipitation_amount')
    return round(six / 6, 2) if isinstance(six, (int, float)) else None


def _daily(rows, tz):
    """Seven days cut at local midnight. Today only covers the hours still to come (MET's series starts now)."""
    by_day = {}
    for row in rows:
        by_day.setdefault(row['local'].date(), []).append(row)
    days = sorted(by_day)[:DAYS]
    out = {'time': [], 'weather_code': [], 'temperature_2m_max': [], 'temperature_2m_min': [], 'precipitation_sum': [],
           'precipitation_probability_max': [], 'wind_gusts_10m_max': [], 'uv_index_max': []}
    for day in days:
        entries = by_day[day]
        temps = [r['data']['instant']['details']['air_temperature'] for r in entries if 'air_temperature' in r['data']['instant']['details']]
        for r in entries:
            six = (r['data'].get('next_6_hours') or {}).get('details', {})
            temps += [v for v in (six.get('air_temperature_max'), six.get('air_temperature_min')) if isinstance(v, (int, float))]
        # Rain: add each non-overlapping window once (hourly amounts first, 6-hour amounts where they are all there is).
        total, covered_until, seen = 0.0, None, False
        for r in entries:
            for window, hours in (('next_1_hours', 1), ('next_6_hours', 6)):
                amount = (r['data'].get(window) or {}).get('details', {}).get('precipitation_amount')
                if isinstance(amount, (int, float)):
                    if covered_until is None or r['utc'] >= covered_until:
                        total += amount
                        covered_until = r['utc'] + timedelta(hours=hours)
                        seen = True
                    break
        uvs = [r['data']['instant']['details']['ultraviolet_index_clear_sky'] for r in entries
               if 'ultraviolet_index_clear_sky' in r['data']['instant']['details']]
        noon = min(entries, key=lambda r: abs(r['local'].hour + r['local'].minute / 60 - 12))
        out['time'].append(day.isoformat())
        out['weather_code'].append(wmo_code(_symbol(noon['data'])))
        out['temperature_2m_max'].append(round(max(temps), 1) if temps else None)
        out['temperature_2m_min'].append(round(min(temps), 1) if temps else None)
        out['precipitation_sum'].append(round(total, 1) if seen else None)
        out['precipitation_probability_max'].append(None)
        out['wind_gusts_10m_max'].append(None)
        out['uv_index_max'].append(round(max(uvs), 1) if uvs else None)
    return out


def build(lat, lon):
    """The forecast for a point in the app's forecast shape, or ForecastUnavailable."""
    body, fetched = _get_raw(lat, lon)
    try:
        props = body['properties']
        series = props['timeseries']
        elevation = (body.get('geometry') or {}).get('coordinates', [None, None, None])[2:3] or [None]
        tzid = zone_at(lat, lon)
        tz = ZoneInfo(tzid) if tzid else timezone.utc
        rows = []
        for item in series:
            utc = datetime.fromisoformat(item['time'].replace('Z', '+00:00'))
            rows.append({'utc': utc, 'local': utc.astimezone(tz), 'data': item['data']})
        first = rows[0]
        details = first['data']['instant']['details']
        offset = first['local'].utcoffset()
    except Exception as e:
        logger.error(f'MET Norway forecast unusable for {lat},{lon}: {e}')
        raise ForecastUnavailable(str(e))

    def iso(row):
        return row['local'].strftime('%Y-%m-%dT%H:%M')

    next_1 = first['data'].get('next_1_hours') or {}
    current = {
        'time': iso(first),
        'temperature_2m': details.get('air_temperature'),
        'apparent_temperature': details.get('apparent_air_temperature'),
        'relative_humidity_2m': details.get('relative_humidity'),
        'precipitation': (next_1.get('details') or {}).get('precipitation_amount'),
        'weather_code': wmo_code(_symbol(first['data'])),
        'wind_speed_10m': _kmh(details.get('wind_speed')),
        'wind_gusts_10m': None,
        'wind_direction_10m': details.get('wind_from_direction'),
        'pressure_msl': details.get('air_pressure_at_sea_level'),
        'cloud_cover': details.get('cloud_area_fraction'),
        'visibility': None,
    }
    hourly = {'time': [], 'temperature_2m': [], 'precipitation_probability': [], 'precipitation': [], 'wind_speed_10m': [],
              'wind_gusts_10m': [], 'weather_code': []}
    for row in rows:
        d = row['data']['instant']['details']
        hourly['time'].append(iso(row))
        hourly['temperature_2m'].append(d.get('air_temperature'))
        hourly['precipitation_probability'].append(None)
        hourly['precipitation'].append(_rain_per_hour(row['data']))
        hourly['wind_speed_10m'].append(_kmh(d.get('wind_speed')))
        hourly['wind_gusts_10m'].append(None)
        hourly['weather_code'].append(wmo_code(_symbol(row['data'])))
    return {
        'lat': lat,
        'lon': lon,
        'timezone': tzid or 'UTC',
        'elevation_m': elevation[0],
        'utc_offset_seconds': int(offset.total_seconds()) if offset is not None else 0,
        'current': current,
        'hourly': hourly,
        'daily': _daily(rows, tz),
        # MET Norway publishes no past hours, so there is no "what just happened here" series.
        'recent': {'time': [], 'temperature_2m': [], 'precipitation': []},
        'units': {'current': {}, 'hourly': {}, 'daily': {}},
        'source': 'MET Norway (api.met.no)',
        'attribution': ATTRIBUTION,
        'capabilities': dict(CAPABILITIES),
        'data_updated_at': (props.get('meta') or {}).get('updated_at'),
        'generated_at': datetime.fromtimestamp(fetched, timezone.utc).isoformat(),
    }
