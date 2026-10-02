"""Premium entitlement lookup against the shared asix.live Supabase
`subscriptions` table (written by the asix.live Stripe webhook). The table is
shared across apps, so every lookup filters on GeoIntel's own project_id."""
import logging
import os
import uuid
from datetime import datetime, timezone

import requests

from cache import cache_get, cache_set

logger = logging.getLogger(__name__)

PLAN_CACHE_TTL = 60
ACTIVE_STATUSES = {'active', 'trialing'}


def _fetch_subscription(user_id):
    """Newest subscriptions row for this user + GeoIntel, or None. Raises on
    any network/HTTP failure so the caller can fail closed."""
    base = os.getenv('SUPABASE_URL', '').rstrip('/')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    project_id = os.getenv('GEOINTEL_PROJECT_ID', '')
    if not (base and key and project_id):
        raise RuntimeError('SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / GEOINTEL_PROJECT_ID not configured')
    response = requests.get(
        f'{base}/rest/v1/subscriptions',
        params={
            'user_id': f'eq.{user_id}',
            'project_id': f'eq.{project_id}',
            'select': 'plan,status,current_period_end,cancel_at_period_end',
            'order': 'current_period_end.desc',
            'limit': '1',
        },
        headers={'apikey': key, 'Authorization': f'Bearer {key}'},
        timeout=5,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def _period_is_current(period_end):
    if not period_end:
        return False
    try:
        end = datetime.fromisoformat(str(period_end).replace('Z', '+00:00'))
    except ValueError:
        return False
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return end > datetime.now(timezone.utc)


def is_premium_subscription(row):
    """Active/trialing is premium. A canceled subscription stays premium
    until the period the user already paid for ends."""
    if not row:
        return False
    status = (row.get('status') or '').lower()
    if status in ACTIVE_STATUSES:
        return True
    if status == 'canceled':
        return _period_is_current(row.get('current_period_end'))
    return False


def get_plan(user_id):
    """'premium' or 'free'. Fails closed to 'free' on any lookup problem
    (not cached, so a recovered Supabase is picked up on the next request)."""
    cache_key = f'plan:{user_id}'
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        uuid.UUID(str(user_id))
        plan = 'premium' if is_premium_subscription(_fetch_subscription(user_id)) else 'free'
    except Exception as e:
        logger.error(f"Entitlement lookup failed for user {user_id}, treating as free: {e}")
        return 'free'
    cache_set(cache_key, plan, ttl=PLAN_CACHE_TTL)
    return plan
