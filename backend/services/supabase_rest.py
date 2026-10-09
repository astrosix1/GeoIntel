"""Minimal PostgREST client for GeoIntel's own Supabase tables, using the
service-role key (server-side only). Shared by the dashboard and comments
features; each caller scopes its queries by the verified user id."""
import logging
import os
import uuid

import requests

logger = logging.getLogger(__name__)


class SupabaseUnavailable(Exception):
    """Supabase isn't configured, or a request to it failed."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class SupabaseConflict(Exception):
    """The write violated a uniqueness constraint (HTTP 409 from PostgREST)."""


# Which SQL file creates which table, for the log line that tells the owner what to run.
_SQL_FILES = {
    'geointel_watch_places': '004_geointel_watchlist.sql',
    'geointel_alerts': '004_geointel_watchlist.sql',
    'geointel_user_prefs': '002_geointel_user_data.sql, then 004 and 005',
    'geointel_saved_events': '002_geointel_user_data.sql',
    'geointel_comments': '003_geointel_comments.sql',
    'geointel_drawings': '006_geointel_drawings.sql',
}


def _failure_reason(response):
    """'table_missing', 'column_missing' or 'request_failed', read from PostgREST's error body."""
    try:
        code = str((response.json() or {}).get('code', ''))
    except (ValueError, AttributeError):
        code = ''
    status = getattr(response, 'status_code', None)
    if code in ('PGRST205', '42P01') or (status == 404 and not code):
        return 'table_missing'
    if code in ('PGRST204', '42703'):
        return 'column_missing'
    return 'request_failed'


def check_uuid(value):
    """The canonical form of a UUID, or SupabaseUnavailable if it isn't one.
    Used on ids interpolated into PostgREST filters."""
    try:
        return str(uuid.UUID(str(value)))
    except ValueError as e:
        raise SupabaseUnavailable('bad_id') from e


def rest(method, table, params=None, json_body=None, prefer=None):
    base = os.getenv('SUPABASE_URL', '').rstrip('/')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if not (base and key):
        raise SupabaseUnavailable('not_configured')
    headers = {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    if prefer:
        headers['Prefer'] = prefer
    try:
        response = requests.request(method, f'{base}/rest/v1/{table}', params=params,
                                    json=json_body, headers=headers, timeout=8)
        response.raise_for_status()
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 409:
            raise SupabaseConflict() from e
        reason = _failure_reason(e.response)
        if reason == 'table_missing':
            logger.error(f"Supabase table '{table}' does not exist: apply the matching SQL file in backend/supabase/ "
                         f"in the Supabase SQL editor ({_SQL_FILES.get(table, 'see backend/supabase/')}). {e}")
        elif reason == 'column_missing':
            logger.error(f"Supabase table '{table}' lacks a column the app reads: apply the newest SQL files in "
                         f"backend/supabase/ (004 and 005 for the watchlist and alert settings). {e}")
        else:
            logger.error(f"Supabase {method} {table} failed: {e}")
        raise SupabaseUnavailable(reason) from e
    except requests.RequestException as e:
        logger.error(f"Supabase {method} {table} failed: {e}")
        raise SupabaseUnavailable('request_failed') from e
    return response


def auth_user_email(user_id):
    """The user's sign-in email, via Supabase's auth admin API (service-role
    key). None if the user has no email; SupabaseUnavailable on any failure."""
    uid = check_uuid(user_id)
    base = os.getenv('SUPABASE_URL', '').rstrip('/')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if not (base and key):
        raise SupabaseUnavailable('not_configured')
    try:
        response = requests.get(f'{base}/auth/v1/admin/users/{uid}',
                                headers={'apikey': key, 'Authorization': f'Bearer {key}'}, timeout=8)
        response.raise_for_status()
        email = (response.json() or {}).get('email')
    except (requests.RequestException, ValueError) as e:
        logger.error(f"Supabase auth user lookup failed: {e}")
        raise SupabaseUnavailable('request_failed') from e
    return email or None
