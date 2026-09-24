"""
HTTP-level checks that the admin gate is actually wired into the routes
(not just correct in isolation — `_check_admin_key()` is covered in depth
by test_admin_auth.py). Also covers the health check and the PATCH
endpoint's field allowlist, which guards against mass-assignment.
"""
from models import Crisis


def test_health_check_ok(client):
    resp = client.get('/api/health')
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'ok'


def test_admin_stats_requires_auth(client):
    resp = client.get('/api/admin/stats')
    assert resp.status_code == 401


def test_admin_sync_requires_auth(client):
    resp = client.post('/api/admin/sync')
    assert resp.status_code == 401


def test_crises_export_is_public(client):
    # GET /api/crises/export used to require the admin key even though it
    # only re-shapes data already public via GET /api/crises — that made it
    # unreachable for the journalists/researchers it's actually meant for
    # (Phase 4). It's public now, protected only by the existing rate limit.
    resp = client.get('/api/crises/export')
    assert resp.status_code == 200


def test_admin_stats_accepts_correct_key(client, monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'test-admin-key')
    resp = client.get('/api/admin/stats', headers={'X-Admin-Key': 'test-admin-key'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'crises_total' in body


def test_patch_crisis_requires_auth(client):
    resp = client.patch('/api/crises/some-id', json={'severity': 99})
    assert resp.status_code == 401


def test_patch_crisis_ignores_fields_outside_allowlist(client, db_session, monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'test-admin-key')
    db_session.add(Crisis(
        id='patch-test-1', type='conflict', title='Original Title',
        country='Testland', latitude=0, longitude=0, severity=40,
    ))
    db_session.commit()

    resp = client.patch(
        '/api/crises/patch-test-1',
        headers={'X-Admin-Key': 'test-admin-key'},
        json={'severity': 85, 'title': 'Hijacked Title', 'id': 'different-id'},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    # severity is in the allowlist -> updated
    assert body['severity'] == 85
    # title/id are not -> untouched, confirming update_crisis's allowed_fields
    # allowlist (not **data) actually blocks mass-assignment
    assert body['title'] == 'Original Title'
    assert body['id'] == 'patch-test-1'
