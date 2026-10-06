"""Point forecast: coordinate handling, caching, provider switch, and the
HTTP endpoint. Open-Meteo is always mocked."""
from unittest.mock import MagicMock, patch

import pytest

from cache import cache_clear_prefix
from extensions import limiter
from services import forecast
from services.forecast import ForecastUnavailable, InvalidCoordinates, check_coordinates, get_forecast


@pytest.fixture(autouse=True)
def clean(app_module, monkeypatch):
    limiter.reset()
    cache_clear_prefix('forecast:')
    monkeypatch.delenv('OPEN_METEO_API_KEY', raising=False)
    yield
    cache_clear_prefix('forecast:')


def _hours(n=72, start_hour=0):
    return [f'2026-10-03T{(start_hour + i) % 24:02d}:00' if i < 24 else f'2026-10-0{4 + (i // 24 - 1)}T{i % 24:02d}:00'
            for i in range(n)]


def _body(lat=29.8, lon=-95.4):
    times = _hours()
    return {
        'latitude': lat, 'longitude': lon, 'timezone': 'America/Chicago', 'elevation': 12.0,
        'current_units': {'temperature_2m': '°C'},
        'current': {'time': '2026-10-03T10:15', 'interval': 900, 'temperature_2m': 26.6,
                    'apparent_temperature': 31.0, 'relative_humidity_2m': 85, 'precipitation': 0.0,
                    'weather_code': 3, 'wind_speed_10m': 11.5, 'wind_gusts_10m': 31.7,
                    'wind_direction_10m': 358, 'pressure_msl': 1013.0, 'cloud_cover': 100,
                    'visibility': 16100.0},
        'hourly_units': {'temperature_2m': '°C'},
        'hourly': {'time': times, 'temperature_2m': list(range(72)),
                   'precipitation_probability': [10] * 72, 'precipitation': [0.0] * 72,
                   'wind_speed_10m': [5.0] * 72, 'wind_gusts_10m': [9.0] * 72, 'weather_code': [3] * 72,
                   'unexpected_extra': [1] * 72},
        'daily_units': {'temperature_2m_max': '°C'},
        'daily': {'time': [f'2026-10-0{d}' for d in range(3, 10)], 'weather_code': [3] * 7,
                  'temperature_2m_max': [30] * 7, 'temperature_2m_min': [20] * 7,
                  'precipitation_sum': [0.0] * 7, 'precipitation_probability_max': [10] * 7,
                  'wind_gusts_10m_max': [35] * 7},
    }


def _ok(body):
    response = MagicMock()
    response.json.return_value = body
    response.raise_for_status.return_value = None
    return response


class TestCheckCoordinates:
    def test_rounds_to_a_tenth_of_a_degree(self):
        assert check_coordinates('29.7604', '-95.3698') == (29.8, -95.4)

    def test_accepts_the_limits(self):
        assert check_coordinates(90, 180) == (90.0, 180.0)
        assert check_coordinates(-90, -180) == (-90.0, -180.0)

    @pytest.mark.parametrize('lat,lon', [(90.5, 0), (-91, 0), (0, 180.1), (0, -181),
                                         ('abc', 0), (0, None), (None, None), ('nan', 0)])
    def test_rejects_bad_input(self, lat, lon):
        with pytest.raises(InvalidCoordinates):
            check_coordinates(lat, lon)

    def test_negative_zero_is_normalised(self):
        lat, lon = check_coordinates(-0.04, -0.04)
        assert str(lat) == '0.0' and str(lon) == '0.0'


class TestGetForecast:
    def test_shapes_and_trims_the_response(self):
        with patch.object(forecast.requests, 'get', return_value=_ok(_body())) as get:
            result = get_forecast(29.76, -95.37)

        params = get.call_args.kwargs['params']
        assert (params['latitude'], params['longitude']) == (29.8, -95.4)
        assert params['timezone'] == 'auto' and params['forecast_days'] == 7
        assert 'apikey' not in params
        assert get.call_args.args[0] == 'https://api.open-meteo.com/v1/forecast'

        assert result['current']['temperature_2m'] == 26.6
        assert result['current']['weather_code'] == 3
        # Starts at the current local hour (10:00) and shows every remaining hour, up to 7 days.
        assert result['hourly']['time'][0] == '2026-10-03T10:00'
        assert len(result['hourly']['time']) == 62      # 72 supplied, 10 already past
        assert len(result['hourly']['temperature_2m']) == 62
        assert result['hourly']['temperature_2m'][0] == 10
        assert 'unexpected_extra' not in result['hourly']
        assert len(result['daily']['time']) == 7
        assert result['units']['daily']['temperature_2m_max'] == '°C'
        assert result['source'] == 'open-meteo.com'

    def test_second_call_is_served_from_cache(self):
        with patch.object(forecast.requests, 'get', return_value=_ok(_body())) as get:
            get_forecast(29.76, -95.37)
            get_forecast(29.8, -95.4)  # same rounded grid point
        assert get.call_count == 1

    def test_different_points_are_cached_separately(self):
        with patch.object(forecast.requests, 'get', return_value=_ok(_body())) as get:
            get_forecast(10, 10)
            get_forecast(11, 11)
        assert get.call_count == 2

    def test_upstream_error_is_unavailable_and_not_cached(self):
        with patch.object(forecast.requests, 'get', side_effect=forecast.requests.ConnectionError('down')):
            with pytest.raises(ForecastUnavailable):
                get_forecast(1, 1)
        with patch.object(forecast.requests, 'get', return_value=_ok(_body())) as get:
            get_forecast(1, 1)
        assert get.call_count == 1

    def test_garbage_response_is_unavailable(self):
        with patch.object(forecast.requests, 'get', return_value=_ok({'unexpected': True})):
            with pytest.raises(ForecastUnavailable):
                get_forecast(2, 2)

    def test_http_error_status_is_unavailable(self):
        bad = _ok({})
        bad.raise_for_status.side_effect = forecast.requests.HTTPError('429')
        with patch.object(forecast.requests, 'get', return_value=bad):
            with pytest.raises(ForecastUnavailable):
                get_forecast(3, 3)

    def test_commercial_key_switches_host_and_adds_apikey(self, monkeypatch):
        monkeypatch.setenv('OPEN_METEO_API_KEY', 'secret-key')
        with patch.object(forecast.requests, 'get', return_value=_ok(_body())) as get:
            get_forecast(4, 4)
        assert get.call_args.args[0] == 'https://customer-api.open-meteo.com/v1/forecast'
        assert get.call_args.kwargs['params']['apikey'] == 'secret-key'

    def test_geocoding_host_follows_the_same_switch(self, monkeypatch):
        assert forecast.provider_url('geocoding') == 'https://geocoding-api.open-meteo.com'
        monkeypatch.setenv('OPEN_METEO_API_KEY', 'k')
        assert forecast.provider_url('geocoding') == 'https://customer-geocoding-api.open-meteo.com'


class TestForecastEndpoint:
    def test_returns_the_forecast(self, client):
        with patch.object(forecast.requests, 'get', return_value=_ok(_body())):
            response = client.get('/api/weather/forecast?lat=29.76&lon=-95.37')
        assert response.status_code == 200
        assert response.get_json()['current']['temperature_2m'] == 26.6

    @pytest.mark.parametrize('query', ['', '?lat=1', '?lat=abc&lon=1', '?lat=95&lon=0', '?lat=0&lon=200'])
    def test_bad_coordinates_are_400(self, client, query):
        with patch.object(forecast.requests, 'get') as get:
            response = client.get(f'/api/weather/forecast{query}')
        assert response.status_code == 400
        get.assert_not_called()

    def test_upstream_failure_is_503(self, client):
        with patch.object(forecast.requests, 'get', side_effect=forecast.requests.Timeout('slow')):
            response = client.get('/api/weather/forecast?lat=5&lon=5')
        assert response.status_code == 503
        assert response.get_json()['error'] == 'forecast_unavailable'

    def test_rate_limited_after_30_requests_a_minute(self, client):
        with patch.object(forecast.requests, 'get', return_value=_ok(_body())):
            codes = [client.get('/api/weather/forecast?lat=6&lon=6').status_code for _ in range(31)]
        assert codes[:30] == [200] * 30
        assert codes[30] == 429
