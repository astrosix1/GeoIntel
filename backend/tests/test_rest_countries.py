"""
Tests for RestCountriesConnector. Live-verified at implementation time
that restcountries.com now gates access behind an API key/deprecation
wall for every version tried, so these tests mock requests.get rather
than hitting the real network — same convention as test_gdelt.py.
"""
from unittest.mock import patch, MagicMock

from data_sources.rest_countries import RestCountriesConnector


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


@patch('data_sources.rest_countries.requests')
def test_fetch_country_success(mock_requests):
    mock_requests.get.return_value = _mock_response(200, {
        'name': {'common': 'France', 'official': 'French Republic'},
        'capital': ['Paris'],
        'region': 'Europe',
        'subregion': 'Western Europe',
        'population': 67391582,
        'area': 551695.0,
        'currencies': {'EUR': {'name': 'Euro', 'symbol': '€'}},
        'languages': {'fra': 'French'},
        'borders': ['BEL', 'DEU', 'ESP'],
        'flags': {'svg': 'https://x/flag.svg', 'png': 'https://x/flag.png'},
        'latlng': [46.0, 2.0],
    })

    result = RestCountriesConnector.fetch_country('FR')

    assert result['name'] == 'France'
    assert result['capital'] == 'Paris'
    assert result['population'] == 67391582
    assert result['area_km2'] == 551695.0
    assert result['currencies'] == [{'code': 'EUR', 'name': 'Euro', 'symbol': '€'}]
    assert result['borders'] == ['BEL', 'DEU', 'ESP']
    assert result['source'] == 'restcountries.com'


@patch('data_sources.rest_countries.requests')
def test_fetch_country_returns_none_on_auth_required(mock_requests):
    """Live behavior as of this implementation: api.restcountries.com
    returns 401 authKeyMissing without a configured key. Must return
    None, not a fabricated fallback."""
    mock_requests.get.return_value = _mock_response(401, {
        'errors': [{'message': 'Authorization key required.', 'code': 'authKeyMissing'}]
    })

    result = RestCountriesConnector.fetch_country('FR')
    assert result is None


@patch('data_sources.rest_countries.requests')
def test_fetch_country_returns_none_on_deprecation_error(mock_requests):
    """Live behavior: restcountries.com's legacy host returns success:false
    with a deprecation message body even at HTTP 200 in some cases."""
    mock_requests.get.return_value = _mock_response(200, {
        'success': False,
        'data': None,
        'errors': [{'message': 'This API version has been deprecated.'}],
    })

    result = RestCountriesConnector.fetch_country('FR')
    assert result is None


@patch('data_sources.rest_countries.requests')
def test_fetch_country_returns_none_on_exception(mock_requests):
    mock_requests.get.side_effect = Exception('network error')
    result = RestCountriesConnector.fetch_country('FR')
    assert result is None


def test_fetch_country_handles_missing_code():
    assert RestCountriesConnector.fetch_country('') is None
    assert RestCountriesConnector.fetch_country(None) is None
