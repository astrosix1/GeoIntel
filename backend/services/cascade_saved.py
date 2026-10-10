"""Saved cascade scenarios (Supabase table geointel_cascades, backend/supabase/008_geointel_cascades.sql). A scenario stores the request the
user made and the result they saw, so reopening it shows exactly that even after the data is refreshed. Every function takes the verified
user id and scopes every query by it; premium is enforced by the caller.
"""
import json
import re

from services.supabase_rest import SupabaseConflict, check_uuid, rest

MAX_SAVED = 20
NAME_MAX = 80
MAX_RESULT_BYTES = 400_000
KEPT_IF_TOO_BIG = 150          # effects kept (most exposed first) when a result is too large to store whole
_CONTROL = re.compile(r'[\x00-\x1f\x7f]')
_LIST_COLUMNS = 'id,name,request,created_at'


class InvalidScenario(ValueError):
    pass


class ScenarioLimitReached(Exception):
    pass


def clean_name(name):
    if not isinstance(name, str):
        raise InvalidScenario('name is required')
    cleaned = ' '.join(_CONTROL.sub(' ', name).split())
    if not 1 <= len(cleaned) <= NAME_MAX:
        raise InvalidScenario(f'name must be 1-{NAME_MAX} characters')
    return cleaned


def compact(result):
    """The result as it will be stored: whole when it fits, else with the most exposed effects only (and a flag saying so)."""
    if len(json.dumps(result)) <= MAX_RESULT_BYTES:
        return result
    kept = result['effects'][:KEPT_IF_TOO_BIG]
    return {**result, 'effects': kept, 'truncated': True}


def _summary(row):
    return {'id': row['id'], 'name': row['name'], 'request': row['request'], 'created_at': row['created_at']}


def list_saved(user_id):
    uid = check_uuid(user_id)
    rows = rest('GET', 'geointel_cascades', params={'user_id': f'eq.{uid}', 'select': _LIST_COLUMNS, 'order': 'created_at.desc',
                                                     'limit': str(MAX_SAVED)}).json()
    return [_summary(r) for r in rows]


def save(user_id, name, request, result):
    """Stores a scenario (cap MAX_SAVED per user) and returns its summary."""
    uid = check_uuid(user_id)
    name = clean_name(name)
    existing = rest('GET', 'geointel_cascades', params={'user_id': f'eq.{uid}', 'select': 'id', 'limit': str(MAX_SAVED + 1)}).json()
    if len(existing) >= MAX_SAVED:
        raise ScenarioLimitReached()
    try:
        rows = rest('POST', 'geointel_cascades', params={'select': _LIST_COLUMNS},
                    json_body=[{'user_id': uid, 'name': name, 'request': request, 'result': compact(result)}],
                    prefer='return=representation').json()
    except SupabaseConflict:
        raise InvalidScenario('could not save that scenario')
    return _summary(rows[0])


def get(user_id, scenario_id):
    """The full saved scenario (request and result), or None."""
    uid, sid = check_uuid(user_id), check_uuid(scenario_id)
    rows = rest('GET', 'geointel_cascades', params={'user_id': f'eq.{uid}', 'id': f'eq.{sid}', 'select': 'id,name,request,result,created_at',
                                                     'limit': '1'}).json()
    return rows[0] if rows else None


def delete(user_id, scenario_id):
    uid, sid = check_uuid(user_id), check_uuid(scenario_id)
    rest('DELETE', 'geointel_cascades', params={'id': f'eq.{sid}', 'user_id': f'eq.{uid}'})
