"""
Tests for GDACSConnector. Live-verified at implementation time that
GDACS's EVENTS4APP GeoJSON feed returns a mix of all disaster types
(EQ/FL/WF/TC/...) regardless of the `eventlist` query param, so filtering
to tropical cyclones (`eventtype == 'TC'`) is done client-side and is what
these tests exercise — same mocking convention as test_rest_countries.py
and test_oec.py (mock requests.get rather than hitting the real network).
"""
from unittest.mock import patch, MagicMock

from data_sources.gdacs import GDACSConnector


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _feature(eventtype, eventid=1, name='Test Event', lon=-111.9, lat=26.2,
             alertlevel='Red', severity=287.0, severitytext='Hurricane', country='Mexico'):
    return {
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
        'properties': {
            'eventtype': eventtype,
            'eventid': eventid,
            'eventname': name,
            'name': f'{name} full',
            'alertlevel': alertlevel,
            'country': country,
            'fromdate': '2026-09-21T03:00:00',
            'todate': '2026-09-29T09:00:00',
            'datemodified': '2026-09-29T14:40:18',
            'severitydata': {'severity': severity, 'severitytext': severitytext, 'severityunit': 'km/h'},
            'url': {'report': 'https://www.gdacs.org/report.aspx?eventid=1'},
        },
    }


@patch('data_sources.gdacs.requests')
def test_fetch_active_storms_keeps_only_weather_hazards(mock_requests):
    """The feed mixes every GDACS type. Weather mode keeps cyclones, floods,
    wildfires and droughts; earthquakes, volcanoes and tsunamis are dropped."""
    mock_requests.get.return_value = _mock_response(200, {
        'type': 'FeatureCollection',
        'features': [
            _feature('EQ', eventid=1),
            _feature('VO', eventid=2),
            _feature('TS', eventid=3),
            _feature('FL', eventid=4),
            _feature('WF', eventid=5),
            _feature('DR', eventid=6),
            _feature('TC', eventid=7, name='POLO-26'),
        ],
    })

    result = GDACSConnector.fetch_active_storms()

    assert [r['event_type'] for r in result] == ['FL', 'WF', 'DR', 'TC']
    cyclone = result[-1]
    assert cyclone['id'] == 7
    assert cyclone['hazard'] == 'Tropical cyclone'
    assert cyclone['name'] == 'POLO-26'
    assert cyclone['lat'] == 26.2
    assert cyclone['lon'] == -111.9
    assert cyclone['alert_level'] == 'Red'
    assert cyclone['severity_kmh'] == 287.0
    assert cyclone['source'] == 'gdacs.org'


@patch('data_sources.gdacs.requests')
def test_fetch_active_storms_carries_hazard_details(mock_requests):
    feature = _feature('WF', eventid=9, severity=5580.0, severitytext='Green impact in 5580 ha')
    feature['properties']['severitydata']['severityunit'] = 'ha'
    feature['properties']['htmldescription'] = 'Green Forest fires in Indonesia.'
    feature['properties']['affectedcountries'] = [{'iso2': 'ID', 'countryname': 'Indonesia'}]
    mock_requests.get.return_value = _mock_response(200, {'type': 'FeatureCollection', 'features': [feature]})

    (wildfire,) = GDACSConnector.fetch_active_storms()

    assert wildfire['hazard'] == 'Wildfire'
    assert wildfire['severity'] == 5580.0
    assert wildfire['severity_unit'] == 'ha'
    assert wildfire['severity_kmh'] is None  # wind speed is only meaningful for cyclones
    assert wildfire['description'] == 'Green Forest fires in Indonesia.'
    assert wildfire['affected_countries'] == ['Indonesia']


@patch('data_sources.gdacs.requests')
def test_fetch_active_storms_returns_empty_list_when_nothing_active(mock_requests):
    """A legitimate real state: no weather hazards right now must come back as
    an empty list, not None and not a fabricated event."""
    mock_requests.get.return_value = _mock_response(200, {
        'type': 'FeatureCollection',
        'features': [_feature('EQ', eventid=1), _feature('VO', eventid=2)],
    })

    assert GDACSConnector.fetch_active_storms() == []


@patch('data_sources.gdacs.requests')
def test_fetch_active_storms_returns_none_on_error_status(mock_requests):
    mock_requests.get.return_value = _mock_response(500, {})
    result = GDACSConnector.fetch_active_storms()
    assert result is None


@patch('data_sources.gdacs.requests')
def test_fetch_active_storms_returns_none_on_exception(mock_requests):
    mock_requests.get.side_effect = Exception('network error')
    result = GDACSConnector.fetch_active_storms()
    assert result is None
