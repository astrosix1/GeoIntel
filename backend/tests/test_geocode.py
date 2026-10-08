"""Place search for the watchlist (Open-Meteo geocoding, mocked)."""
from unittest.mock import MagicMock, patch

import pytest

from cache import cache_clear_prefix
from services import geocode
from services.forecast import ForecastUnavailable
from services.geocode import InvalidQuery, search_places


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    cache_clear_prefix('geocode:')
    monkeypatch.setenv('OPEN_METEO_API_KEY', 'test-key')  # these tests cover the Open-Meteo path, used only with a commercial key
    yield
    cache_clear_prefix('geocode:')


def _ok(body):
    response = MagicMock()
    response.json.return_value = body
    response.raise_for_status.return_value = None
    return response


HOUSTON = {'name': 'Houston', 'latitude': 29.76, 'longitude': -95.37, 'country': 'United States', 'admin1': 'Texas',
           'population': 2000000}


def test_maps_results_and_drops_extra_fields():
    with patch.object(geocode.requests, 'get', return_value=_ok({'results': [HOUSTON]})) as get:
        results = search_places('  Houston ')
    assert results == [{'name': 'Houston', 'country': 'United States', 'admin1': 'Texas', 'lat': 29.76, 'lon': -95.37}]
    params = get.call_args.kwargs['params']
    assert params['name'] == 'Houston' and params['count'] == 8
    assert get.call_args.args[0] == 'https://customer-geocoding-api.open-meteo.com/v1/search'


def test_no_matches_is_an_empty_list():
    with patch.object(geocode.requests, 'get', return_value=_ok({'generationtime_ms': 0.3})):
        assert search_places('zzzzzz') == []


def test_malformed_items_are_skipped():
    body = {'results': [HOUSTON, {'name': 'NoCoords'}, {'latitude': 1, 'longitude': 2}]}
    with patch.object(geocode.requests, 'get', return_value=_ok(body)):
        assert [r['name'] for r in search_places('Hous')] == ['Houston']


@pytest.mark.parametrize('bad', ['', ' ', 'a', 'x' * 81, None])
def test_bad_queries_are_rejected_without_a_request(bad):
    with patch.object(geocode.requests, 'get') as get:
        with pytest.raises(InvalidQuery):
            search_places(bad)
    get.assert_not_called()


def test_repeat_searches_are_cached_case_insensitively():
    with patch.object(geocode.requests, 'get', return_value=_ok({'results': [HOUSTON]})) as get:
        search_places('Houston')
        search_places('houston')
    assert get.call_count == 1


def test_provider_failure_is_unavailable_and_not_cached():
    with patch.object(geocode.requests, 'get', side_effect=geocode.requests.ConnectionError('down')):
        with pytest.raises(ForecastUnavailable):
            search_places('Houston')
    with patch.object(geocode.requests, 'get', return_value=_ok({'results': [HOUSTON]})) as get:
        search_places('Houston')
    assert get.call_count == 1


def test_commercial_key_switches_host(monkeypatch):
    monkeypatch.setenv('OPEN_METEO_API_KEY', 'k')
    with patch.object(geocode.requests, 'get', return_value=_ok({'results': []})) as get:
        search_places('Oslo')
    assert get.call_args.args[0] == 'https://customer-geocoding-api.open-meteo.com/v1/search'
    assert get.call_args.kwargs['params']['apikey'] == 'k'
