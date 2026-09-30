"""HTTP-level checks for the new /api/countries/<code> endpoint (step 4 of
the rewrite plan). The service layer itself is covered in depth by
test_country_profile.py; this just confirms the blueprint is wired up and
handles bad input / assembly failure sanely."""
from unittest.mock import patch


def test_get_country_profile_route_returns_real_profile(client):
    fake_profile = {
        'country_code': 'FR',
        'demographics': {'name': 'France', 'population': 67000000},
        'demographics_source': 'restcountries.com',
        'trade': {'top_exports_by_commodity': None},
        'narrative': {'model': 'static-facts-only'},
        'generated_at': '2026-01-01T00:00:00',
    }
    with patch('blueprints.countries.get_country_profile', return_value=fake_profile):
        resp = client.get('/api/countries/FR')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['demographics']['name'] == 'France'


def test_get_country_profile_route_404_when_unassemblable(client):
    with patch('blueprints.countries.get_country_profile', return_value=None):
        resp = client.get('/api/countries/ZZ')
    assert resp.status_code == 404


def test_get_country_profile_route_rejects_overlong_code(client):
    resp = client.get('/api/countries/NOTACOUNTRY')
    assert resp.status_code == 400
