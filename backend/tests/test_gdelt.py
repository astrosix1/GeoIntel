"""
Tests for GDELTConnector (Phase 6 of the compendious-tool roadmap) —
a free, real, no-key alternative/addition to ACLED, added after ACLED's own
myACLED access system turned out to gate real API reads behind a
Research-tier/licensed account. GDELT's raw event export is a fixed
61-column tab-separated file with no header; these tests build minimal
realistic rows (only the columns GDELTConnector actually reads varied per
test) rather than depending on the real network.
"""
from unittest.mock import patch, MagicMock

import pytest

import data_sources as ds
from models import Actor


def make_row(
    global_event_id='1000001',
    actor1_name='UNITED STATES',
    actor2_name='RUSSIA',
    event_code='190',       # root '19' FIGHT
    quad_class='4',
    goldstein='-8.0',
    num_sources='3',
    num_articles='5',
    action_geo_fullname='Kyiv, Kyiv, Ukraine',
    action_geo_lat='50.4501',
    action_geo_long='30.5234',
    date_added='20260924120000',
    source_url='https://example.com/article',
):
    fields = [''] * 61
    fields[0] = global_event_id
    fields[6] = actor1_name
    fields[16] = actor2_name
    fields[26] = event_code
    fields[29] = quad_class
    fields[30] = goldstein
    fields[32] = num_sources
    fields[33] = num_articles
    fields[52] = action_geo_fullname
    fields[56] = action_geo_lat
    fields[57] = action_geo_long
    fields[59] = date_added
    fields[60] = source_url
    return fields


@pytest.fixture(autouse=True)
def clean_actors(db_session):
    db_session.query(Actor).delete()
    db_session.commit()
    ds.NewsBasedCrisisDetector._actor_name_patterns = None
    yield
    db_session.query(Actor).delete()
    db_session.commit()
    ds.NewsBasedCrisisDetector._actor_name_patterns = None


def test_quad_class_1_and_2_are_filtered_out(app_module):
    for qc in ('1', '2'):
        assert ds.GDELTConnector._parse_row(make_row(quad_class=qc)) is None


def test_quad_class_3_and_4_are_kept(app_module):
    for qc in ('3', '4'):
        crisis = ds.GDELTConnector._parse_row(make_row(quad_class=qc))
        assert crisis is not None


def test_known_cameo_root_codes_map_to_real_crisis_types(app_module):
    cases = {
        '140': 'civil_unrest',  # PROTEST
        '150': 'military',      # EXHIBIT FORCE POSTURE
        '180': 'conflict',      # ASSAULT
        '190': 'conflict',      # FIGHT
        '200': 'conflict',      # MASS VIOLENCE
        '100': 'diplomatic',    # DEMAND
    }
    for event_code, expected_type in cases.items():
        crisis = ds.GDELTConnector._parse_row(make_row(event_code=event_code, quad_class='4'))
        assert crisis['type'] == expected_type, event_code


def test_unmapped_cameo_root_code_is_skipped(app_module):
    # Root '99' doesn't exist in the real CAMEO scheme / GDELT_TYPE_MAP.
    assert ds.GDELTConnector._parse_row(make_row(event_code='990', quad_class='4')) is None


def test_severity_derived_from_goldstein_not_a_constant(app_module):
    harsh = ds.GDELTConnector._parse_row(make_row(goldstein='-10.0'))
    mild = ds.GDELTConnector._parse_row(make_row(goldstein='-1.0'))
    assert harsh['severity'] == 100
    assert mild['severity'] == 10
    assert harsh['severity'] > mild['severity']


def test_severity_clamps_to_zero_for_cooperative_goldstein(app_module):
    # Edge case: a QuadClass 3/4 row with an unusually positive Goldstein
    # score must not produce a negative severity.
    crisis = ds.GDELTConnector._parse_row(make_row(goldstein='5.0'))
    assert crisis['severity'] == 0


def test_confidence_derived_from_real_num_sources(app_module):
    low = ds.GDELTConnector._parse_row(make_row(num_sources='1'))
    high = ds.GDELTConnector._parse_row(make_row(num_sources='8'))
    assert high['confidence'] > low['confidence']
    assert 50 <= low['confidence'] <= 95
    assert 50 <= high['confidence'] <= 95


def test_country_parsed_from_last_comma_segment_of_geo_fullname(app_module):
    crisis = ds.GDELTConnector._parse_row(
        make_row(action_geo_fullname='Antananarivo, Antananarivo, Madagascar')
    )
    assert crisis['country'] == 'Madagascar'


def test_country_level_geo_fullname_with_no_comma(app_module):
    crisis = ds.GDELTConnector._parse_row(make_row(action_geo_fullname='Ukraine'))
    assert crisis['country'] == 'Ukraine'


def test_missing_geo_fullname_is_skipped(app_module):
    assert ds.GDELTConnector._parse_row(make_row(action_geo_fullname='')) is None


def test_zero_zero_placeholder_geo_is_skipped(app_module):
    # GDELT's own placeholder for "no real geo resolved" — must not be
    # treated as a real pin at (0, 0).
    crisis = ds.GDELTConnector._parse_row(
        make_row(action_geo_lat='0', action_geo_long='0')
    )
    assert crisis is None


def test_crisis_id_uses_real_global_event_id(app_module):
    crisis = ds.GDELTConnector._parse_row(make_row(global_event_id='987654321'))
    assert crisis['id'] == 'gdelt_987654321'


def test_stakeholders_matched_against_real_actor_roster(app_module, db_session):
    db_session.add_all([
        Actor(id='US', name='United States', category='STATE', latitude=38, longitude=-97),
        Actor(id='RU', name='Russia', category='STATE', latitude=60, longitude=90),
    ])
    db_session.commit()

    crisis = ds.GDELTConnector._parse_row(make_row(actor1_name='UNITED STATES', actor2_name='RUSSIA'))
    assert set(crisis['stakeholders'].split(',')) == {'US', 'RU'}


def test_short_row_is_skipped_not_a_crash(app_module):
    assert ds.GDELTConnector._parse_row(['4']) is None


def test_get_recent_timestamps_derives_correct_real_url_pattern(app_module):
    fake_response = MagicMock()
    fake_response.text = (
        "12345 abc123 http://data.gdeltproject.org/gdeltv2/20260924120000.export.CSV.zip\n"
        "67890 def456 http://data.gdeltproject.org/gdeltv2/20260924120000.mentions.CSV.zip\n"
        "11111 ghi789 http://data.gdeltproject.org/gdeltv2/20260924120000.gkg.csv.zip\n"
    )
    fake_response.raise_for_status = lambda: None

    with patch('data_sources.requests.get', return_value=fake_response) as mock_get:
        timestamps = ds.GDELTConnector._get_recent_timestamps()

    mock_get.assert_called_once_with(ds.GDELT_LASTUPDATE_URL, timeout=10)
    assert timestamps == ['20260924120000', '20260924114500', '20260924113000', '20260924111500']


def test_fetch_event_rows_returns_empty_on_network_failure_not_a_crash(app_module):
    with patch('data_sources.requests.get', side_effect=Exception('network down')):
        assert ds.GDELTConnector._fetch_event_rows('20260924120000') == []


def test_fetch_recent_events_returns_empty_when_lastupdate_fails(app_module):
    with patch('data_sources.requests.get', side_effect=Exception('network down')):
        assert ds.GDELTConnector.fetch_recent_events() == []


def test_fetch_recent_events_dedups_across_overlapping_windows(app_module):
    # The same GlobalEventID appearing in more than one of the 4 fetched
    # files (real overlap since GDELT's windows aren't perfectly disjoint
    # in practice) must only produce one crisis record.
    row = make_row(global_event_id='555')
    with patch.object(ds.GDELTConnector, '_get_recent_timestamps', return_value=['t1', 't2']), \
         patch.object(ds.GDELTConnector, '_fetch_event_rows', return_value=[row]):
        crises = ds.GDELTConnector.fetch_recent_events()

    assert len(crises) == 1
    assert crises[0]['id'] == 'gdelt_555'
