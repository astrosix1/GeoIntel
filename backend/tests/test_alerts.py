"""Hazard alert evaluation: matching, dedupe, escalation, preferences, and the
email digest with retry. Supabase is the in-memory fake; the hazard feed,
Resend and the auth email lookup are patched."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services import alerts, supabase_rest
from services.alerts import _digest, evaluate_alerts
from services.supabase_rest import SupabaseUnavailable
from supabase_fake import FakePostgrest

HOUSTON = (29.73, -95.27)


def hazard(id=1, level='Red', lat=29.9, lon=-95.0, **extra):
    return {'id': id, 'event_type': 'TC', 'hazard': 'Tropical cyclone', 'name': f'STORM-{id}',
            'alert_level': level, 'lat': lat, 'lon': lon, **extra}


class Harness:
    def __init__(self, db):
        self.db = db
        self.storms = []              # None = hazard feed down
        self.addresses = {}           # user_id -> email
        self.sent = []                # (to, subject, html, text)
        self.send_ok = True
        self.configured = True
        self.lookup_fails = set()

    def user(self, email='user@example.com', **prefs):
        user_id = str(uuid.uuid4())
        self.addresses[user_id] = email
        if prefs:
            self.db.add('geointel_user_prefs', user_id=user_id, **prefs)
        return user_id

    def place(self, user_id, name='Port', lat=HOUSTON[0], lon=HOUSTON[1], radius=300):
        return self.db.add('geointel_watch_places', user_id=user_id, name=name, lat=lat, lon=lon, radius_km=radius)

    def alerts(self, user_id=None):
        rows = self.db.tables['geointel_alerts']
        return [r for r in rows if user_id is None or r['user_id'] == user_id]

    # patched collaborators
    def feed(self):
        return None if self.storms is None else {'storms': self.storms}

    def lookup(self, user_id):
        if user_id in self.lookup_fails:
            raise SupabaseUnavailable('request_failed')
        return self.addresses.get(user_id)

    def send(self, to, subject, html, text):
        if not self.send_ok:
            return False
        self.sent.append((to, subject, html, text))
        return True


@pytest.fixture()
def h(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://proj.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
    fake = FakePostgrest()
    harness = Harness(fake)
    with patch.object(supabase_rest.requests, 'request', fake.request), \
            patch.object(alerts, 'get_active_storms', side_effect=lambda: harness.feed()), \
            patch.object(alerts, 'auth_user_email', side_effect=harness.lookup), \
            patch.object(alerts, 'send_email', side_effect=harness.send), \
            patch.object(alerts, 'is_configured', side_effect=lambda: harness.configured):
        yield harness


class TestMatching:
    def test_hazard_in_radius_creates_an_alert(self, h):
        user = h.user()
        place = h.place(user)
        h.storms = [hazard(1, 'Red')]
        summary = evaluate_alerts()
        (alert,) = h.alerts(user)
        assert summary['new_alerts'] == 1
        assert alert['place_id'] == place['id']
        assert alert['hazard_key'] == 'TC-1-red'
        assert alert['title'] == 'STORM-1'
        assert alert['alert_level'] == 'Red'
        assert 0 < alert['distance_km'] < 300

    def test_hazard_outside_radius_is_ignored(self, h):
        user = h.user()
        h.place(user, radius=300)
        h.storms = [hazard(1, 'Red', lat=40.0, lon=-95.0)]
        evaluate_alerts()
        assert h.alerts() == []

    def test_radius_is_per_place(self, h):
        user = h.user()
        h.place(user, 'Tight', radius=10)
        wide = h.place(user, 'Wide', radius=2000)
        h.storms = [hazard(1, 'Red')]
        evaluate_alerts()
        assert [a['place_id'] for a in h.alerts(user)] == [wide['id']]

    def test_each_user_is_alerted_only_for_their_own_places(self, h):
        near, far = h.user(), h.user()
        h.place(near)
        h.place(far, lat=-30, lon=150)
        h.storms = [hazard(1, 'Red')]
        evaluate_alerts()
        assert len(h.alerts(near)) == 1
        assert h.alerts(far) == []

    def test_two_places_near_one_hazard_give_two_alerts(self, h):
        user = h.user()
        h.place(user, 'A')
        h.place(user, 'B')
        h.storms = [hazard(1, 'Red')]
        assert evaluate_alerts()['new_alerts'] == 2

    def test_unusable_hazards_are_ignored(self, h):
        user = h.user()
        h.place(user)
        h.storms = [hazard(1, 'Unknown'), hazard(2, None), hazard(3, 'Red', lat=None, lon=None),
                    {'event_type': 'TC', 'alert_level': 'Red', 'lat': 29.9, 'lon': -95.0},   # no id
                    hazard(5, 'Red', event_type='')]
        evaluate_alerts()
        assert h.alerts() == []

    def test_no_places_does_nothing(self, h):
        h.storms = [hazard()]
        assert evaluate_alerts() == {'places': 0, 'new_alerts': 0, 'emails': 0, 'skipped': None}

    def test_hazard_feed_down_is_a_quiet_no_op(self, h):
        user = h.user()
        h.place(user)
        h.storms = None
        summary = evaluate_alerts()
        assert summary['skipped'] == 'hazard_feed_unavailable'
        assert h.alerts() == [] and h.sent == []

    def test_deleted_place_stops_alerting(self, h):
        user = h.user()
        place = h.place(user)
        h.db.tables['geointel_watch_places'].remove(place)
        h.storms = [hazard()]
        evaluate_alerts()
        assert h.alerts() == []


class TestLevelsAndEscalation:
    @pytest.mark.parametrize('minimum,level,alerted', [
        ('green', 'Green', True), ('green', 'Orange', True), ('green', 'Red', True),
        ('orange', 'Green', False), ('orange', 'Orange', True), ('orange', 'Red', True),
        ('red', 'Green', False), ('red', 'Orange', False), ('red', 'Red', True),
    ])
    def test_minimum_level_is_respected(self, h, minimum, level, alerted):
        user = h.user(alert_min_level=minimum)
        h.place(user)
        h.storms = [hazard(1, level)]
        evaluate_alerts()
        assert bool(h.alerts(user)) is alerted

    def test_default_minimum_is_orange(self, h):
        user = h.user()   # no prefs row at all
        h.place(user)
        h.storms = [hazard(1, 'Green'), hazard(2, 'Orange')]
        evaluate_alerts()
        assert [a['hazard_key'] for a in h.alerts(user)] == ['TC-2-orange']

    def test_same_hazard_does_not_alert_twice(self, h):
        user = h.user()
        h.place(user)
        h.storms = [hazard(1, 'Red')]
        assert evaluate_alerts()['new_alerts'] == 1
        assert evaluate_alerts()['new_alerts'] == 0
        assert len(h.alerts(user)) == 1

    def test_escalation_alerts_again(self, h):
        user = h.user(alert_min_level='green')
        h.place(user)
        h.storms = [hazard(1, 'Green')]
        evaluate_alerts()
        h.storms = [hazard(1, 'Orange')]
        assert evaluate_alerts()['new_alerts'] == 1
        assert sorted(a['hazard_key'] for a in h.alerts(user)) == ['TC-1-green', 'TC-1-orange']

    def test_dropping_back_to_an_already_alerted_level_is_quiet(self, h):
        user = h.user(alert_min_level='green')
        h.place(user)
        for level in ('Green', 'Orange', 'Green'):
            h.storms = [hazard(1, level)]
            evaluate_alerts()
        assert len(h.alerts(user)) == 2

    def test_different_hazards_alert_separately(self, h):
        user = h.user()
        h.place(user)
        h.storms = [hazard(1, 'Red'), hazard(2, 'Red', lat=30.0)]
        assert evaluate_alerts()['new_alerts'] == 2


class TestEmail:
    def test_one_digest_per_user_with_all_new_alerts(self, h):
        user = h.user('ada@example.com')
        h.place(user, 'A')
        h.place(user, 'B')
        h.storms = [hazard(1, 'Red'), hazard(2, 'Orange', lat=30.0)]
        summary = evaluate_alerts()
        assert summary['emails'] == 1 and len(h.sent) == 1
        to, subject, body, text = h.sent[0]
        assert to == 'ada@example.com'
        assert '4 hazards' in subject
        assert 'STORM-1' in text and 'STORM-2' in text and 'from A' in text and 'from B' in text
        assert all(a['emailed_at'] for a in h.alerts(user))

    def test_each_user_gets_their_own_email(self, h):
        a, b = h.user('a@example.com'), h.user('b@example.com')
        h.place(a)
        h.place(b)
        h.storms = [hazard()]
        evaluate_alerts()
        assert sorted(m[0] for m in h.sent) == ['a@example.com', 'b@example.com']

    def test_not_resent_on_the_next_run(self, h):
        user = h.user()
        h.place(user)
        h.storms = [hazard()]
        evaluate_alerts()
        evaluate_alerts()
        assert len(h.sent) == 1

    def test_failed_send_is_retried_without_a_duplicate_alert(self, h):
        user = h.user()
        h.place(user)
        h.storms = [hazard()]
        h.send_ok = False
        first = evaluate_alerts()
        assert first['new_alerts'] == 1 and first['emails'] == 0
        assert h.alerts(user)[0]['emailed_at'] is None
        h.send_ok = True
        second = evaluate_alerts()
        assert second['new_alerts'] == 0 and second['emails'] == 1
        assert len(h.alerts(user)) == 1 and len(h.sent) == 1

    def test_email_off_still_creates_in_app_alerts(self, h):
        user = h.user(alert_email=False)
        h.place(user)
        h.storms = [hazard()]
        summary = evaluate_alerts()
        assert summary['new_alerts'] == 1 and h.sent == []
        assert h.alerts(user)[0]['emailed_at'] is None

    def test_mailer_not_configured_still_creates_in_app_alerts(self, h):
        user = h.user()
        h.place(user)
        h.storms = [hazard()]
        h.configured = False
        summary = evaluate_alerts()
        assert summary['new_alerts'] == 1 and summary['emails'] == 0 and h.sent == []

    def test_emails_caught_up_once_the_mailer_is_configured(self, h):
        user = h.user()
        h.place(user)
        h.storms = [hazard()]
        h.configured = False
        evaluate_alerts()
        h.configured = True
        assert evaluate_alerts()['emails'] == 1

    def test_user_without_an_email_address_is_skipped(self, h):
        user = h.user(email=None)
        h.place(user)
        h.storms = [hazard()]
        summary = evaluate_alerts()
        assert summary['new_alerts'] == 1 and summary['emails'] == 0
        assert h.alerts(user)[0]['emailed_at'] is None

    def test_email_lookup_failure_does_not_block_other_users(self, h):
        broken, fine = h.user('x@example.com'), h.user('ok@example.com')
        h.place(broken)
        h.place(fine)
        h.lookup_fails.add(broken)
        h.storms = [hazard()]
        summary = evaluate_alerts()
        assert summary['emails'] == 1 and [m[0] for m in h.sent] == ['ok@example.com']

    def test_old_unsent_alerts_are_not_emailed(self, h):
        user = h.user()
        place = h.place(user)
        old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        h.db.add('geointel_alerts', user_id=user, place_id=place['id'], hazard_key='TC-9-red', hazard_type='TC',
                 title='Old', alert_level='Red', distance_km=1.0, created_at=old)
        h.storms = []
        assert evaluate_alerts()['emails'] == 0

    def test_alerts_created_before_the_user_turned_email_on_are_sent_when_recent(self, h):
        user = h.user(alert_email=False)
        h.place(user)
        h.storms = [hazard()]
        evaluate_alerts()
        h.db.tables['geointel_user_prefs'][0]['alert_email'] = True
        assert evaluate_alerts()['emails'] == 1


class TestDigestContent:
    def row(self, i=1, title='Storm', place_id='p1'):
        return {'id': str(uuid.uuid4()), 'place_id': place_id, 'title': title, 'alert_level': 'Red', 'distance_km': 12.5}

    def test_text_and_html_describe_each_alert(self):
        subject, body, text = _digest([self.row(title='POLO')], {'p1': 'Port of Houston'})
        assert subject == 'GeoIntel weather alert: 1 hazard near your places'
        assert 'Red alert: POLO is 12.5 km from Port of Houston' in text
        assert 'POLO' in body and 'Port of Houston' in body

    def test_html_is_escaped(self):
        _, body, text = _digest([self.row(title='<script>alert(1)</script>')], {'p1': '<b>Evil</b> & Co'})
        assert '<script>' not in body and '<b>' not in body
        assert '&lt;script&gt;' in body and '&amp; Co' in body
        assert '<script>' in text   # plain text part is not HTML

    def test_long_digests_are_truncated(self):
        rows = [self.row(title=f'S{i}') for i in range(25)]
        subject, body, text = _digest(rows, {'p1': 'Place'})
        assert '25 hazards' in subject
        assert 'S19' in text and 'S20' not in text
        assert '...and 5 more' in text and '...and 5 more' in body

    def test_footer_explains_how_to_turn_alerts_off(self):
        _, body, text = _digest([self.row()], {'p1': 'Place'})
        assert 'Dashboard > Alerts' in text and 'Dashboard &gt; Alerts' in body

    def test_app_url_comes_from_the_environment(self, monkeypatch):
        monkeypatch.setenv('APP_BASE_URL', 'https://example.org/')
        _, body, text = _digest([self.row()], {'p1': 'Place'})
        assert 'https://example.org' in text and 'https://example.org/' not in text.split('Open GeoIntel: ')[1].split('\n')[0]


class TestResilience:
    def test_supabase_down_is_reported_not_raised(self, h):
        h.storms = [hazard()]
        h.db.fail = True
        summary = evaluate_alerts()
        assert summary['skipped'] == 'request_failed'

    def test_unconfigured_supabase_is_reported_not_raised(self, h, monkeypatch):
        monkeypatch.delenv('SUPABASE_URL')
        h.storms = [hazard()]
        assert evaluate_alerts()['skipped'] == 'not_configured'

    def test_unexpected_errors_never_escape(self, h):
        h.storms = [hazard()]
        with patch.object(alerts, 'rest', side_effect=RuntimeError('boom')):
            assert evaluate_alerts()['skipped'] == 'error'
