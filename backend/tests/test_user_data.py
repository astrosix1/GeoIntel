"""Dashboard data: the service layer (against an in-memory fake of the
Supabase REST calls) and the premium-gated /api/me/saved and /api/me/prefs
endpoints."""
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import jwt
import pytest
import requests

from models import Crisis
from services import entitlements, supabase_rest, user_data
from services.user_data import (
    InvalidPrefs, SaveLimitReached, UserDataUnavailable,
    get_prefs, list_saved, normalise_outlets, save_event, set_prefs, unsave_event,
)

SECRET = 'jwt-signing-secret'


class FakeSupabase:
    """Just enough PostgREST for the two dashboard tables."""

    def __init__(self):
        self.tables = {'geointel_saved_events': [], 'geointel_user_prefs': []}
        self.calls = []
        self.fail = False
        self._clock = 0

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        table = url.rsplit('/', 1)[-1]
        self.calls.append((method, table))
        if self.fail:
            raise requests.ConnectionError('supabase down')
        params = params or {}
        rows = self.tables[table]

        def matches(row):
            return all(row.get(k) == v[3:] for k, v in params.items()
                       if k in ('user_id', 'crisis_id') and v.startswith('eq.'))

        def project(row):
            select = params.get('select')
            return {c: row.get(c) for c in select.split(',')} if select else dict(row)

        if method == 'GET':
            found = [r for r in rows if matches(r)]
            if params.get('order') == 'saved_at.desc':
                found.sort(key=lambda r: r['saved_at'], reverse=True)
            if 'limit' in params:
                found = found[:int(params['limit'])]
            data = [project(r) for r in found]
        elif method == 'POST':
            key_fields = ('user_id', 'crisis_id') if table == 'geointel_saved_events' else ('user_id',)
            data = []
            for incoming in json:
                existing = next((r for r in rows if all(r[k] == incoming[k] for k in key_fields)), None)
                if existing:
                    existing.update(incoming)
                    row = existing
                else:
                    self._clock += 1
                    row = dict(incoming)
                    if table == 'geointel_saved_events':
                        row['saved_at'] = f'2026-10-0{1 + self._clock % 9}T00:00:{self._clock:02d}+00:00'
                    rows.append(row)
                data.append(project(row))
            if 'return=representation' not in (headers or {}).get('Prefer', ''):
                data = []
        elif method == 'DELETE':
            self.tables[table] = [r for r in rows if not matches(r)]
            data = []
        else:
            raise AssertionError(method)
        return SimpleNamespace(json=lambda: data, raise_for_status=lambda: None, status_code=200)


@pytest.fixture()
def supabase(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://proj.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
    fake = FakeSupabase()
    with patch.object(supabase_rest.requests, 'request', fake.request):
        yield fake


@pytest.fixture()
def crises(app_module, client, db_session):
    client.get('/api/health')  # let the app's first-request seeding happen now
    ids = []
    for i in range(3):
        cid = f'dash-{uuid.uuid4().hex[:8]}'
        ids.append(cid)
        db_session.add(Crisis(
            id=cid, type='conflict', title=f'Event {i}', country='Testland', latitude=1.5 + i,
            longitude=2.5, severity=60 + i, source='GDELT', source_url=f'https://www.example.com/{i}',
            is_active=True, date_start=datetime(2026, 10, 1, 12, 0, 0),
        ))
    db_session.commit()
    yield ids
    db_session.query(Crisis).filter(Crisis.id.in_(ids)).delete(synchronize_session=False)
    db_session.commit()


def new_user():
    return str(uuid.uuid4())


class TestSavedEvents:
    def test_snapshot_comes_from_our_crisis_row(self, supabase, crises):
        uid = new_user()
        saved = save_event(uid, crises[0])
        assert saved['title'] == 'Event 0'
        assert saved['country'] == 'Testland'
        assert saved['severity'] == 60
        assert saved['lat'] == 1.5 and saved['lon'] == 2.5
        assert saved['source_url'] == 'https://www.example.com/0'
        assert saved['event_date'].startswith('2026-10-01T12:00:00')
        assert supabase.tables['geointel_saved_events'][0]['user_id'] == uid

    def test_saving_twice_is_idempotent(self, supabase, crises):
        uid = new_user()
        save_event(uid, crises[0])
        save_event(uid, crises[0])
        assert len(list_saved(uid)) == 1

    def test_unknown_crisis_returns_none_and_writes_nothing(self, supabase, crises):
        assert save_event(new_user(), 'does-not-exist') is None
        assert ('POST', 'geointel_saved_events') not in supabase.calls

    def test_list_is_newest_first_and_only_the_users_own(self, supabase, crises):
        alice, bob = new_user(), new_user()
        save_event(alice, crises[0])
        save_event(alice, crises[1])
        save_event(bob, crises[2])
        assert [s['crisis_id'] for s in list_saved(alice)] == [crises[1], crises[0]]
        assert [s['crisis_id'] for s in list_saved(bob)] == [crises[2]]

    def test_unsave_removes_only_the_users_own_row(self, supabase, crises):
        alice, bob = new_user(), new_user()
        save_event(alice, crises[0])
        save_event(bob, crises[0])
        unsave_event(alice, crises[0])
        assert list_saved(alice) == []
        assert len(list_saved(bob)) == 1

    def test_unsave_with_a_malformed_id_makes_no_request(self, supabase):
        unsave_event(new_user(), 'x,y)&select=*')
        assert supabase.calls == []

    def test_cap_blocks_new_saves_but_allows_resaving(self, supabase, crises, monkeypatch):
        monkeypatch.setattr(user_data, 'MAX_SAVED', 2)
        uid = new_user()
        save_event(uid, crises[0])
        save_event(uid, crises[1])
        with pytest.raises(SaveLimitReached):
            save_event(uid, crises[2])
        assert save_event(uid, crises[0]) is not None

    def test_archived_events_can_still_be_saved(self, supabase, crises, db_session):
        db_session.query(Crisis).filter(Crisis.id == crises[0]).update({Crisis.is_active: False})
        db_session.commit()
        assert save_event(new_user(), crises[0]) is not None


class TestPrefs:
    def test_default_is_empty(self, supabase):
        assert get_prefs(new_user()) == {'hidden_outlets': []}

    def test_set_normalises_dedupes_and_persists(self, supabase):
        uid = new_user()
        saved = set_prefs(uid, ['WWW.BBC.com', 'bbc.com', ' nypost.com ', 'thehindu.com'])
        assert saved == {'hidden_outlets': ['bbc.com', 'nypost.com', 'thehindu.com']}
        assert get_prefs(uid) == saved

    def test_prefs_are_per_user(self, supabase):
        alice, bob = new_user(), new_user()
        set_prefs(alice, ['bbc.com'])
        assert get_prefs(bob) == {'hidden_outlets': []}

    def test_setting_again_replaces(self, supabase):
        uid = new_user()
        set_prefs(uid, ['bbc.com'])
        set_prefs(uid, [])
        assert get_prefs(uid) == {'hidden_outlets': []}

    @pytest.mark.parametrize('bad', ['bbc.com', None, {'a': 1}, [1], ['not a host'], ['localhost'], ['http://bbc.com'], [''], ['a b.com']])
    def test_invalid_input_is_rejected(self, supabase, bad):
        with pytest.raises(InvalidPrefs):
            set_prefs(new_user(), bad)

    def test_too_many_outlets_is_rejected(self, supabase, monkeypatch):
        monkeypatch.setattr(user_data, 'MAX_HIDDEN_OUTLETS', 2)
        with pytest.raises(InvalidPrefs):
            normalise_outlets(['a.com', 'b.com', 'c.com'])


class TestUnavailable:
    def test_unconfigured(self, monkeypatch):
        monkeypatch.delenv('SUPABASE_URL', raising=False)
        monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
        with pytest.raises(UserDataUnavailable) as exc:
            list_saved(new_user())
        assert exc.value.reason == 'not_configured'

    def test_request_failure(self, supabase):
        supabase.fail = True
        with pytest.raises(UserDataUnavailable) as exc:
            get_prefs(new_user())
        assert exc.value.reason == 'request_failed'

    def test_bad_user_id(self, supabase):
        with pytest.raises(UserDataUnavailable):
            list_saved("x' or 1=1")
        assert supabase.calls == []


def _token(uid):
    return jwt.encode({'sub': uid, 'aud': 'authenticated', 'exp': int(time.time()) + 3600}, SECRET, algorithm='HS256')


@pytest.fixture()
def secret(monkeypatch):
    monkeypatch.setenv('SUPABASE_JWT_SECRET', SECRET)


def call(client, method, path, uid=None, plan='active', **kwargs):
    headers = {'Authorization': f'Bearer {_token(uid)}'} if uid else {}
    row = {'status': plan} if plan else None
    with patch.object(entitlements, '_fetch_subscription', return_value=row):
        return getattr(client, method)(path, headers=headers, **kwargs)


ROUTES = [('get', '/api/me/saved'), ('put', '/api/me/saved/x'), ('delete', '/api/me/saved/x'),
          ('get', '/api/me/prefs'), ('put', '/api/me/prefs')]


class TestEndpoints:
    @pytest.mark.parametrize('method,path', ROUTES)
    def test_anonymous_gets_401(self, client, secret, method, path):
        res = call(client, method, path)
        assert res.status_code == 401

    @pytest.mark.parametrize('method,path', ROUTES)
    def test_free_user_gets_403_and_touches_nothing(self, client, secret, supabase, method, path):
        res = call(client, method, path, new_user(), plan=None, json={'hidden_outlets': []})
        assert res.status_code == 403
        assert supabase.calls == []

    def test_save_list_unsave_round_trip(self, client, secret, supabase, crises):
        uid = new_user()
        assert call(client, 'put', f'/api/me/saved/{crises[0]}', uid).status_code == 200
        listed = call(client, 'get', '/api/me/saved', uid).get_json()['saved']
        assert [s['crisis_id'] for s in listed] == [crises[0]]
        assert 'user_id' not in listed[0]
        assert call(client, 'delete', f'/api/me/saved/{crises[0]}', uid).status_code == 204
        assert call(client, 'get', '/api/me/saved', uid).get_json() == {'saved': []}

    def test_users_cannot_see_each_others_saves(self, client, secret, supabase, crises):
        alice, bob = new_user(), new_user()
        call(client, 'put', f'/api/me/saved/{crises[0]}', alice)
        assert call(client, 'get', '/api/me/saved', bob).get_json() == {'saved': []}
        call(client, 'delete', f'/api/me/saved/{crises[0]}', bob)
        assert len(call(client, 'get', '/api/me/saved', alice).get_json()['saved']) == 1

    def test_unknown_crisis_is_404(self, client, secret, supabase, crises):
        assert call(client, 'put', '/api/me/saved/does-not-exist', new_user()).status_code == 404

    def test_save_limit_is_409(self, client, secret, supabase, crises, monkeypatch):
        monkeypatch.setattr(user_data, 'MAX_SAVED', 1)
        uid = new_user()
        call(client, 'put', f'/api/me/saved/{crises[0]}', uid)
        res = call(client, 'put', f'/api/me/saved/{crises[1]}', uid)
        assert res.status_code == 409
        assert res.get_json()['error'] == 'save_limit_reached'

    def test_prefs_round_trip(self, client, secret, supabase):
        uid = new_user()
        res = call(client, 'put', '/api/me/prefs', uid, json={'hidden_outlets': ['WWW.Example.com']})
        assert res.get_json() == {'hidden_outlets': ['example.com']}
        assert call(client, 'get', '/api/me/prefs', uid).get_json() == {'hidden_outlets': ['example.com']}

    @pytest.mark.parametrize('body', [None, {}, {'hidden_outlets': 'bbc.com'}, {'hidden_outlets': ['not a host']}, [1, 2]])
    def test_invalid_prefs_body_is_400(self, client, secret, supabase, body):
        res = call(client, 'put', '/api/me/prefs', new_user(), json=body)
        assert res.status_code == 400
        assert res.get_json()['error'] == 'invalid_prefs'

    def test_supabase_down_is_503(self, client, secret, supabase):
        supabase.fail = True
        res = call(client, 'get', '/api/me/saved', new_user())
        assert res.status_code == 503
        assert res.get_json()['error'] == 'user_data_unavailable'

    def test_unconfigured_is_503(self, client, secret, monkeypatch):
        monkeypatch.delenv('SUPABASE_URL', raising=False)
        monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
        res = call(client, 'get', '/api/me/prefs', new_user())
        assert res.status_code == 503
