"""
Tests for OECConnector. Live-verified at implementation time: OEC's
unauthenticated tesseract endpoint responds HTTP 200 but with an empty
`data: []` result set for a real query (France's HS4 export mix), so the
"empty rows -> None, not a fabrication" path is the one that actually
fires in this environment today; both paths are tested here with mocks
(same convention as the other connector tests) so the suite doesn't
depend on OEC's live behavior at test time.
"""
from unittest.mock import patch, MagicMock

from data_sources.oec import OECConnector


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


@patch('data_sources.oec.requests')
def test_fetch_top_exports_success(mock_requests):
    mock_requests.get.return_value = _mock_response(200, {
        'data': [
            {'HS4': '8703', 'Trade Value': 5000000},
            {'HS4': '2710', 'Trade Value': 3000000},
        ]
    })

    result = OECConnector.fetch_top_exports('FR')

    assert result == [
        {'hs4': '8703', 'trade_value_usd': 5000000},
        {'hs4': '2710', 'trade_value_usd': 3000000},
    ]


@patch('data_sources.oec.requests')
def test_fetch_top_exports_returns_none_on_empty_data(mock_requests):
    """Live behavior as of this implementation: 200 OK with an empty
    dataset for the unauthenticated tier. Must return None, never an
    invented commodity list."""
    mock_requests.get.return_value = _mock_response(200, {
        'page': {'total': 0}, 'data': []
    })

    result = OECConnector.fetch_top_exports('FR')
    assert result is None


@patch('data_sources.oec.requests')
def test_fetch_top_exports_returns_none_on_error_status(mock_requests):
    mock_requests.get.return_value = _mock_response(500, {})
    result = OECConnector.fetch_top_exports('FR')
    assert result is None


def test_fetch_top_exports_returns_none_for_unmapped_country():
    """Countries not in the small explicit ISO2->OEC code map are treated
    as unavailable rather than guessed at."""
    result = OECConnector.fetch_top_exports('ZZ')
    assert result is None


@patch('data_sources.oec.requests')
def test_fetch_top_exports_returns_none_on_exception(mock_requests):
    mock_requests.get.side_effect = Exception('network error')
    result = OECConnector.fetch_top_exports('FR')
    assert result is None
