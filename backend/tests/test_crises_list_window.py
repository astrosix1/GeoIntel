"""HTTP-level checks for the bounded/lean list: `view=map`, `days` window,
ordering and caps, and the edge-cache header. Default (no params) must stay
exactly as before."""
from datetime import datetime, timedelta

import pytest

import blueprints.crises as crises_module
from cache import cache_clear_prefix
from models import Crisis

LEAN_KEYS = {'id', 'title', 'country', 'type', 'severity', 'scope', 'date', 'lat', 'lon', 'source_url',
             'location_confidence'}


@pytest.fixture(autouse=True)
def clean_crises(app_module, client, db_session):
    # The app seeds curated/sample crises on its first request of the whole
    # process; trigger that now so it can't land in the middle of a test.
    client.get('/api/health')
    db_session.query(Crisis).delete()
    db_session.commit()
    cache_clear_prefix('crises:list:')
    yield
    db_session.query(Crisis).delete()
    db_session.commit()
    cache_clear_prefix('crises:list:')


def seed(db_session, id, age_hours=1, severity=50, scope='global', event_kind=None, location_confidence=70):
    db_session.add(Crisis(
        id=id, type='conflict', title=f'Crisis {id}', country='Testland',
        latitude=1.5, longitude=2.5, severity=severity, scope=scope,
        source='GDELT', source_url=f'https://example.com/{id}', is_active=True,
        event_kind=event_kind, location_confidence=location_confidence,
        date_start=datetime.utcnow() - timedelta(hours=age_hours),
        analysis='long analysis text', impact='impact text',
    ))
    db_session.commit()


def ids(resp):
    return [c['id'] for c in resp.get_json()['crises']]


class TestLeanView:
    def test_map_view_returns_only_lean_fields(self, app_module, client, db_session):
        seed(db_session, 'a')
        body = client.get('/api/crises?view=map').get_json()
        assert set(body['crises'][0].keys()) == LEAN_KEYS
        assert body['count'] == 1

    def test_statement_flag_is_present_only_for_statements(self, app_module, client, db_session):
        seed(db_session, 'talk', event_kind='statement', location_confidence=55)
        seed(db_session, 'fight', event_kind='physical', location_confidence=85)
        seed(db_session, 'unknown', event_kind=None)
        rows = {r['id']: r for r in client.get('/api/crises?view=map').get_json()['crises']}
        assert rows['talk']['statement'] is True and rows['talk']['location_confidence'] == 55
        assert 'statement' not in rows['fight'] and rows['fight']['location_confidence'] == 85
        assert 'statement' not in rows['unknown']

    def test_map_view_values_match_the_row(self, app_module, client, db_session):
        seed(db_session, 'a', severity=77, scope='local')
        row = client.get('/api/crises?view=map').get_json()['crises'][0]
        assert (row['id'], row['severity'], row['scope'], row['lat'], row['lon']) == ('a', 77, 'local', 1.5, 2.5)
        assert row['source_url'] == 'https://example.com/a'
        assert row['date'] is not None

    def test_default_view_is_unchanged_and_full(self, app_module, client, db_session):
        seed(db_session, 'a')
        row = client.get('/api/crises').get_json()['crises'][0]
        assert {'analysis', 'impact', 'domains', 'stakeholders'} <= set(row.keys())

    def test_map_view_honors_scope_filter(self, app_module, client, db_session):
        seed(db_session, 'g', scope='global')
        seed(db_session, 'l', scope='local')
        assert ids(client.get('/api/crises?view=map&scope=local')) == ['l']

    def test_map_view_is_edge_cacheable(self, app_module, client, db_session):
        seed(db_session, 'a')
        cc = client.get('/api/crises?view=map').headers['Cache-Control']
        assert 's-maxage=60' in cc and 'public' in cc

    def test_cached_map_view_keeps_the_header(self, app_module, client, db_session):
        seed(db_session, 'a')
        client.get('/api/crises?view=map')
        assert 's-maxage=60' in client.get('/api/crises?view=map').headers['Cache-Control']

    def test_full_view_gets_no_public_cache_header(self, app_module, client, db_session):
        seed(db_session, 'a')
        assert 's-maxage' not in (client.get('/api/crises').headers.get('Cache-Control') or '')


class TestWindow:
    def test_days_filters_by_age(self, app_module, client, db_session):
        seed(db_session, 'new', age_hours=5)
        seed(db_session, 'old', age_hours=24 * 5)
        assert ids(client.get('/api/crises?days=2&view=map')) == ['new']

    def test_no_days_returns_everything(self, app_module, client, db_session):
        seed(db_session, 'new', age_hours=5)
        seed(db_session, 'old', age_hours=24 * 30)
        assert set(ids(client.get('/api/crises?view=map'))) == {'new', 'old'}

    def test_short_window_is_newest_first(self, app_module, client, db_session):
        seed(db_session, 'older', age_hours=30, severity=100)
        seed(db_session, 'newer', age_hours=2, severity=10)
        assert ids(client.get('/api/crises?days=2&view=map')) == ['newer', 'older']

    def test_long_window_is_severity_then_recency(self, app_module, client, db_session):
        seed(db_session, 'low-new', age_hours=1, severity=10)
        seed(db_session, 'high-old', age_hours=100, severity=90)
        seed(db_session, 'high-new', age_hours=2, severity=90)
        assert ids(client.get('/api/crises?days=7&view=map')) == ['high-new', 'high-old', 'low-new']

    def test_long_window_is_capped_keeping_the_highest_severity(self, app_module, client, db_session, monkeypatch):
        monkeypatch.setattr(crises_module, 'LONG_WINDOW_CAP', 2)
        seed(db_session, 'a', severity=10)
        seed(db_session, 'b', severity=90)
        seed(db_session, 'c', severity=50)
        assert ids(client.get('/api/crises?days=7&view=map')) == ['b', 'c']

    def test_short_window_cap_keeps_the_newest(self, app_module, client, db_session, monkeypatch):
        monkeypatch.setattr(crises_module, 'MAX_LIST_LIMIT', 2)
        seed(db_session, 'oldest', age_hours=40)
        seed(db_session, 'mid', age_hours=20)
        seed(db_session, 'newest', age_hours=1)
        assert ids(client.get('/api/crises?days=2&view=map')) == ['newest', 'mid']

    def test_explicit_limit_is_honored_and_ceilinged(self, app_module, client, db_session, monkeypatch):
        monkeypatch.setattr(crises_module, 'MAX_LIST_LIMIT', 3)
        for i in range(5):
            seed(db_session, f'r{i}', severity=50 + i)
        assert len(ids(client.get('/api/crises?view=map&limit=2'))) == 2
        assert len(ids(client.get('/api/crises?view=map&limit=999'))) == 3

    def test_non_integer_days_or_limit_is_a_400(self, app_module, client, db_session):
        assert client.get('/api/crises?days=abc').status_code == 400
        assert client.get('/api/crises?limit=abc').status_code == 400

    def test_inactive_rows_are_never_served(self, app_module, client, db_session):
        seed(db_session, 'live')
        seed(db_session, 'archived')
        db_session.query(Crisis).filter(Crisis.id == 'archived').update({Crisis.is_active: False})
        db_session.commit()
        assert ids(client.get('/api/crises?view=map')) == ['live']
