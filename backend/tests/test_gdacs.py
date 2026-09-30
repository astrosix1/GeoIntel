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
def test_fetch_active_storms_filters_to_tropical_cyclones(mock_requests):
    """Live behavior: the feed mixes EQ/FL/TC event types together; only
    TC (tropical cyclone) events should be returned."""
    mock_requests.get.return_value = _mock_response(200, {
        'type': 'FeatureCollection',
        'features': [
            _feature('EQ', eventid=1),
            _feature('FL', eventid=2),
            _feature('TC', eventid=3, name='POLO-26'),
        ],
    })

    result = GDACSConnector.fetch_active_storms()

    assert len(result) == 1
    assert result[0]['id'] == 3
    assert result[0]['event_type'] == 'TC'
    assert result[0]['name'] == 'POLO-26'
    assert result[0]['lat'] == 26.2
    assert result[0]['lon'] == -111.9
    assert result[0]['alert_level'] == 'Red'
    assert result[0]['severity_kmh'] == 287.0
    assert result[0]['source'] == 'gdacs.org'


@patch('data_sources.gdacs.requests')
def test_fetch_active_storms_returns_empty_list_when_no_storms(mock_requests):
    """A legitimate real state — zero active tropical cyclones globally —
    must come back as an empty list, not None and not a fabricated storm."""
    mock_requests.get.return_value = _mock_response(200, {
        'type': 'FeatureCollection',
        'features': [_feature('EQ', eventid=1), _feature('FL', eventid=2)],
    })

    result = GDACSConnector.fetch_active_storms()
    assert result == []


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
