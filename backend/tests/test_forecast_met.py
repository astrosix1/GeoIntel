"""MET Norway forecast provider: shape, local time, daily cut, revalidation, failure, and the pieces around it (zone lookup, Nominatim
place search, the alert limits the source cannot serve). requests is always mocked; the response is a real saved one (Paris)."""
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cache import cache_clear_prefix
from services import condition_alerts, forecast, forecast_met, geocode
from services.forecast_errors import ForecastUnavailable
from services.timezone_lookup import zone_at

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'met_forecast_paris.json').read_text(encoding='utf-8'))


def _resp(body=None, status=200, last_modified='Thu, 08 Oct 2026 19:24:38 GMT'):
    response = MagicMock(status_code=status)
    response.json.return_value = body
    response.headers = {'Last-Modified': last_modified}
    response.raise_for_status.side_effect = None if status < 400 else RuntimeError(str(status))
    return response


@pytest.fixture(autouse=True)
def clean(app_module, monkeypatch):
    monkeypatch.delenv('OPEN_METEO_API_KEY', raising=False)
    cache_clear_prefix('forecast:')
    cache_clear_prefix('met:')
    yield
    cache_clear_prefix('forecast:')
    cache_clear_prefix('met:')


class TestShape:
    def _build(self):
        with patch.object(forecast_met.requests, 'get', return_value=_resp(FIXTURE)):
            return forecast.get_forecast(48.9, 2.4)

    def test_the_default_provider_is_met_norway_and_it_says_so(self):
        out = self._build()
        assert forecast.provider() == 'met-norway'
        assert out['source'].startswith('MET Norway') and out['attribution']['license'].startswith('CC BY 4.0')

    def test_times_are_the_places_local_clock(self):
        out = self._build()
        assert out['timezone'] == 'Europe/Paris' and out['utc_offset_seconds'] == 7200
        assert out['current']['time'] == '2026-10-08T21:00'      # 19:00 UTC
        assert out['hourly']['time'][0] == '2026-10-08T21:00'

    def test_current_conditions_are_converted_and_missing_fields_stay_missing(self):
        c = self._build()['current']
        assert c['temperature_2m'] == 11.0 and c['apparent_temperature'] == 10.0 and c['pressure_msl'] == 1024.9
        assert c['wind_speed_10m'] == round(2.6 * 3.6, 1)          # m/s to km/h
        assert c['weather_code'] == 2                                # partlycloudy_night
        assert c['wind_gusts_10m'] is None and c['visibility'] is None

    def test_steps_after_the_first_days_are_six_hours_apart_and_still_aligned(self):
        h = self._build()['hourly']
        assert len(h['time']) == len(h['temperature_2m']) == len(h['weather_code']) == 92
        assert h['precipitation_probability'][0] is None and h['wind_gusts_10m'][0] is None
        assert all(r is None or r >= 0 for r in h['precipitation'])

    def test_seven_days_cut_at_local_midnight(self):
        d = self._build()['daily']
        assert d['time'][0] == '2026-10-08' and len(d['time']) == 7 and d['time'] == sorted(d['time'])
        for key in ('weather_code', 'temperature_2m_max', 'temperature_2m_min', 'precipitation_sum', 'uv_index_max'):
            assert len(d[key]) == 7
        assert all(hi >= lo for hi, lo in zip(d['temperature_2m_max'], d['temperature_2m_min']))
        assert d['wind_gusts_10m_max'] == [None] * 7 and d['precipitation_probability_max'] == [None] * 7
        assert d['uv_index_max'][0] is not None and d['uv_index_max'][-1] is None   # UV only covers the first days

    def test_rain_totals_count_each_window_once(self):
        out = self._build()
        hours = out['hourly']
        day = out['daily']['time'][1]
        by_hand = sum(r for t, r in zip(hours['time'], hours['precipitation']) if t.startswith(day) and r)
        assert out['daily']['precipitation_sum'][1] == pytest.approx(by_hand, abs=0.15)

    def test_there_is_no_recent_series_and_capabilities_say_what_is_missing(self):
        out = self._build()
        assert out['recent']['time'] == []
        assert out['capabilities']['wind_gusts'] is False and out['capabilities']['precipitation_probability'] is False

    def test_the_result_is_cached(self):
        with patch.object(forecast_met.requests, 'get', return_value=_resp(FIXTURE)) as get:
            forecast.get_forecast(48.9, 2.4)
            forecast.get_forecast(48.9, 2.4)
        assert get.call_count == 1


class TestRequestRules:
    def test_the_app_identifies_itself_and_sends_rounded_coordinates(self):
        with patch.object(forecast_met.requests, 'get', return_value=_resp(FIXTURE)) as get:
            forecast.get_forecast(48.9123, 2.4456)
        assert 'GeoIntel' in get.call_args.kwargs['headers']['User-Agent']
        assert get.call_args.kwargs['params'] == {'lat': 48.9, 'lon': 2.4}

    def test_a_stale_response_is_revalidated_with_if_modified_since(self):
        key = 'met:raw:48.9:2.4'
        from cache import cache_set
        cache_set(key, {'body': FIXTURE, 'fetched': time.time() - 3600, 'last_modified': 'Thu, 08 Oct 2026 19:24:38 GMT'}, ttl=3600)
        with patch.object(forecast_met.requests, 'get', return_value=_resp(None, status=304)) as get:
            out = forecast_met.build(48.9, 2.4)
        assert get.call_args.kwargs['headers']['If-Modified-Since'] == 'Thu, 08 Oct 2026 19:24:38 GMT'
        assert out['current']['temperature_2m'] == 11.0

    def test_when_the_api_is_down_a_recent_response_is_still_shown_with_its_real_age(self):
        from cache import cache_set
        old = time.time() - 3600
        cache_set('met:raw:48.9:2.4', {'body': FIXTURE, 'fetched': old, 'last_modified': None}, ttl=3600)
        with patch.object(forecast_met.requests, 'get', side_effect=RuntimeError('down')):
            out = forecast_met.build(48.9, 2.4)
        assert out['generated_at'].startswith(time.strftime('%Y-%m-%d', time.gmtime(old)))

    def test_with_nothing_to_show_it_is_unavailable(self):
        with patch.object(forecast_met.requests, 'get', side_effect=RuntimeError('down')):
            with pytest.raises(ForecastUnavailable):
                forecast.get_forecast(1, 1)

    def test_a_garbled_response_is_unavailable_not_a_crash(self):
        with patch.object(forecast_met.requests, 'get', return_value=_resp({'properties': {}})):
            with pytest.raises(ForecastUnavailable):
                forecast.get_forecast(2, 2)


class TestSymbols:
    def test_day_and_night_variants_map_to_the_same_wmo_code(self):
        assert forecast_met.wmo_code('clearsky_day') == forecast_met.wmo_code('clearsky_night') == 0
        assert forecast_met.wmo_code('heavyrain') == 65 and forecast_met.wmo_code('lightsnowshowers_day') == 85
        assert forecast_met.wmo_code('rainandthunder') == 95

    def test_an_unknown_symbol_is_none(self):
        assert forecast_met.wmo_code('something_new') is None and forecast_met.wmo_code(None) is None


class TestZones:
    @pytest.mark.parametrize('lat,lon,zone', [(48.9, 2.4, 'Europe/Paris'), (40.7, -74.0, 'America/New_York'), (35.7, 139.7, 'Asia/Tokyo'),
                                              (-33.9, 151.2, 'Australia/Sydney')])
    def test_known_places(self, lat, lon, zone):
        assert zone_at(lat, lon) == zone

    def test_open_sea_and_bad_input_have_no_zone(self):
        assert zone_at(0.0, -30.0) is None and zone_at(95.0, 0.0) is None


class TestPlaceSearch:
    RAW = [{'name': 'Paris', 'lat': '48.85', 'lon': '2.35', 'address': {'country': 'France', 'state': 'Ile-de-France'}},
           {'name': 'Paris', 'lat': '48.85', 'lon': '2.34', 'address': {'country': 'France', 'state': 'Ile-de-France'}},
           {'name': 'Paris', 'lat': '33.66', 'lon': '-95.55', 'address': {'country': 'United States', 'state': 'Texas'}},
           {'lat': 'x', 'lon': '1', 'address': {}}]

    def test_results_are_mapped_deduplicated_and_ordered(self):
        from data_sources.geocoding import NominatimGeocoder
        with patch('data_sources.geocoding.requests.get', return_value=_resp(self.RAW)), patch('time.sleep'):
            out = NominatimGeocoder.search('Paris')
        assert [(r['name'], r['admin1'], r['country']) for r in out] == [('Paris', 'Ile-de-France', 'France'), ('Paris', 'Texas', 'United States')]

    def test_without_a_key_the_search_goes_to_nominatim_and_is_cached(self):
        cache_clear_prefix('geocode:')
        with patch('data_sources.geocoding.NominatimGeocoder.search', return_value=[{'name': 'Oslo'}]) as search:
            assert geocode.search_places('Oslo') == [{'name': 'Oslo'}]
            geocode.search_places('oslo')
        assert search.call_count == 1

    def test_a_down_service_is_unavailable(self):
        cache_clear_prefix('geocode:')
        with patch('data_sources.geocoding.NominatimGeocoder.search', side_effect=RuntimeError('down')):
            with pytest.raises(ForecastUnavailable):
                geocode.search_places('Bergen')


class TestAlertLimits:
    def test_gust_alerts_are_not_offered_without_gust_data(self, monkeypatch):
        assert condition_alerts.unavailable_conditions() == ['gust_kmh']
        monkeypatch.setenv('OPEN_METEO_API_KEY', 'k')
        assert condition_alerts.unavailable_conditions() == []

    def test_a_missing_gust_forecast_never_fires_an_alert(self):
        daily = {'time': ['2026-10-09', '2026-10-10'], 'wind_gusts_10m_max': [None, None], 'temperature_2m_max': [41.0, 20.0]}
        found = condition_alerts.breaches({'daily': daily}, {'gust_kmh': 60.0, 'heat_c': 38.0})
        assert [(k, d) for k, d, *_ in found] == [('heat_c', '2026-10-09')]
