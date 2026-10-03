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
        logger.error(f"Supabase {method} {table} failed: {e}")
        raise SupabaseUnavailable('request_failed') from e
    except requests.RequestException as e:
        logger.error(f"Supabase {method} {table} failed: {e}")
        raise SupabaseUnavailable('request_failed') from e
    return response
