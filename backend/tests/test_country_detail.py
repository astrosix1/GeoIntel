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


@patch('services.country_detail.build_conflicts', return_value=None)
@patch('services.country_detail.cache_set')
@patch('services.country_detail.cache_get', return_value=None)
@patch('services.country_detail.WorldBankConnector')
@patch('services.country_detail.FactbookConnector')
def test_detail_adds_estimated_counts_and_migration(mock_fb, mock_wb, _get, _set, _conflicts):
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


@patch('services.country_detail.build_conflicts', return_value=None)
@patch('services.country_detail.cache_set')
@patch('services.country_detail.cache_get', return_value=None)
@patch('services.country_detail.WorldBankConnector')
@patch('services.country_detail.FactbookConnector')
def test_no_population_means_no_estimates_and_nothing_means_none(mock_fb, mock_wb, _get, _set, _conflicts):
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


def _crisis(db_session, **extra):
    import uuid
    from datetime import datetime
    from models import Crisis
    values = dict(id=f'cd-{uuid.uuid4().hex[:8]}', type='conflict', title='Clashes', country='Syria', latitude=35.0, longitude=38.0,
                  severity=60, source='GDELT', is_active=True, event_kind='physical', date_start=datetime.utcnow(), source_count=1)
    values.update(extra)
    db_session.add(Crisis(**values))
    db_session.commit()
    return values['id']


def test_conflicts_count_only_recent_violent_physical_reports_for_the_country(app_module, db_session):
    from datetime import datetime, timedelta
    from cache import cache_delete
    cache_delete('country_conflicts:SY')
    top = _crisis(db_session, severity=90, title='Heavy fighting')
    _crisis(db_session, type='military', severity=40)
    _crisis(db_session, country='syrian arab republic')                       # another spelling of the same country
    _crisis(db_session, event_kind='statement')                               # talk, not violence
    _crisis(db_session, type='diplomatic')                                    # not a violent type
    _crisis(db_session, date_start=datetime.utcnow() - timedelta(days=45))    # too old
    _crisis(db_session, country='Lebanon')                                    # another country
    _crisis(db_session, merged_into=top, is_active=False)                     # merged duplicate

    out = cd.build_conflicts('SY')

    assert out['total'] == 3 and out['last_7_days'] == 3
    assert out['by_type'] == {'conflict': 2, 'military': 1}
    assert out['top_events'][0]['id'] == top
    assert cd.build_conflicts('ZZ') is None
