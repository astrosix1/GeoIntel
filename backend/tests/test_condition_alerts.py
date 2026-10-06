"""Forecast-limit alerts: validation, which days breach, alert rows, dedupe, and the evaluator.
Supabase is the in-memory fake; the forecast provider is patched."""
import uuid
from unittest.mock import patch

import pytest

from services import alerts, condition_alerts as ca, supabase_rest
from services.forecast import ForecastUnavailable
from supabase_fake import FakePostgrest


def forecast(**daily):
    base = {'time': ['2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-10'],
            'temperature_2m_max': [30, 30, 30, 30, 30], 'temperature_2m_min': [20] * 5,
            'precipitation_sum': [0] * 5, 'wind_gusts_10m_max': [20] * 5, 'uv_index_max': [3] * 5}
    base.update(daily)
    return {'daily': base}


class TestClean:
    def test_valid_and_off(self):
        assert ca.clean_conditions({'heat_c': 38, 'cold_c': None, 'uv_index': 8.04}) == {'heat_c': 38.0, 'uv_index': 8.0}

    @pytest.mark.parametrize('bad', [{'heat_c': 24.9}, {'heat_c': 55.1}, {'cold_c': 11}, {'rain_mm': 9},
                                     {'gust_kmh': 251}, {'uv_index': 17}, {'x': 1}, {'heat_c': '40'},
                                     {'heat_c': True}, {'heat_c': float('nan')}, None, [], 'x'])
    def test_rejected(self, bad):
        with pytest.raises(ca.InvalidConditions):
            ca.clean_conditions(bad)

    def test_stored_conditions_never_raises(self):
        assert ca.stored_conditions({'heat_c': 38, 'x': 1, 'rain_mm': 'a', 'uv_index': True}) == {'heat_c': 38.0}
        assert ca.stored_conditions(None) == {} and ca.stored_conditions('x') == {}


class TestBreaches:
    def test_each_condition_fires_on_the_right_side_of_its_limit(self):
        f = forecast(temperature_2m_max=[30, 41, 30, 30, 30], temperature_2m_min=[20, 20, -12, 20, 20],
                     precipitation_sum=[0, 0, 0, 90, 0], wind_gusts_10m_max=[20, 20, 20, 20, 120],
                     uv_index_max=[12, 3, 3, 3, 3])
        found = ca.breaches(f, {'heat_c': 38, 'cold_c': -10, 'rain_mm': 80, 'gust_kmh': 100, 'uv_index': 11})
        # days 4 and 5 are outside the three-day window
        assert {(k, d) for k, d, *_ in found} == {('heat_c', '2026-10-07'), ('cold_c', '2026-10-08'),
                                                  ('uv_index', '2026-10-06')}

    def test_a_value_exactly_at_the_limit_counts(self):
        assert ca.breaches(forecast(temperature_2m_max=[38, 30, 30, 30, 30]), {'heat_c': 38})
        assert ca.breaches(forecast(temperature_2m_min=[-10, 20, 20, 20, 20]), {'cold_c': -10})

    def test_missing_fields_and_values_are_ignored(self):
        assert ca.breaches({'daily': {'time': ['2026-10-06']}}, {'heat_c': 30}) == []
        assert ca.breaches(forecast(temperature_2m_max=[None, 30, 30, 30, 30]), {'heat_c': 25}) == [
            ('heat_c', '2026-10-07', 30, 25), ('heat_c', '2026-10-08', 30, 25)]
        assert ca.breaches({}, {'heat_c': 30}) == []


class TestAlertRow:
    def test_text_and_key(self):
        place = {'id': 'p1', 'user_id': 'u1'}
        row = ca.alert_row(place, 'heat_c', '2026-10-07', 41.3, 38.0)
        assert row['hazard_key'] == 'WX-heat_c-2026-10-07' and row['hazard_type'] == 'WX'
        assert row['title'] == 'Heat: forecast high of 41.3°C on Wed 07 Oct (your limit 38°C)'
        assert row['alert_level'] == 'Orange' and row['distance_km'] == 0


class Harness:
    def __init__(self, db):
        self.db = db
        self.forecasts = {}
        self.calls = []

    def user(self, **conditions):
        uid = str(uuid.uuid4())
        self.db.add('geointel_user_prefs', user_id=uid, alert_conditions=conditions)
        return uid

    def place(self, uid, name='Home', lat=29.73, lon=-95.27):
        return self.db.add('geointel_watch_places', user_id=uid, name=name, lat=lat, lon=lon, radius_km=100)

    def get_forecast(self, lat, lon):
        self.calls.append((lat, lon))
        result = self.forecasts.get((lat, lon), forecast())
        if isinstance(result, Exception):
            raise result
        return result

    def alerts(self):
        return self.db.tables['geointel_alerts']


@pytest.fixture()
def h(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://proj.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
    fake = FakePostgrest()
    harness = Harness(fake)
    with patch.object(supabase_rest.requests, 'request', fake.request), \
            patch.object(ca, 'get_forecast', side_effect=harness.get_forecast):
        yield harness


class TestEvaluate:
    def test_breach_creates_one_alert_per_day_and_never_repeats(self, h):
        uid = h.user(heat_c=38)
        place = h.place(uid)
        h.forecasts[(29.7, -95.3)] = forecast(temperature_2m_max=[40, 41, 30, 30, 30])
        first = ca.evaluate_conditions()
        assert first['new_alerts'] == 2 and first['users'] == 1 and first['places'] == 1
        assert {a['hazard_key'] for a in h.alerts()} == {'WX-heat_c-2026-10-06', 'WX-heat_c-2026-10-07'}
        assert all(a['place_id'] == place['id'] and a['user_id'] == uid for a in h.alerts())
        assert ca.evaluate_conditions()['new_alerts'] == 0
        assert len(h.alerts()) == 2

    def test_a_later_day_alerts_again(self, h):
        uid = h.user(heat_c=38)
        h.place(uid)
        h.forecasts[(29.7, -95.3)] = forecast(temperature_2m_max=[40, 30, 30, 30, 30])
        ca.evaluate_conditions()
        h.forecasts[(29.7, -95.3)] = forecast(temperature_2m_max=[40, 30, 39, 30, 30])
        assert ca.evaluate_conditions()['new_alerts'] == 1

    def test_users_without_limits_cost_nothing(self, h):
        uid = h.user()
        h.place(uid)
        summary = ca.evaluate_conditions()
        assert summary['users'] == 0 and h.calls == []

    def test_one_forecast_per_grid_cell_shared_between_places_and_users(self, h):
        a, b = h.user(heat_c=30), h.user(cold_c=5)
        h.place(a, 'One', 29.71, -95.26)
        h.place(a, 'Two', 29.74, -95.29)
        h.place(b, 'Three', 29.70, -95.30)
        ca.evaluate_conditions()
        assert h.calls == [(29.7, -95.3)]

    def test_only_each_users_own_limits_apply(self, h):
        hot, mild = h.user(heat_c=38), h.user(heat_c=45)
        h.place(hot, 'A')
        h.place(mild, 'B')
        h.forecasts[(29.7, -95.3)] = forecast(temperature_2m_max=[40, 30, 30, 30, 30])
        ca.evaluate_conditions()
        assert {a['user_id'] for a in h.alerts()} == {hot}

    def test_unavailable_forecast_skips_that_place_only(self, h):
        uid = h.user(heat_c=38)
        h.place(uid, 'Down', 10.0, 10.0)
        h.place(uid, 'Up', 29.73, -95.27)
        h.forecasts[(10.0, 10.0)] = ForecastUnavailable('x')
        h.forecasts[(29.7, -95.3)] = forecast(temperature_2m_max=[40, 30, 30, 30, 30])
        summary = ca.evaluate_conditions()
        assert summary['new_alerts'] == 1 and summary['skipped'] is None

    def test_grid_limit_stops_without_failing(self, h):
        uid = h.user(heat_c=38)
        for i in range(3):
            h.place(uid, f'P{i}', 10.0 + i, 20.0)
        with patch.object(ca, 'MAX_GRIDS_PER_RUN', 2):
            summary = ca.evaluate_conditions()
        assert summary['stopped'] == 'grid_limit' and len(h.calls) == 2

    def test_supabase_down_is_reported_not_raised(self, h):
        with patch.object(ca, 'rest', side_effect=supabase_rest.SupabaseUnavailable('request_failed')):
            assert ca.evaluate_conditions()['skipped'] == 'request_failed'

    def test_unexpected_error_does_not_escape(self, h):
        with patch.object(ca, 'rest', side_effect=RuntimeError('boom')):
            assert ca.evaluate_conditions()['skipped'] == 'error'


def test_forecast_alert_email_reads_as_a_forecast_alert():
    row = {'place_id': 'p', 'hazard_type': 'WX', 'title': 'Heat: forecast high of 41°C on Wed 07 Oct (your limit 38°C)',
           'alert_level': 'Orange', 'distance_km': 0}
    subject, html_body, text = alerts._digest([row], {'p': 'Home'})
    assert 'forecast' in subject and 'is 0 km' not in text and 'at Home' in text and 'at Home' in html_body
