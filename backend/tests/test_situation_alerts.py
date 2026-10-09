"""Situation alerts: a watched place hears about a situation or serious event starting inside its radius."""
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from models import Crisis, Situation
from services import situation_alerts as sa, supabase_rest
from services.place_alert_prefs import InvalidPlaceAlertPrefs, clean_prefs, situation_settings
from supabase_fake import FakePostgrest

HOUSTON = (29.73, -95.27)
ON = {'situations': {'enabled': True}}


@pytest.fixture()
def h(app_module, db_session, monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://proj.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
    for model in (Situation, Crisis):
        db_session.query(model).delete()
    db_session.commit()
    fake = FakePostgrest()
    with patch.object(supabase_rest.requests, 'request', fake.request):
        yield SimpleHarness(fake, db_session)
    for model in (Situation, Crisis):
        db_session.query(model).delete()
    db_session.commit()


class SimpleHarness:
    def __init__(self, fake, session):
        self.fake, self.session = fake, session
        self.user = str(uuid.uuid4())

    def place(self, prefs=None, lat=HOUSTON[0], lon=HOUSTON[1], radius=200, name='Port'):
        row = self.fake.add('geointel_watch_places', user_id=self.user, name=name, lat=lat, lon=lon, radius_km=radius)
        row['alert_prefs'] = prefs if prefs is not None else {}
        return row

    def event(self, id, severity=65, hours=2, lat=29.9, lon=-95.0, kind='physical', title=None, situation_id=None, **extra):
        self.session.add(Crisis(id=id, type='conflict', title=title or f'Event {id}', country='United States', latitude=lat, longitude=lon,
                                severity=severity, is_active=True, event_kind=kind, situation_id=situation_id,
                                date_start=datetime.utcnow() - timedelta(hours=hours), **extra))
        self.session.commit()

    def alerts(self):
        return self.fake.tables['geointel_alerts']


class TestPrefs:
    def test_validation_and_defaults(self):
        assert situation_settings({}) == (False, 40, False)                   # off unless switched on
        assert situation_settings(ON) == (True, 40, False)
        assert situation_settings({'situations': {'enabled': True, 'min_severity': 'critical', 'statements': True}}) == (True, 80, True)
        assert clean_prefs({'situations': {'enabled': True, 'min_severity': 'severe'}}) == {'situations': {'enabled': True, 'min_severity': 'severe'}}
        for bad in ({'situations': 'x'}, {'situations': {'enabled': 'yes'}}, {'situations': {'min_severity': 'huge'}}, {'situations': {'x': 1}}):
            with pytest.raises(InvalidPlaceAlertPrefs):
                clean_prefs(bad)

    @pytest.mark.parametrize('severity,level', [(40, 'Green'), (59, 'Green'), (60, 'Orange'), (79, 'Orange'), (80, 'Red'), (100, 'Red')])
    def test_levels(self, severity, level):
        assert sa.alert_level(severity) == level


class TestEvaluate:
    def test_a_serious_event_inside_the_radius_alerts_once(self, h):
        place = h.place(ON)
        h.event('e1', severity=65)
        assert sa.evaluate_situations()['new_alerts'] == 1
        (alert,) = h.alerts()
        assert alert['place_id'] == place['id'] and alert['hazard_type'] == 'SIT'
        assert alert['hazard_key'] == 'SIT-e1-orange' and alert['alert_level'] == 'Orange'
        assert 0 < alert['distance_km'] < 200
        assert sa.evaluate_situations()['new_alerts'] == 0                      # never twice

    def test_escalation_alerts_again(self, h):
        h.place(ON)
        h.event('e1', severity=65)
        sa.evaluate_situations()
        e = h.session.query(Crisis).filter(Crisis.id == 'e1').one()
        e.severity = 85
        h.session.commit()
        assert sa.evaluate_situations()['new_alerts'] == 1
        assert {a['hazard_key'] for a in h.alerts()} == {'SIT-e1-orange', 'SIT-e1-red'}

    def test_off_by_default_and_outside_the_radius_and_below_the_severity(self, h):
        h.place({})                                                              # not switched on
        h.place(ON, name='Far', lat=60.0, lon=10.0)                             # event is far away
        h.place({'situations': {'enabled': True, 'min_severity': 'critical'}}, name='Picky')
        h.event('e1', severity=65)
        assert sa.evaluate_situations()['new_alerts'] == 0

    def test_statements_only_when_asked(self, h):
        h.place(ON, name='A')
        h.place({'situations': {'enabled': True, 'statements': True}}, name='B')
        h.event('talk', kind='statement')
        sa.evaluate_situations()
        assert [a['place_id'] for a in h.alerts()] == [h.fake.tables['geointel_watch_places'][1]['id']]

    def test_old_events_and_merged_or_inactive_ones_are_ignored(self, h):
        h.place(ON)
        h.event('old', hours=48)
        h.event('merged', merged_into='x')
        h.event('quiet', severity=20)
        assert sa.evaluate_situations()['new_alerts'] == 0

    def test_a_situation_is_one_alert_named_by_its_main_headline(self, h):
        h.place(ON)
        for i in range(3):
            h.event(f's{i}', hours=3 - i, situation_id='s0')
        h.session.add(Situation(id='s0', title='Houthis strike Saudi airports', country='Saudi Arabia', story_count=3, source_total=5,
                                first_at=datetime.utcnow(), last_at=datetime.utcnow()))
        h.session.commit()
        assert sa.evaluate_situations()['new_alerts'] == 1
        (alert,) = h.alerts()
        assert alert['title'] == 'Houthis strike Saudi airports (3 stories)' and alert['hazard_key'].startswith('SIT-s0-')

    def test_at_most_five_per_place_per_run_most_severe_first(self, h):
        h.place(ON)
        for i in range(8):
            h.event(f'e{i}', severity=50 + i, lat=29.9 + i * 0.01)
        assert sa.evaluate_situations()['new_alerts'] == 5
        assert {a['hazard_key'] for a in h.alerts()} == {f'SIT-e{i}-orange' if 50 + i >= 60 else f'SIT-e{i}-green' for i in range(3, 8)}

    def test_missing_prefs_column_is_skipped_quietly(self, h):
        with patch.object(sa, 'rest', side_effect=supabase_rest.SupabaseUnavailable('column_missing')):
            assert sa.evaluate_situations()['skipped'] == 'no_prefs_column'
