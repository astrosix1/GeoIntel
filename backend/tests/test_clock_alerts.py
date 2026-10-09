"""Clock-change alerts: the next change of a zone within a week, one alert per place and change."""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from services import clock_alerts as ca, supabase_rest
from services.place_alert_prefs import InvalidPlaceAlertPrefs, clean_prefs, clock_enabled
from supabase_fake import FakePostgrest

UTC = timezone.utc


class TestNextChange:
    def test_europe_springs_forward_on_the_last_sunday_of_march(self):
        change = ca.next_change('Europe/Oslo', datetime(2026, 3, 25, 12, 0, tzinfo=UTC))
        assert change['direction'] == 'forward' and change['shift_minutes'] == 60
        assert (change['local_before'], change['local_after'], change['local_date']) == ('01:59', '03:00', '2026-03-29')

    def test_europe_falls_back_in_october(self):
        change = ca.next_change('Europe/Oslo', datetime(2026, 10, 24, 12, 0, tzinfo=UTC))
        assert change['direction'] == 'back' and change['local_date'] == '2026-10-25'

    def test_outside_the_week_there_is_nothing_to_say(self):
        assert ca.next_change('Europe/Oslo', datetime(2026, 3, 1, tzinfo=UTC)) is None
        assert ca.next_change('Asia/Tokyo', datetime(2026, 3, 25, tzinfo=UTC)) is None      # no daylight saving at all

    def test_half_hour_shifts_and_unknown_zones(self):
        change = ca.next_change('Australia/Lord_Howe', datetime(2026, 4, 1, tzinfo=UTC), days=10)
        assert change and change['shift_minutes'] == 30
        assert ca.next_change('Nowhere/Land', datetime(2026, 3, 25, tzinfo=UTC)) is None

    def test_row_text_and_key(self):
        change = ca.next_change('Europe/Oslo', datetime(2026, 3, 25, 12, 0, tzinfo=UTC))
        row = ca.alert_row({'id': 'p1', 'user_id': 'u1', 'name': 'Oslo office'}, change)
        assert row['hazard_key'] == 'CLK-Europe/Oslo-2026-03-29' and row['hazard_type'] == 'CLK'
        assert row['title'].startswith('Clocks go forward 1 hour in Oslo office on Sun 29 Mar')


class TestPrefs:
    def test_off_unless_enabled_and_validated(self):
        assert clock_enabled({}) is False and clock_enabled({'clock': {'enabled': True}}) is True
        assert clean_prefs({'clock': {'enabled': True}}) == {'clock': {'enabled': True}}
        for bad in ({'clock': 'x'}, {'clock': {'enabled': 'yes'}}, {'clock': {'x': 1}}):
            with pytest.raises(InvalidPlaceAlertPrefs):
                clean_prefs(bad)


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://proj.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
    fake = FakePostgrest()
    with patch.object(supabase_rest.requests, 'request', fake.request):
        yield fake


class TestEvaluate:
    NOW = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)

    def place(self, db, prefs, name='Oslo', lat=59.91, lon=10.75):
        row = db.add('geointel_watch_places', user_id=str(uuid.uuid4()), name=name, lat=lat, lon=lon, radius_km=100)
        row['alert_prefs'] = prefs
        return row

    def test_alerts_once_for_a_place_that_asked(self, db):
        place = self.place(db, {'clock': {'enabled': True}})
        self.place(db, {}, name='Silent')
        assert ca.evaluate_clock_changes(self.NOW)['new_alerts'] == 1
        (alert,) = db.tables['geointel_alerts']
        assert alert['place_id'] == place['id'] and alert['hazard_type'] == 'CLK'
        assert ca.evaluate_clock_changes(self.NOW)['new_alerts'] == 0

    def test_no_alert_when_nothing_changes_that_week(self, db):
        self.place(db, {'clock': {'enabled': True}})
        assert ca.evaluate_clock_changes(datetime(2026, 5, 1, tzinfo=UTC))['new_alerts'] == 0

    def test_a_zone_without_daylight_saving_never_alerts(self, db):
        self.place(db, {'clock': {'enabled': True}}, name='Tokyo', lat=35.68, lon=139.69)
        assert ca.evaluate_clock_changes(self.NOW)['new_alerts'] == 0

    def test_missing_prefs_column_is_skipped_quietly(self):
        with patch.object(ca, 'rest', side_effect=supabase_rest.SupabaseUnavailable('column_missing')):
            assert ca.evaluate_clock_changes(self.NOW)['skipped'] == 'no_prefs_column'
