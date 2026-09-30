"""HTTP-level checks for the `?scope=global|local|all` filter on
GET /api/crises (item 10.4 of the Phase 10 plan) — the real Local/Global
news-scope classification GDELTConnector._parse_row now assigns instead of
discarding rows. Default (no `scope` param) must behave exactly as before,
i.e. return both scopes, so existing callers aren't silently affected."""
import pytest

from models import Crisis
from cache import cache_clear_prefix


@pytest.fixture(autouse=True)
def clean_crises(db_session):
    db_session.query(Crisis).delete()
    db_session.commit()
    cache_clear_prefix('crises:list:')
    yield
    db_session.query(Crisis).delete()
    db_session.commit()
    cache_clear_prefix('crises:list:')


def seed(db_session, id, scope, severity=50):
    db_session.add(Crisis(
        id=id, type='conflict', title=f'Crisis {id}', country='Testland',
        latitude=0, longitude=0, severity=severity, scope=scope,
        source='GDELT', is_active=True,
    ))
    db_session.commit()


def test_default_scope_returns_both_local_and_global(app_module, client, db_session):
    seed(db_session, 'g1', 'global')
    seed(db_session, 'l1', 'local')
    resp = client.get('/api/crises')
    assert resp.status_code == 200
    ids = {c['id'] for c in resp.get_json()['crises']}
    assert {'g1', 'l1'} <= ids


def test_scope_global_excludes_local(app_module, client, db_session):
    seed(db_session, 'g2', 'global')
    seed(db_session, 'l2', 'local')
    resp = client.get('/api/crises?scope=global')
    body = resp.get_json()
    ids = {c['id'] for c in body['crises']}
    assert 'g2' in ids
    assert 'l2' not in ids
    assert all(c['scope'] == 'global' for c in body['crises'])


def test_scope_local_excludes_global(app_module, client, db_session):
    seed(db_session, 'g3', 'global')
    seed(db_session, 'l3', 'local')
    resp = client.get('/api/crises?scope=local')
    body = resp.get_json()
    ids = {c['id'] for c in body['crises']}
    assert 'l3' in ids
    assert 'g3' not in ids
    assert all(c['scope'] == 'local' for c in body['crises'])


def test_scope_all_is_equivalent_to_default(app_module, client, db_session):
    seed(db_session, 'g4', 'global')
    seed(db_session, 'l4', 'local')
    resp = client.get('/api/crises?scope=all')
    ids = {c['id'] for c in resp.get_json()['crises']}
    assert {'g4', 'l4'} <= ids


def test_crisis_to_dict_defaults_scope_to_global(app_module, db_session):
    seed(db_session, 'g5', 'global')
    crisis = db_session.query(Crisis).filter(Crisis.id == 'g5').first()
    assert crisis.to_dict()['scope'] == 'global'
