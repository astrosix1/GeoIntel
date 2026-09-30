"""
Tests for services/country_profile.py — the assembly layer combining real
REST Countries/WorldBank demographics, real WorldBank/OEC trade data, and
the AI-or-honest-static narrative. Every external connector is mocked;
uses distinct country codes per test to avoid the module's own 6h cache
colliding across tests.
"""
from unittest.mock import patch

from services import country_profile as cp


@patch('services.country_profile.fetch_wikipedia_image')
@patch('services.country_profile.WorldBankConnector')
@patch('services.country_profile.OECConnector')
@patch('services.country_profile.RestCountriesConnector')
def test_profile_uses_rest_countries_when_available(mock_rc, mock_oec, mock_wb, mock_wiki_image):
    mock_rc.fetch_country.return_value = {
        'name': 'France', 'official_name': 'French Republic', 'capital': 'Paris',
        'region': 'Europe', 'subregion': 'Western Europe', 'population': 67000000,
        'area_km2': 551695.0, 'currencies': [], 'languages': [], 'borders': ['DEU'],
        'flag_svg': None, 'flag_png': None,
    }
    mock_oec.fetch_top_exports.return_value = None
    mock_wb.fetch_latest_indicator.return_value = (None, None)
    mock_wiki_image.return_value = {'src': 'https://upload.wikimedia.org/france.jpg', 'caption': 'France'}

    profile = cp.get_country_profile('FRT1')

    assert profile['demographics']['name'] == 'France'
    assert profile['demographics']['population'] == 67000000
    assert profile['demographics_source'] == 'restcountries.com'
    assert profile['image'] == {'src': 'https://upload.wikimedia.org/france.jpg', 'caption': 'France'}
    mock_wiki_image.assert_called_once_with('France', 'France')


@patch('services.country_profile.fetch_wikipedia_image')
@patch('services.country_profile.WorldBankConnector')
@patch('services.country_profile.OECConnector')
@patch('services.country_profile.RestCountriesConnector')
def test_profile_image_absent_when_wikipedia_has_none(mock_rc, mock_oec, mock_wb, mock_wiki_image):
    mock_rc.fetch_country.return_value = {
        'name': 'Nowhereland', 'official_name': None, 'capital': None, 'region': None,
        'subregion': None, 'population': None, 'area_km2': None, 'currencies': [],
        'languages': [], 'borders': [], 'flag_svg': None, 'flag_png': None,
    }
    mock_oec.fetch_top_exports.return_value = None
    mock_wb.fetch_latest_indicator.return_value = (None, None)
    mock_wiki_image.return_value = None

    profile = cp.get_country_profile('NW5')

    assert profile['image'] is None


@patch('services.country_profile.fetch_wikipedia_image', return_value=None)
@patch('services.country_profile.WorldBankConnector')
@patch('services.country_profile.OECConnector')
@patch('services.country_profile.RestCountriesConnector')
def test_profile_falls_back_to_worldbank_when_rest_countries_unavailable(mock_rc, mock_oec, mock_wb, mock_wiki_image):
    mock_rc.fetch_country.return_value = None
    mock_oec.fetch_top_exports.return_value = None
    mock_wb.fetch_country_meta.return_value = {
        'name': 'Testland', 'capital': 'Test City', 'region': 'Europe & Central Asia',
    }

    def indicator_side_effect(code, indicator, per_page=20):
        return {
            cp._POPULATION_INDICATOR: (5000000, 2023),
            cp._AREA_INDICATOR: (10000.0, 2023),
        }.get(indicator, (None, None))

    mock_wb.fetch_latest_indicator.side_effect = indicator_side_effect

    profile = cp.get_country_profile('TL2')

    assert profile['demographics']['name'] == 'Testland'
    assert profile['demographics']['population'] == 5000000
    assert profile['demographics']['area_km2'] == 10000.0
    assert 'API key' in profile['demographics_source']


@patch('services.country_profile.fetch_wikipedia_image', return_value=None)
@patch('services.country_profile.WorldBankConnector')
@patch('services.country_profile.OECConnector')
@patch('services.country_profile.RestCountriesConnector')
def test_trade_section_honest_when_oec_unavailable(mock_rc, mock_oec, mock_wb, mock_wiki_image):
    mock_rc.fetch_country.return_value = {
        'name': 'X', 'official_name': None, 'capital': None, 'region': None,
        'subregion': None, 'population': None, 'area_km2': None, 'currencies': [],
        'languages': [], 'borders': [], 'flag_svg': None, 'flag_png': None,
    }
    mock_oec.fetch_top_exports.return_value = None

    def indicator_side_effect(code, indicator, per_page=20):
        return {
            cp._GDP_INDICATOR: (2.5e12, 2023),
            cp._EXPORTS_INDICATOR: (30.0, 2023),
            cp._IMPORTS_INDICATOR: (28.0, 2023),
        }.get(indicator, (None, None))

    mock_wb.fetch_latest_indicator.side_effect = indicator_side_effect

    profile = cp.get_country_profile('XY3')
    trade = profile['trade']

    assert trade['top_exports_by_commodity'] is None
    assert trade['top_exports_unavailable_reason'] is not None
    assert 'fabricat' not in trade['top_exports_unavailable_reason'].lower()  # sanity: honest wording
    assert trade['gdp_usd_billions'] == 2500.0
    assert trade['trade_openness_percent_of_gdp'] == 58.0


@patch('services.country_profile.fetch_wikipedia_image', return_value=None)
@patch('services.country_profile.anthropic_client', None)
@patch('services.country_profile.WorldBankConnector')
@patch('services.country_profile.OECConnector')
@patch('services.country_profile.RestCountriesConnector')
def test_narrative_static_fallback_has_no_generated_text_without_api_key(mock_rc, mock_oec, mock_wb, mock_wiki_image):
    mock_rc.fetch_country.return_value = {
        'name': 'X', 'official_name': None, 'capital': None, 'region': None,
        'subregion': None, 'population': None, 'area_km2': None, 'currencies': [],
        'languages': [], 'borders': [], 'flag_svg': None, 'flag_png': None,
    }
    mock_oec.fetch_top_exports.return_value = None
    mock_wb.fetch_latest_indicator.return_value = (None, None)

    profile = cp.get_country_profile('AB4')
    narrative = profile['narrative']

    assert narrative['model'] == 'static-facts-only'
    assert narrative['geography_infrastructure'] is None
    assert narrative['world_contribution'] is None


def test_get_country_profile_empty_code_returns_none():
    assert cp.get_country_profile('') is None
    assert cp.get_country_profile(None) is None
