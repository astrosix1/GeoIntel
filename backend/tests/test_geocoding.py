"""
Tests for real incident-level geocoding (Phase 5.2 of the compendious-tool
roadmap): NominatimGeocoder and _extract_incident_location in
data_sources.py.

Today's geocoding only matched a curated list of city names against
article text — zero landmark/building-level entries (no UN HQ, White
House, Kremlin), so an article about "the UN General Assembly" that
doesn't separately name a city was silently dropped rather than pinned.
NominatimGeocoder resolves an arbitrary place name to real coordinates
via OpenStreetMap's free API; _extract_incident_location asks Claude for
the single real-world location actually tied to an article's event (AI
primary, falls back to None — and from there to the existing curated
city-match — when no key is configured, matching this app's consistent
AI-primary/static-fallback pattern).
"""
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

import data_sources as ds


@pytest.fixture(autouse=True)
def clean_geocode_cache():
    ds.NominatimGeocoder._cache = {}
    ds.NominatimGeocoder._last_request_at = 0.0
    yield
    ds.NominatimGeocoder._cache = {}
    ds.NominatimGeocoder._last_request_at = 0.0


def _fake_nominatim_response(lat='40.7489', lon='-73.9680', country='United States'):
    return [{
        'lat': lat, 'lon': lon,
        'address': {'country': country},
    }]


def test_geocode_returns_real_coordinates(app_module):
    with patch('data_sources.requests.get') as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200, json=lambda: _fake_nominatim_response(),
        )
        mock_get.return_value.raise_for_status = lambda: None

        result = ds.NominatimGeocoder.geocode('United Nations Headquarters, New York')
        assert result == {'lat': 40.7489, 'lon': -73.968, 'country': 'United States'}
        assert mock_get.call_count == 1


def test_geocode_sends_a_descriptive_user_agent(app_module):
    with patch('data_sources.requests.get') as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: _fake_nominatim_response())
        mock_get.return_value.raise_for_status = lambda: None

        ds.NominatimGeocoder.geocode('The Kremlin')
        headers = mock_get.call_args.kwargs.get('headers', {})
        assert 'User-Agent' in headers
        assert headers['User-Agent']  # non-empty, real identifying string


def test_geocode_no_match_returns_none(app_module):
    with patch('data_sources.requests.get') as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
        mock_get.return_value.raise_for_status = lambda: None

        assert ds.NominatimGeocoder.geocode('Nonexistent Made Up Place Xyzzy') is None


def test_geocode_network_error_returns_none_not_a_crash(app_module):
    with patch('data_sources.requests.get', side_effect=Exception('network down')):
        assert ds.NominatimGeocoder.geocode('Somewhere') is None


def test_geocode_caches_repeated_place_names(app_module):
    with patch('data_sources.requests.get') as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: _fake_nominatim_response())
        mock_get.return_value.raise_for_status = lambda: None

        ds.NominatimGeocoder.geocode('The White House')
        ds.NominatimGeocoder.geocode('The White House')
        ds.NominatimGeocoder.geocode('the white house')  # case-insensitive cache key

        assert mock_get.call_count == 1


def test_geocode_self_throttles_to_one_request_per_second(app_module):
    with patch('data_sources.requests.get') as mock_get, patch('time.sleep') as mock_sleep:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: _fake_nominatim_response())
        mock_get.return_value.raise_for_status = lambda: None

        ds.NominatimGeocoder.geocode('Place A')
        ds.NominatimGeocoder.geocode('Place B')  # different key -> not cached, must throttle

        assert mock_sleep.called


def _fake_ai_message(text):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def test_extract_incident_location_returns_none_without_api_key(app_module):
    # conftest.py sets ANTHROPIC_API_KEY='' for the whole test session —
    # this must be the safe, static-fallback-triggering default, matching
    # every other AI feature in this app.
    assert ds._extract_incident_location('Some article text') is None


def test_extract_incident_location_parses_a_real_location(app_module):
    fake_client = MagicMock()
    fake_client.api_key = 'test-key'
    fake_client.messages.create.return_value = _fake_ai_message('United Nations Headquarters, New York')

    with patch('data_sources._geocode_ai_client', fake_client):
        result = ds._extract_incident_location('The UN General Assembly convened today...')
        assert result == 'United Nations Headquarters, New York'


def test_extract_incident_location_handles_none_response(app_module):
    fake_client = MagicMock()
    fake_client.api_key = 'test-key'
    fake_client.messages.create.return_value = _fake_ai_message('NONE')

    with patch('data_sources._geocode_ai_client', fake_client):
        assert ds._extract_incident_location('A generic policy op-ed with no location.') is None


def test_extract_incident_location_handles_malformed_response_without_crashing(app_module):
    fake_client = MagicMock()
    fake_client.api_key = 'test-key'
    fake_client.messages.create.side_effect = Exception('malformed/empty response')

    with patch('data_sources._geocode_ai_client', fake_client):
        assert ds._extract_incident_location('Some text') is None


def test_extract_crisis_from_article_falls_back_to_location_map_without_api_key(app_module):
    # Zero regression check: with no ANTHROPIC_API_KEY (true in this test
    # environment), the AI+Nominatim path must contribute nothing, and the
    # existing curated city-match must still work exactly as before.
    article = {
        'title': 'Military conflict escalates near Tehran',
        'description': 'Officials reported an armed clash amid rising tension.',
        'source': {'name': 'Test Wire'},
        'publishedAt': '2026-01-01T00:00:00Z',
        'url': 'https://example.com/a',
    }
    with patch('data_sources.requests.get') as mock_get:
        # Nominatim must never even be reached when there's no API key.
        crisis = ds.NewsBasedCrisisDetector._extract_crisis_from_article(article)
        assert mock_get.call_count == 0

    assert crisis is not None
    assert crisis['country'] == 'Iran'
    assert crisis['location_confidence'] == 82
