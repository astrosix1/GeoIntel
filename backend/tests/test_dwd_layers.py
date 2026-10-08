"""DWD forecast layers: time dimensions and the endpoint (the WMS capabilities are a saved snippet, never fetched)."""
from unittest.mock import MagicMock, patch

import pytest

from cache import cache_clear_prefix
from data_sources import dwd
from extensions import limiter

XML = '''<Layer queryable="1"><Name>Icon_reg025_fd_sl_T2M</Name><Dimension name="time" default="current" units="ISO8601">2026-10-07T06:00:00.000Z/2026-10-07T09:00:00.000Z/PT1H</Dimension></Layer>
<Layer queryable="1"><Name>Icon_reg025_fd_sl_PMSL</Name><Dimension name="time" default="current" units="ISO8601">2026-10-07T06:00:00.000Z,2026-10-07T07:00:00.000Z,2026-10-07T10:00:00.000Z</Dimension></Layer>
<Layer queryable="1"><Name>Icon_reg025_fd_sl_TOTPREC06H</Name></Layer>'''


@pytest.fixture(autouse=True)
def clean(app_module):
    limiter.reset()
    cache_clear_prefix('dwd:')
    yield
    cache_clear_prefix('dwd:')


class TestTimes:
    def test_a_range_is_expanded_on_its_step(self):
        assert dwd.parse_times('2026-10-07T06:00:00.000Z/2026-10-07T09:00:00.000Z/PT1H') == [
            '2026-10-07T06:00:00Z', '2026-10-07T07:00:00Z', '2026-10-07T08:00:00Z', '2026-10-07T09:00:00Z']
        assert len(dwd.parse_times('2026-10-07T12:00:00.000Z/2026-10-08T00:00:00.000Z/PT3H')) == 5

    def test_a_list_is_kept_sorted_and_without_repeats(self):
        assert dwd.parse_times('2026-10-07T10:00:00Z,2026-10-07T06:00:00Z,2026-10-07T06:00:00Z') == ['2026-10-07T06:00:00Z', '2026-10-07T10:00:00Z']

    def test_minute_steps_and_a_range_of_days_keep_the_newest_times(self):
        times = dwd.parse_times('2026-10-05T00:00:00.000Z/2026-10-08T22:30:00.000Z/PT5M')
        assert len(times) == dwd.MAX_TIMES and times[-1] == '2026-10-08T22:30:00Z'
        assert times[-2] == '2026-10-08T22:25:00Z'

    def test_nonsense_is_empty(self):
        assert dwd.parse_times('') == dwd.parse_times(None) == dwd.parse_times('soon') == dwd.parse_times('a/b/PT1H') == []
        assert dwd.parse_times('2026-10-07T06:00:00Z/2026-10-07T09:00:00Z/P1D') == []


class TestLayers:
    def _get(self, text=XML):
        return MagicMock(status_code=200, text=text, raise_for_status=lambda: None)

    def test_layers_with_times_are_listed_and_those_without_are_left_out(self):
        with patch.object(dwd.requests, 'get', return_value=self._get()):
            out = dwd.layers()
        assert set(out['layers']) == {'temperature', 'pressure'}      # rain has no time dimension here, wind is absent
        assert out['layers']['temperature']['wms_layer'] == 'Icon_reg025_fd_sl_T2M' and len(out['layers']['temperature']['times']) == 4
        assert out['attribution']['license'] == 'CC BY 4.0' and out['attribution']['text'].startswith('Quelle: Deutscher Wetterdienst')

    def test_the_answer_is_remembered(self):
        with patch.object(dwd.requests, 'get', return_value=self._get()) as get:
            dwd.layers()
            dwd.layers()
        assert get.call_count == 1

    def test_an_unreachable_service_or_an_empty_one_is_none(self):
        with patch.object(dwd.requests, 'get', side_effect=RuntimeError('down')):
            assert dwd.layers() is None
        cache_clear_prefix('dwd:')
        with patch.object(dwd.requests, 'get', return_value=self._get('<nothing/>')):
            assert dwd.layers() is None


class TestNoPast:
    def test_only_the_live_hour_and_the_forecast_ahead_are_offered(self):
        from datetime import datetime, timezone
        full = {'layers': {'temperature': {'times': ['2026-10-07T06:00:00Z', '2026-10-08T19:00:00Z', '2026-10-08T20:00:00Z', '2026-10-09T20:00:00Z']},
                           'wind': {'times': ['2026-10-07T06:00:00Z']}}, 'attribution': {}}
        with patch('data_sources.dwd.layers', return_value=full):
            out = dwd.current_layers(datetime(2026, 10, 8, 20, 25, tzinfo=timezone.utc))
        assert out['layers']['temperature']['times'] == ['2026-10-08T20:00:00Z', '2026-10-09T20:00:00Z']   # the hour we are in is live
        assert 'wind' not in out['layers']                                                                 # nothing but the past: not offered
        assert len(full['layers']['temperature']['times']) == 4                                            # the cached copy is untouched

    def test_nothing_left_or_no_service_is_none(self):
        from datetime import datetime, timezone
        with patch('data_sources.dwd.layers', return_value={'layers': {'temperature': {'times': ['2026-10-07T06:00:00Z']}}, 'attribution': {}}):
            assert dwd.current_layers(datetime(2026, 10, 8, 20, 25, tzinfo=timezone.utc)) is None
        with patch('data_sources.dwd.layers', return_value=None):
            assert dwd.current_layers() is None


class TestRadarNowcast:
    def test_the_radar_is_cut_at_the_five_minutes_we_are_in(self):
        from datetime import datetime, timezone
        times = ['2026-10-08T20:00:00Z', '2026-10-08T20:05:00Z', '2026-10-08T20:10:00Z', '2026-10-08T20:15:00Z', '2026-10-08T21:30:00Z']
        full = {'layers': {'radar': {'times': times}}, 'attribution': {}}
        with patch('data_sources.dwd.layers', return_value=full):
            out = dwd.current_layers(datetime(2026, 10, 8, 20, 12, tzinfo=timezone.utc))
        assert out['layers']['radar']['times'] == ['2026-10-08T20:10:00Z', '2026-10-08T20:15:00Z', '2026-10-08T21:30:00Z']

    def test_the_radar_forecast_is_a_known_layer(self):
        assert dwd.LAYERS['radar'][0] == 'Radar_rv_product_1x1km_ger'


class TestEndpoint:
    def test_returns_the_layers_or_503(self, client):
        with patch('data_sources.dwd.current_layers', return_value={'layers': {'temperature': {'times': []}}, 'attribution': {}}):
            assert client.get('/api/weather/layers').get_json()['layers']
        with patch('data_sources.dwd.current_layers', return_value=None):
            assert client.get('/api/weather/layers').status_code == 503
