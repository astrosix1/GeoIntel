"""HTTP-level checks for /api/weather/storms (step 5 of the rewrite plan).
Mocks services.weather.get_active_storms — the connector itself is covered
by test_gdacs.py."""
from unittest.mock import patch


def test_get_storms_route_returns_real_storm_list(client):
    fake_result = {
        'storms': [{'id': 3, 'name': 'POLO-26', 'event_type': 'TC', 'lat': 26.2, 'lon': -111.9}],
        'count': 1,
        'source': 'gdacs.org',
        'generated_at': '2026-09-29T14:40:18',
    }
    with patch('blueprints.weather.get_active_storms', return_value=fake_result):
        resp = client.get('/api/weather/storms')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['count'] == 1
    assert body['storms'][0]['name'] == 'POLO-26'


def test_get_storms_route_returns_empty_list_honestly(client):
    """Zero active storms is a legitimate real state, not an error."""
    fake_result = {'storms': [], 'count': 0, 'source': 'gdacs.org', 'generated_at': '2026-09-29T14:40:18'}
    with patch('blueprints.weather.get_active_storms', return_value=fake_result):
        resp = client.get('/api/weather/storms')

    assert resp.status_code == 200
    assert resp.get_json()['storms'] == []


def test_get_storms_route_503_when_feed_unavailable(client):
    with patch('blueprints.weather.get_active_storms', return_value=None):
        resp = client.get('/api/weather/storms')
    assert resp.status_code == 503
