"""Weather-condition alerts for watchlist places: heat, cold, heavy rain, strong gusts, UV.

A user sets a limit per condition (Dashboard > Alerts). Each hour this looks at the
next few days of the forecast for every place of every user who set at least one limit
and records an alert when a limit is forecast to be passed. Alerts go into the same table
as hazard alerts (hazard_type 'WX'), so the existing digest email, unread count and
dedupe all apply: the alert key includes the condition and the date, so one forecast
breach alerts once per place per day, and a later day alerts again.

Only the forecast provider's own daily values are compared; nothing is estimated. A place
whose forecast cannot be fetched is skipped this run and retried next hour.
"""
import logging
import time
from datetime import datetime, timezone

from services.forecast import ForecastUnavailable, get_forecast
from services.place_alert_prefs import weather_limits
from services.supabase_rest import SupabaseUnavailable, rest

logger = logging.getLogger(__name__)

DAYS_AHEAD = 3
MAX_GRIDS_PER_RUN = 400
RUN_TIME_BUDGET_SECONDS = 8 * 60
MAX_PLACES_SCANNED = 5000
USERS_PER_QUERY = 50
INSERT_CHUNK = 200
ALERT_LEVEL = 'Orange'

# key -> (daily forecast field, True when the alert fires at or above the limit, label, unit, min, max)
CONDITIONS = {
    'heat_c': ('temperature_2m_max', True, 'Heat', '°C', 25, 55),
    'cold_c': ('temperature_2m_min', False, 'Cold', '°C', -60, 10),
    'rain_mm': ('precipitation_sum', True, 'Heavy rain', ' mm', 10, 500),
    'gust_kmh': ('wind_gusts_10m_max', True, 'Strong gusts', ' km/h', 50, 250),
    'uv_index': ('uv_index_max', True, 'High UV', '', 6, 16),
}


def unavailable_conditions():
    """Limits the current forecast source cannot check (MET Norway publishes no wind gusts for a global point), so the settings
    screen does not offer them and says why. Empty with the Open-Meteo commercial plan."""
    from services.forecast import provider
    return ['gust_kmh'] if provider() == 'met-norway' else []


class InvalidConditions(ValueError):
    pass


def clean_conditions(value):
    """A validated {key: number} from user input. A key set to null is dropped
    (switched off); an unknown key or an out-of-range number is rejected."""
    if not isinstance(value, dict):
        raise InvalidConditions('alert_conditions must be an object')
    cleaned = {}
    for key, limit in value.items():
        if key not in CONDITIONS:
            raise InvalidConditions(f'unknown condition: {key}')
        if limit is None:
            continue
        if isinstance(limit, bool) or not isinstance(limit, (int, float)) or limit != limit:
            raise InvalidConditions(f'{key} must be a number')
        _, _, _, _, low, high = CONDITIONS[key]
        if not low <= limit <= high:
            raise InvalidConditions(f'{key} must be between {low} and {high}')
        cleaned[key] = round(float(limit), 1)
    return cleaned


def stored_conditions(raw):
    """The conditions saved for a user, quietly ignoring anything invalid (never raises)."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, limit in raw.items():
        if key in CONDITIONS and isinstance(limit, (int, float)) and not isinstance(limit, bool):
            out[key] = float(limit)
    return out


def _fmt(value):
    return f'{value:g}'


def breaches(forecast, conditions):
    """[(condition key, date, forecast value, limit)] for every day in the next DAYS_AHEAD
    whose forecast passes a limit."""
    daily = forecast.get('daily') or {}
    dates = daily.get('time') or []
    found = []
    for key, limit in conditions.items():
        field, above, *_ = CONDITIONS[key]
        values = daily.get(field)
        if not isinstance(values, list):
            continue
        for date, value in list(zip(dates, values))[:DAYS_AHEAD]:
            if not isinstance(value, (int, float)):
                continue
            if (value >= limit) if above else (value <= limit):
                found.append((key, date, value, limit))
    return found


def alert_row(place, key, date, value, limit):
    _, above, label, unit, *_ = CONDITIONS[key]
    day = datetime.strptime(date, '%Y-%m-%d').strftime('%a %d %b')
    what = {'heat_c': 'high', 'cold_c': 'low', 'rain_mm': 'total', 'gust_kmh': 'peak gust', 'uv_index': 'peak UV index'}[key]
    return {
        'user_id': place['user_id'],
        'place_id': place['id'],
        'hazard_key': f'WX-{key}-{date}',
        'hazard_type': 'WX',
        'title': f'{label}: forecast {what} of {_fmt(value)}{unit} on {day} (your limit {_fmt(limit)}{unit})',
        'alert_level': ALERT_LEVEL,
        'distance_km': 0,
    }


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def evaluate_conditions():
    """One pass. Returns a summary and never raises, so the scheduler job stays healthy."""
    summary = {'users': 0, 'places': 0, 'grids': 0, 'new_alerts': 0, 'skipped': None, 'stopped': None}
    try:
        prefs = rest('GET', 'geointel_user_prefs', params={
            'select': 'user_id,alert_conditions', 'limit': str(MAX_PLACES_SCANNED),
        }).json()
        account = {}
        for row in prefs:
            conditions = stored_conditions(row.get('alert_conditions'))
            if conditions:
                account[row['user_id']] = conditions

        # Every place is looked at: a place uses the limits it chose, else its owner's account limits.
        scan = {'order': 'created_at.asc', 'limit': str(MAX_PLACES_SCANNED)}
        try:
            all_places = rest('GET', 'geointel_watch_places', params={**scan, 'select': 'id,user_id,name,lat,lon,alert_prefs'}).json()
        except SupabaseUnavailable as e:
            if e.reason != 'column_missing':
                raise
            all_places = rest('GET', 'geointel_watch_places', params={**scan, 'select': 'id,user_id,name,lat,lon'}).json()   # 007 not applied
        places, wanted = [], {}
        for place in all_places:
            limits = weather_limits(place.get('alert_prefs'), account.get(place['user_id'], {}))
            if limits:
                places.append(place)
                wanted[place['id']] = limits
        summary['users'] = len({p['user_id'] for p in places})
        if not places:
            return summary
        summary['places'] = len(places)

        forecasts, started, rows = {}, time.monotonic(), []
        for place in places:
            grid = (round(place['lat'], 1), round(place['lon'], 1))
            if grid not in forecasts:
                if len(forecasts) >= MAX_GRIDS_PER_RUN:
                    summary['stopped'] = 'grid_limit'
                    continue
                if time.monotonic() - started > RUN_TIME_BUDGET_SECONDS:
                    summary['stopped'] = 'time_budget'
                    continue
                try:
                    forecasts[grid] = get_forecast(*grid)
                except ForecastUnavailable:
                    forecasts[grid] = None
                except Exception as e:
                    logger.warning(f"Condition forecast failed for {grid}: {e}")
                    forecasts[grid] = None
            forecast = forecasts.get(grid)
            if not forecast:
                continue
            for key, date, value, limit in breaches(forecast, wanted[place['id']]):
                rows.append(alert_row(place, key, date, value, limit))
        summary['grids'] = len(forecasts)

        for chunk in _chunks(rows, INSERT_CHUNK):
            inserted = rest('POST', 'geointel_alerts',
                            params={'on_conflict': 'place_id,hazard_key', 'select': 'id'},
                            json_body=chunk,
                            prefer='resolution=ignore-duplicates,return=representation').json()
            summary['new_alerts'] += len(inserted)
    except SupabaseUnavailable as e:
        logger.error(f"Condition alerts skipped: {e.reason}")
        summary['skipped'] = e.reason
    except Exception as e:  # keep the scheduler job alive whatever happens
        logger.error(f"Condition alert evaluation failed: {e}")
        summary['skipped'] = 'error'
    if summary['new_alerts']:
        logger.info(f"Condition alerts: {summary}")
    return summary
