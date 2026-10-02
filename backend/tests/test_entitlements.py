"""Tests for services/entitlements.py — the premium/free decision against the
shared Supabase `subscriptions` table."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from cache import cache_delete
from services import entitlements
from services.entitlements import get_plan, is_premium_subscription


def _iso(delta_days):
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat()


@pytest.fixture()
def user_id():
    uid = str(uuid.uuid4())
    cache_delete(f'plan:{uid}')
    yield uid
    cache_delete(f'plan:{uid}')


class TestIsPremiumSubscription:
    def test_no_row_is_free(self):
        assert is_premium_subscription(None) is False

    @pytest.mark.parametrize('status', ['active', 'trialing', 'ACTIVE'])
    def test_active_statuses_are_premium(self, status):
        assert is_premium_subscription({'status': status, 'current_period_end': _iso(-5)}) is True

    def test_canceled_but_paid_period_still_running_is_premium(self):
        assert is_premium_subscription({'status': 'canceled', 'current_period_end': _iso(10)}) is True

    def test_canceled_and_period_over_is_free(self):
        assert is_premium_subscription({'status': 'canceled', 'current_period_end': _iso(-1)}) is False

    def test_canceled_with_no_period_end_is_free(self):
        assert is_premium_subscription({'status': 'canceled', 'current_period_end': None}) is False

    @pytest.mark.parametrize('status', ['past_due', 'unpaid', 'incomplete', 'incomplete_expired', '', None])
    def test_other_statuses_are_free(self, status):
        assert is_premium_subscription({'status': status, 'current_period_end': _iso(10)}) is False

    def test_zulu_suffix_timestamp_is_parsed(self):
        end = (datetime.now(timezone.utc) + timedelta(days=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
        assert is_premium_subscription({'status': 'canceled', 'current_period_end': end}) is True

    def test_garbage_timestamp_is_free(self):
        assert is_premium_subscription({'status': 'canceled', 'current_period_end': 'not-a-date'}) is False


class TestGetPlan:
    def test_active_subscription_is_premium(self, user_id):
        with patch.object(entitlements, '_fetch_subscription', return_value={'status': 'active'}):
            assert get_plan(user_id) == 'premium'

    def test_no_subscription_is_free(self, user_id):
        with patch.object(entitlements, '_fetch_subscription', return_value=None):
            assert get_plan(user_id) == 'free'

    def test_lookup_failure_fails_closed_and_is_not_cached(self, user_id):
        with patch.object(entitlements, '_fetch_subscription', side_effect=RuntimeError('supabase down')):
            assert get_plan(user_id) == 'free'
        # Recovery is picked up immediately — the failure wasn't cached.
        with patch.object(entitlements, '_fetch_subscription', return_value={'status': 'active'}):
            assert get_plan(user_id) == 'premium'

    def test_result_is_cached(self, user_id):
        with patch.object(entitlements, '_fetch_subscription', return_value={'status': 'active'}) as fetch:
            get_plan(user_id)
            get_plan(user_id)
        assert fetch.call_count == 1

    def test_non_uuid_user_id_fails_closed_without_querying(self):
        with patch.object(entitlements, '_fetch_subscription') as fetch:
            assert get_plan('x" or 1=1') == 'free'
        fetch.assert_not_called()


class TestFetchSubscription:
    def test_unconfigured_raises(self, monkeypatch):
        for var in ('SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'GEOINTEL_PROJECT_ID'):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(RuntimeError):
            entitlements._fetch_subscription(str(uuid.uuid4()))

    def test_filters_on_user_and_geointel_project(self, monkeypatch):
        monkeypatch.setenv('SUPABASE_URL', 'https://proj.supabase.co/')
        monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
        monkeypatch.setenv('GEOINTEL_PROJECT_ID', 'proj-geointel')
        uid = str(uuid.uuid4())
        fake = MagicMock()
        fake.json.return_value = [{'status': 'active'}]
        with patch.object(entitlements.requests, 'get', return_value=fake) as get:
            row = entitlements._fetch_subscription(uid)
        assert row == {'status': 'active'}
        args, kwargs = get.call_args
        assert args[0] == 'https://proj.supabase.co/rest/v1/subscriptions'
        assert kwargs['params']['user_id'] == f'eq.{uid}'
        assert kwargs['params']['project_id'] == 'eq.proj-geointel'
        assert kwargs['headers']['apikey'] == 'service-key'

    def test_empty_result_is_none(self, monkeypatch):
        monkeypatch.setenv('SUPABASE_URL', 'https://proj.supabase.co')
        monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
        monkeypatch.setenv('GEOINTEL_PROJECT_ID', 'proj-geointel')
        fake = MagicMock()
        fake.json.return_value = []
        with patch.object(entitlements.requests, 'get', return_value=fake):
            assert entitlements._fetch_subscription(str(uuid.uuid4())) is None
