"""Watchlist places and the alerts raised for them (Supabase tables from
backend/supabase/004_geointel_watchlist.sql).

RLS is on with no policies, so only the service-role key used here can touch
the tables. Every function takes the *verified* user id and scopes every query
by it. Premium is enforced by the caller (@require_premium), not here.
"""
import math
import re
from datetime import datetime, timezone

from services.place_alert_prefs import InvalidPlaceAlertPrefs, clean_prefs, stored_prefs
from services.condition_alerts import InvalidConditions, clean_conditions, stored_conditions, unavailable_conditions
from services.geo import distance_km
from services.supabase_rest import SupabaseConflict, SupabaseUnavailable, check_uuid, rest

MAX_PLACES = 25
NAME_MAX = 80
RADIUS_MIN_KM = 10
RADIUS_MAX_KM = 2000
ALERT_PAGE = 50
MAX_READ_IDS = 200

_PLACE_COLUMNS = 'id,name,lat,lon,radius_km,created_at,alert_prefs'
_PLACE_COLUMNS_OLD = 'id,name,lat,lon,radius_km,created_at'     # before 007_geointel_place_alert_prefs.sql is applied
_ALERT_COLUMNS = 'id,place_id,hazard_key,hazard_type,title,alert_level,distance_km,created_at,read_at'
_CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f]')


ALERT_LEVELS = ('green', 'orange', 'red')
DEFAULT_ALERT_SETTINGS = {'alert_email': True, 'alert_min_level': 'orange', 'alert_conditions': {}}


class InvalidPlace(ValueError):
    pass


class InvalidAlertSettings(ValueError):
    pass


class PlaceExists(Exception):
    pass


class PlaceLimitReached(Exception):
    pass


def _number(value, label):
    if isinstance(value, bool):
        raise InvalidPlace(f'{label} must be a number')
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise InvalidPlace(f'{label} must be a number')
    if not math.isfinite(number):
        raise InvalidPlace(f'{label} must be a number')
    return number


def clean_place(name, lat, lon, radius_km):
    """A validated {name, lat, lon, radius_km} or InvalidPlace."""
    if not isinstance(name, str):
        raise InvalidPlace('name is required')
    cleaned = ' '.join(_CONTROL_CHARS.sub(' ', name).split())
    if not 1 <= len(cleaned) <= NAME_MAX:
        raise InvalidPlace(f'name must be 1-{NAME_MAX} characters')
    lat, lon, radius = _number(lat, 'lat'), _number(lon, 'lon'), _number(radius_km, 'radius_km')
    if not -90 <= lat <= 90:
        raise InvalidPlace('lat must be between -90 and 90')
    if not -180 <= lon <= 180:
        raise InvalidPlace('lon must be between -180 and 180')
    if radius != int(radius) or not RADIUS_MIN_KM <= radius <= RADIUS_MAX_KM:
        raise InvalidPlace(f'radius_km must be a whole number from {RADIUS_MIN_KM} to {RADIUS_MAX_KM}')
    return {'name': cleaned, 'lat': round(lat, 4) + 0.0, 'lon': round(lon, 4) + 0.0, 'radius_km': int(radius)}


def _with_prefs(rows):
    return [{**r, 'alert_prefs': stored_prefs(r.get('alert_prefs'))} for r in rows]


def list_places(user_id):
    uid = check_uuid(user_id)
    params = {'user_id': f'eq.{uid}', 'order': 'created_at.asc', 'limit': str(MAX_PLACES)}
    try:
        rows = rest('GET', 'geointel_watch_places', params={**params, 'select': _PLACE_COLUMNS}).json()
    except SupabaseUnavailable as e:
        if e.reason != 'column_missing':
            raise
        rows = rest('GET', 'geointel_watch_places', params={**params, 'select': _PLACE_COLUMNS_OLD}).json()   # 007 not applied yet
    return _with_prefs(rows)


def add_place(user_id, name, lat, lon, radius_km, alert_prefs=None):
    """Adds a place (cap MAX_PLACES per user; a duplicate name is refused). Its alert choices are the ones given, else the same
    as the user's most recently added place (so a new place starts like the others), else the defaults. Returns the saved row."""
    uid = check_uuid(user_id)
    place = clean_place(name, lat, lon, radius_km)
    prefs = clean_prefs(alert_prefs)
    existing = list_places(uid)
    if len(existing) >= MAX_PLACES:
        raise PlaceLimitReached()
    if alert_prefs is None and existing:
        prefs = existing[-1].get('alert_prefs') or {}
    row = {**place, 'user_id': uid}
    if prefs:
        row['alert_prefs'] = prefs        # only sent when set, so adding a place works before 007 is applied
    try:
        rows = rest('POST', 'geointel_watch_places', params={'select': _PLACE_COLUMNS if prefs else _PLACE_COLUMNS_OLD},
                    json_body=[row], prefer='return=representation').json()
    except SupabaseConflict:
        raise PlaceExists()
    return _with_prefs(rows)[0]


def update_place_prefs(user_id, place_id, alert_prefs, apply_to_all=False):
    """Saves the alert choices for one of the user's places, or for all of them. Returns the updated place rows."""
    uid = check_uuid(user_id)
    pid = check_uuid(place_id)
    prefs = clean_prefs(alert_prefs)
    params = {'user_id': f'eq.{uid}', 'select': _PLACE_COLUMNS}
    if not apply_to_all:
        params['id'] = f'eq.{pid}'
    rows = rest('PATCH', 'geointel_watch_places', params=params, json_body={'alert_prefs': prefs}, prefer='return=representation').json()
    return _with_prefs(rows)


def delete_place(user_id, place_id):
    """Deletes one of the user's own places (its alerts go with it)."""
    uid = check_uuid(user_id)
    pid = check_uuid(place_id)
    rest('DELETE', 'geointel_watch_places', params={'id': f'eq.{pid}', 'user_id': f'eq.{uid}'})


def nearby_hazards(place, storms):
    """Hazards from the live GDACS list within the place's radius, nearest
    first, each with its distance. Pure; `storms` is get_active_storms()['storms']."""
    found = []
    for storm in storms or []:
        lat, lon = storm.get('lat'), storm.get('lon')
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        distance = distance_km(place['lat'], place['lon'], lat, lon)
        if distance <= place['radius_km']:
            found.append({
                'id': storm.get('id'),
                'event_type': storm.get('event_type'),
                'hazard': storm.get('hazard'),
                'name': storm.get('name'),
                'alert_level': storm.get('alert_level'),
                'distance_km': round(distance, 1),
            })
    return sorted(found, key=lambda h: h['distance_km'])


def list_alerts(user_id, limit=ALERT_PAGE):
    """The user's alerts newest first, each with its place's name."""
    uid = check_uuid(user_id)
    alerts = rest('GET', 'geointel_alerts', params={
        'user_id': f'eq.{uid}', 'select': _ALERT_COLUMNS, 'order': 'created_at.desc', 'limit': str(limit),
    }).json()
    names = {p['id']: p['name'] for p in list_places(uid)}
    return [{**a, 'place_name': names.get(a['place_id'])} for a in alerts]


def unread_count(user_id):
    uid = check_uuid(user_id)
    rows = rest('GET', 'geointel_alerts', params={
        'user_id': f'eq.{uid}', 'read_at': 'is.null', 'select': 'id', 'limit': '100',
    }).json()
    return len(rows)


def mark_alerts_read(user_id, ids=None):
    """Marks the given alert ids (or all, if ids is None) read. Only ever
    touches the user's own alerts."""
    uid = check_uuid(user_id)
    params = {'user_id': f'eq.{uid}', 'read_at': 'is.null'}
    if ids is not None:
        cleaned = [check_uuid(i) for i in ids[:MAX_READ_IDS]]
        if not cleaned:
            return
        params['id'] = f'in.({",".join(cleaned)})'
    rest('PATCH', 'geointel_alerts', params=params,
         json_body={'read_at': datetime.now(timezone.utc).isoformat()})


def get_alert_settings(user_id):
    """{'alert_email': bool, 'alert_min_level': 'green'|'orange'|'red',
    'alert_conditions': {limit key: number}}, defaults when never changed."""
    uid = check_uuid(user_id)
    rows = rest('GET', 'geointel_user_prefs', params={
        'user_id': f'eq.{uid}', 'select': 'alert_email,alert_min_level,alert_conditions', 'limit': '1',
    }).json()
    row = rows[0] if rows else {}
    return {
        'alert_email': row.get('alert_email') if isinstance(row.get('alert_email'), bool)
        else DEFAULT_ALERT_SETTINGS['alert_email'],
        'alert_min_level': row.get('alert_min_level') or DEFAULT_ALERT_SETTINGS['alert_min_level'],
        'alert_conditions': stored_conditions(row.get('alert_conditions')),
        'unavailable_conditions': unavailable_conditions(),
    }


def set_alert_settings(user_id, alert_email=None, alert_min_level=None, alert_conditions=None):
    """Updates only the settings provided (the user's other preferences are
    left alone) and returns the full settings."""
    uid = check_uuid(user_id)
    changes = {}
    if alert_email is not None:
        if not isinstance(alert_email, bool):
            raise InvalidAlertSettings('alert_email must be true or false')
        changes['alert_email'] = alert_email
    if alert_min_level is not None:
        if alert_min_level not in ALERT_LEVELS:
            raise InvalidAlertSettings(f"alert_min_level must be one of {', '.join(ALERT_LEVELS)}")
        changes['alert_min_level'] = alert_min_level
    if alert_conditions is not None:
        try:
            # Merged into what is saved: a key set to null switches that condition off.
            merged = {**get_alert_settings(uid)['alert_conditions'], **{k: v for k, v in alert_conditions.items()}} \
                if isinstance(alert_conditions, dict) else alert_conditions
            changes['alert_conditions'] = clean_conditions(merged)
        except InvalidConditions as e:
            raise InvalidAlertSettings(str(e))
    if not changes:
        raise InvalidAlertSettings('nothing to change')
    rest('POST', 'geointel_user_prefs', params={'on_conflict': 'user_id'},
         json_body=[{'user_id': uid, **changes, 'updated_at': datetime.now(timezone.utc).isoformat()}],
         prefer='resolution=merge-duplicates')
    return get_alert_settings(uid)
