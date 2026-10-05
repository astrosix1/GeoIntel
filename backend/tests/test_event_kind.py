"""Statement vs physical classification (CAMEO), GDELT/ACLED ingest of it, ACLED's
own precision, and the removal of invented sample events."""
import importlib.util
import os
from unittest.mock import MagicMock, patch

import pytest

import data_sources as ds
from data_sources.gdelt import cameo_kind
from models import Crisis
from tests.test_gdelt import make_row


class TestCameoKind:
    @pytest.mark.parametrize('code', ['100', '101', '110', '112', '120', '128', '130', '138', '160', '163', '172',
                                      '1721', '10', '13'])
    def test_statements(self, code):
        assert cameo_kind(code) == 'statement'

    @pytest.mark.parametrize('code', ['140', '141', '145', '150', '153', '170', '171', '173', '174', '175',
                                      '180', '183', '190', '193', '195', '200', '204', '14', '20'])
    def test_things_that_happened(self, code):
        assert cameo_kind(code) == 'physical'

    def test_sanctions_are_the_one_statement_inside_root_17(self):
        assert cameo_kind('172') == 'statement'
        assert [cameo_kind(c) for c in ('171', '173', '174', '175')] == ['physical'] * 4

    @pytest.mark.parametrize('bad', [None, '', ' ', '1', 'abc', 'x12', 5, '01', '043', '09'])
    def test_missing_malformed_or_outside_the_conflict_roots_is_unknown(self, bad):
        assert cameo_kind(bad) is None

    def test_whitespace_is_ignored(self):
        assert cameo_kind(' 190 ') == 'physical'


def test_the_migration_copy_of_the_rule_agrees_with_the_real_one():
    path = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'versions', 'a5d8c2f1b934_add_event_kind_to_crises.py')
    spec = importlib.util.spec_from_file_location('migration_a5d8', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for code in ['100', '112', '130', '160', '172', '171', '173', '140', '150', '183', '190', '200', '043', '01', '9', '']:
        assert module._kind(code) == cameo_kind(code), code


class TestGdeltIngest:
    @pytest.mark.parametrize('event_code,expected', [('112', 'statement'), ('130', 'statement'), ('172', 'statement'),
                                                     ('173', 'physical'), ('190', 'physical'), ('141', 'physical')])
    def test_parsed_rows_carry_the_kind(self, app_module, event_code, expected):
        crisis = ds.GDELTConnector._parse_row(make_row(event_code=event_code))
        assert crisis['event_kind'] == expected


class TestAcled:
    EVENT = {'data_id': '1', 'event_type': 'Battles', 'actor1': 'A', 'actor2': 'B', 'country': 'Ukraine',
             'latitude': '48.5', 'longitude': '37.9', 'fatalities': '4', 'event_date': '2026-10-01', 'notes': 'n'}

    @pytest.mark.parametrize('precision,confidence', [('1', 92), (1, 92), ('2', 85), ('3', 70), (None, 85), ('', 85), ('x', 85), ('9', 85)])
    def test_location_confidence_comes_from_geo_precision(self, app_module, precision, confidence):
        event = {**self.EVENT, 'geo_precision': precision} if precision is not None else dict(self.EVENT)
        assert ds.ACLEDConnector._parse_event(event)['location_confidence'] == confidence

    def test_acled_events_are_physical_incidents(self, app_module):
        assert ds.ACLEDConnector._parse_event(self.EVENT)['event_kind'] == 'physical'

    def test_the_type_map_uses_acleds_real_event_types(self, app_module):
        assert set(ds.ACLED_TYPE_MAP) == {'Battles', 'Violence against civilians', 'Explosions/Remote violence',
                                          'Protests', 'Riots', 'Strategic developments'}
        assert ds.ACLEDConnector._parse_event(self.EVENT)['type'] == 'conflict'

    def test_unconfigured_acled_returns_nothing_not_invented_events(self, app_module, monkeypatch):
        monkeypatch.delenv('ACLED_EMAIL', raising=False)
        monkeypatch.delenv('ACLED_PASSWORD', raising=False)
        ds._acled_token_cache.update({'access_token': None, 'refresh_token': None, 'expires_at': None})
        assert ds.ACLEDConnector.fetch_recent_events() == []

    def test_a_failed_request_returns_nothing_not_invented_events(self, app_module):
        with patch.object(ds.ACLEDConnector, '_get_access_token', return_value='token'), \
                patch('data_sources.acled.requests.get', side_effect=RuntimeError('down')):
            assert ds.ACLEDConnector.fetch_recent_events() == []

    def test_a_real_response_is_parsed(self, app_module):
        response = MagicMock()
        response.json.return_value = {'data': [{**self.EVENT, 'geo_precision': '1'}]}
        response.raise_for_status = lambda: None
        with patch.object(ds.ACLEDConnector, '_get_access_token', return_value='token'), \
                patch('data_sources.acled.requests.get', return_value=response) as get:
            crises = ds.ACLEDConnector.fetch_recent_events()
        assert [c['id'] for c in crises] == ['acled_1'] and crises[0]['location_confidence'] == 92
        assert 'Battles' in get.call_args.kwargs['params']['event_type']


def test_startup_does_not_seed_invented_events(client, db_session):
    client.get('/api/health')
    assert db_session.query(Crisis).filter(Crisis.source == 'Sample Data').count() == 0


def test_to_dict_exposes_the_kind(db_session):
    db_session.add(Crisis(id='ek-1', type='conflict', title='t', country='X', latitude=1, longitude=1,
                          event_kind='statement'))
    db_session.commit()
    try:
        assert db_session.query(Crisis).filter(Crisis.id == 'ek-1').first().to_dict()['event_kind'] == 'statement'
    finally:
        db_session.query(Crisis).filter(Crisis.id == 'ek-1').delete()
        db_session.commit()
