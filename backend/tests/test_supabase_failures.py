"""Why a Supabase request failed is told apart: a missing table or column is a setup problem, not an outage."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

from services import supabase_rest
from services.supabase_rest import SupabaseUnavailable, _failure_reason, rest


def _response(status, body):
    return SimpleNamespace(status_code=status, json=lambda: body)


@pytest.mark.parametrize('status,body,reason', [
    (404, {'code': 'PGRST205', 'message': "Could not find the table 'public.geointel_watch_places' in the schema cache"}, 'table_missing'),
    (400, {'code': '42P01', 'message': 'relation does not exist'}, 'table_missing'),
    (400, {'code': '42703', 'message': 'column geointel_user_prefs.alert_conditions does not exist'}, 'column_missing'),
    (400, {'code': 'PGRST204', 'message': 'Could not find the column'}, 'column_missing'),
    (500, {'code': 'XX000'}, 'request_failed'),
    (401, {}, 'request_failed'),
])
def test_failure_reason(status, body, reason):
    assert _failure_reason(_response(status, body)) == reason


def test_rest_raises_the_reason(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'k')

    class Resp:
        status_code = 404

        def json(self):
            return {'code': 'PGRST205'}

        def raise_for_status(self):
            raise requests.HTTPError('404', response=self)

    with patch.object(supabase_rest.requests, 'request', return_value=Resp()):
        with pytest.raises(SupabaseUnavailable) as caught:
            rest('GET', 'geointel_watch_places')
    assert caught.value.reason == 'table_missing'
