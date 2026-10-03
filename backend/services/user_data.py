"""Per-user dashboard data in Supabase: saved events and outlet preferences.

The tables (see backend/supabase/002_geointel_user_data.sql) have row level
security enabled with no policies, so only the service-role key used here can
touch them. Every function takes the *verified* user id (from the JWT, via
services/auth.get_current_user) and scopes every query by it. Premium is
enforced by the caller (@require_premium), not here.
"""
import logging
import re
from datetime import datetime, timezone

from models import Session, Crisis
from services.supabase_rest import SupabaseUnavailable, check_uuid, rest

logger = logging.getLogger(__name__)

MAX_SAVED = 500
MAX_HIDDEN_OUTLETS = 1000

_SAVED_COLUMNS = 'crisis_id,title,country,type,severity,lat,lon,source_url,event_date,saved_at'
_CRISIS_ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,60}$')
# A plain hostname: dot-separated labels, alphabetic TLD.
_OUTLET_RE = re.compile(r'^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$')


# Kept under its original name for the dashboard code and its tests.
UserDataUnavailable = SupabaseUnavailable


class SaveLimitReached(Exception):
    pass


class InvalidPrefs(ValueError):
    pass


_check_user_id = check_uuid
_rest = rest


def list_saved(user_id):
    """The user's saved events, newest first."""
    uid = _check_user_id(user_id)
    response = _rest('GET', 'geointel_saved_events', params={
        'user_id': f'eq.{uid}',
        'select': _SAVED_COLUMNS,
        'order': 'saved_at.desc',
        'limit': str(MAX_SAVED),
    })
    return response.json()


def save_event(user_id, crisis_id):
    """Save (or re-save) an event. The snapshot is built here from GeoIntel's
    own crisis row — never from client-sent fields — so it can't be spoofed
    and survives the event being archived. Returns the saved row, or None if
    no such crisis exists. Raises SaveLimitReached past MAX_SAVED."""
    uid = _check_user_id(user_id)
    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            return None
        snapshot = {
            'user_id': uid,
            'crisis_id': crisis.id,
            'title': crisis.title,
            'country': crisis.country,
            'type': crisis.type,
            'severity': crisis.severity,
            'lat': crisis.latitude,
            'lon': crisis.longitude,
            'source_url': crisis.source_url,
            'event_date': crisis.date_start.isoformat() if crisis.date_start else None,
        }
    finally:
        session.close()

    existing = _rest('GET', 'geointel_saved_events', params={
        'user_id': f'eq.{uid}', 'select': 'crisis_id', 'limit': str(MAX_SAVED + 1),
    }).json()
    if crisis_id not in {row['crisis_id'] for row in existing} and len(existing) >= MAX_SAVED:
        raise SaveLimitReached()

    rows = _rest(
        'POST', 'geointel_saved_events',
        params={'on_conflict': 'user_id,crisis_id', 'select': _SAVED_COLUMNS},
        json_body=[snapshot],
        prefer='resolution=merge-duplicates,return=representation',
    ).json()
    return rows[0] if rows else None


def unsave_event(user_id, crisis_id):
    uid = _check_user_id(user_id)
    if not _CRISIS_ID_RE.match(crisis_id or ''):
        return
    _rest('DELETE', 'geointel_saved_events', params={'user_id': f'eq.{uid}', 'crisis_id': f'eq.{crisis_id}'})


def normalise_outlets(value):
    """Clean a list of outlet hostnames: lowercase, strip a leading www.,
    validate as a hostname, de-duplicate (order kept), cap the size. Raises
    InvalidPrefs on any bad input rather than silently dropping entries."""
    if not isinstance(value, list):
        raise InvalidPrefs('hidden_outlets must be a list')
    seen, cleaned = set(), []
    for item in value:
        if not isinstance(item, str):
            raise InvalidPrefs('outlets must be strings')
        host = item.strip().lower().removeprefix('www.')
        if not _OUTLET_RE.match(host):
            raise InvalidPrefs(f'not a valid outlet hostname: {item[:60]!r}')
        if host not in seen:
            seen.add(host)
            cleaned.append(host)
    if len(cleaned) > MAX_HIDDEN_OUTLETS:
        raise InvalidPrefs('too many hidden outlets')
    return cleaned


def get_prefs(user_id):
    uid = _check_user_id(user_id)
    rows = _rest('GET', 'geointel_user_prefs', params={
        'user_id': f'eq.{uid}', 'select': 'hidden_outlets', 'limit': '1',
    }).json()
    return {'hidden_outlets': (rows[0].get('hidden_outlets') or []) if rows else []}


def set_prefs(user_id, hidden_outlets):
    uid = _check_user_id(user_id)
    cleaned = normalise_outlets(hidden_outlets)
    _rest(
        'POST', 'geointel_user_prefs',
        params={'on_conflict': 'user_id'},
        json_body=[{'user_id': uid, 'hidden_outlets': cleaned,
                    'updated_at': datetime.now(timezone.utc).isoformat()}],
        prefer='resolution=merge-duplicates',
    )
    return {'hidden_outlets': cleaned}
