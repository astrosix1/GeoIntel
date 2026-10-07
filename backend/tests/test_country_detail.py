"""Premium country detail: Factbook + World Bank population + bundled UN migration table. Connectors are mocked."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask

from blueprints.countries import countries_bp
from data_sources.factbook import parse_profile
from services import country_detail as cd

FIX = Path(__file__).parent / 'fixtures' / 'factbook'


def _fr():
    return parse_profile(json.loads((FIX / 'fr.json').read_text(encoding='utf-8')))


@patch('services.country_detail.cache_set')
@patch('services.country_detail.cache_get', return_value=None)
@patch('services.country_detail.WorldBankConnector')
@patch('services.country_detail.FactbookConnector')
def test_detail_adds_estimated_counts_and_migration(mock_fb, mock_wb, _get, _set):
    mock_fb.fetch_profile.return_value = _fr()
    mock_wb.fetch_latest_indicator.side_effect = lambda cc, ind: (68000000, 2024) if ind == 'SP.POP.TOTL' else (9186757, 2024)

    detail = cd.get_country_detail('fr')

    assert detail['government']['type'] == 'semi-presidential republic'
    catholic = detail['people']['religions']['items'][0]
    assert catholic['name'] == 'Roman Catholic' and catholic['estimated_count'] == round(68000000 * 0.47)
    assert detail['people']['age_structure'][0]['count'] == 11852892  # the Factbook's own count, not an estimate
    mig = detail['migration']
    assert mig['origins'][0]['country_code'] == 'DZ' and mig['origins'][0]['count'] > 1_000_000
    assert mig['migrant_stock'] == 9186757 and mig['share_of_population'] == 13.5
    assert mig['other_count'] > 0
    assert 'CIA World Factbook' in detail['sources']


@patch('services.country_detail.cache_set')
@patch('services.country_detail.cache_get', return_value=None)
@patch('services.country_detail.WorldBankConnector')
@patch('services.country_detail.FactbookConnector')
def test_no_population_means_no_estimates_and_nothing_means_none(mock_fb, mock_wb, _get, _set):
    mock_fb.fetch_profile.return_value = _fr()
    mock_wb.fetch_latest_indicator.return_value = (None, None)
    detail = cd.get_country_detail('FR')
    assert 'estimated_count' not in detail['people']['religions']['items'][0]
    mock_fb.fetch_profile.return_value = None
    assert cd.get_country_detail('ZZ') is None  # not in the bundled migration table either


def test_endpoint_is_premium_only():
    app = Flask(__name__)
    app.register_blueprint(countries_bp)
    with app.test_client() as c:
        assert c.get('/api/countries/FR/detail').status_code == 401
