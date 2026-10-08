"""Watchlist places, alerts list/read, alert settings and place search: the
service layer (against the in-memory Supabase fake) and the HTTP endpoints."""
import time
import uuid
from unittest.mock import patch

import jwt
import pytest

from cache import cache_delete
from extensions import limiter
from services import entitlements, supabase_rest
from services import watchlist as svc
from services.forecast import ForecastUnavailable
from services.supabase_rest import SupabaseUnavailable
from supabase_fake import FakePostgrest

SECRET = 'jwt-signing-secret'


@pytest.fixture(autouse=True)
def fresh_limits(app_module):
    limiter.reset()
    yield


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://proj.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
    fake = FakePostgrest()
    with patch.object(supabase_rest.requests, 'request', fake.request):
        yield fake


def uid():
    return str(uuid.uuid4())


def add_place(user, name='Port of Houston', lat=29.73, lon=-95.27, radius=200):
    return svc.add_place(user, name, lat, lon, radius)


def add_alert(db, user, place, level='Orange', **extra):
    return db.add('geointel_alerts', user_id=user, place_id=place['id'], hazard_key=extra.pop('hazard_key', f'TC-1-{level}'),
                  hazard_type='TC', title='Storm', alert_level=level, distance_km=50.0, **extra)


class TestCleanPlace:
    def test_trims_collapses_and_rounds(self):
        assert svc.clean_place('  Port   of\tHouston ', 29.123456, -95.987654, 200) == {
            'name': 'Port of Houston', 'lat': 29.1235, 'lon': -95.9877, 'radius_km': 200}

    def test_accepts_the_limits(self):
        svc.clean_place('a', -90, -180, 10)
        svc.clean_place('a' * 80, 90, 180, 2000)

    def test_strips_control_characters(self):
        assert svc.clean_place('Bay\x00\x07 Area', 1, 1, 50)['name'] == 'Bay Area'

    @pytest.mark.parametrize('name', ['', '   ', 'x' * 81, None, 5, '\x00\x01'])
    def test_bad_names(self, name):
        with pytest.raises(svc.InvalidPlace):
            svc.clean_place(name, 1, 1, 50)

    @pytest.mark.parametrize('lat,lon', [(91, 0), (-91, 0), (0, 181), (0, -181), ('x', 0), (0, None),
                                         (True, 0), (float('nan'), 0), (0, float('inf'))])
    def test_bad_coordinates(self, lat, lon):
        with pytest.raises(svc.InvalidPlace):
            svc.clean_place('Place', lat, lon, 50)

    @pytest.mark.parametrize('radius', [9, 2001, 0, -5, 12.5, 'big', None, True, float('nan')])
    def test_bad_radius(self, radius):
        with pytest.raises(svc.InvalidPlace):
            svc.clean_place('Place', 1, 1, radius)

    def test_whole_number_float_radius_is_fine(self):
        assert svc.clean_place('Place', 1, 1, 50.0)['radius_km'] == 50


class TestPlaces:
    def test_add_and_list_in_order(self, db):
        user = uid()
        add_place(user, 'First')
        add_place(user, 'Second')
        assert [p['name'] for p in svc.list_places(user)] == ['First', 'Second']

    def test_places_are_per_user(self, db):
        alice, bob = uid(), uid()
        add_place(alice, 'Shared name')
        add_place(bob, 'Shared name')  # same name, different user: fine
        assert len(svc.list_places(alice)) == 1
        assert len(svc.list_places(bob)) == 1

    def test_duplicate_name_is_refused_ignoring_case(self, db):
        user = uid()
        add_place(user, 'Port')
        with pytest.raises(svc.PlaceExists):
            add_place(user, 'PORT')

    def test_cap_is_enforced(self, db):
        user = uid()
        for i in range(svc.MAX_PLACES):
            add_place(user, f'Place {i}')
        with pytest.raises(svc.PlaceLimitReached):
            add_place(user, 'One too many')
        assert len(svc.list_places(user)) == svc.MAX_PLACES

    def test_cap_is_per_user(self, db):
        full, other = uid(), uid()
        for i in range(svc.MAX_PLACES):
            add_place(full, f'Place {i}')
        add_place(other, 'Mine')

    def test_delete_own_place_and_its_alerts(self, db):
        user = uid()
        place = add_place(user)
        add_alert(db, user, place)
        svc.delete_place(user, place['id'])
        assert svc.list_places(user) == []
        assert db.tables['geointel_alerts'] == []

    def test_cannot_delete_someone_elses_place(self, db):
        owner, other = uid(), uid()
        place = add_place(owner)
        svc.delete_place(other, place['id'])
        assert len(svc.list_places(owner)) == 1

    def test_bad_ids_are_rejected(self, db):
        with pytest.raises(SupabaseUnavailable) as exc:
            svc.delete_place(uid(), 'not-a-uuid')
        assert exc.value.reason == 'bad_id'

    def test_invalid_place_is_not_saved(self, db):
        with pytest.raises(svc.InvalidPlace):
            svc.add_place(uid(), 'x', 1, 1, 5)
        assert db.tables['geointel_watch_places'] == []


class TestNearbyHazards:
    PLACE = {'lat': 29.73, 'lon': -95.27, 'radius_km': 300}

    def storm(self, lat, lon, **extra):
        return {'id': 1, 'event_type': 'TC', 'hazard': 'Tropical cyclone', 'name': 'A', 'alert_level': 'Red',
                'lat': lat, 'lon': lon, **extra}

    def test_returns_hazards_within_radius_nearest_first(self):
        far, near = self.storm(31.5, -95.0, id=2), self.storm(29.9, -95.0, id=3)
        outside = self.storm(40, -95, id=4)
        found = svc.nearby_hazards(self.PLACE, [far, outside, near])
        assert [h['id'] for h in found] == [3, 2]
        assert found[0]['distance_km'] < found[1]['distance_km'] <= 300

    def test_radius_edge_is_inclusive(self):
        from services.geo import distance_km
        edge = self.storm(32.0, -95.27)
        place = {**self.PLACE, 'radius_km': 10}
        assert svc.nearby_hazards(place, [edge]) == []
        place['radius_km'] = int(distance_km(29.73, -95.27, 32.0, -95.27)) + 1
        assert len(svc.nearby_hazards(place, [edge])) == 1

    def test_skips_hazards_without_coordinates(self):
        assert svc.nearby_hazards(self.PLACE, [self.storm(None, None), {'id': 9}]) == []

    def test_no_hazards(self):
        assert svc.nearby_hazards(self.PLACE, []) == []
        assert svc.nearby_hazards(self.PLACE, None) == []


class TestAlerts:
    def test_listed_newest_first_with_place_name(self, db):
        user = uid()
        place = add_place(user, 'Port')
        add_alert(db, user, place, 'Green', hazard_key='a')
        add_alert(db, user, place, 'Red', hazard_key='b')
        alerts = svc.list_alerts(user)
        assert [a['alert_level'] for a in alerts] == ['Red', 'Green']
        assert alerts[0]['place_name'] == 'Port'

    def test_alerts_are_per_user(self, db):
        alice, bob = uid(), uid()
        add_alert(db, alice, add_place(alice))
        assert svc.list_alerts(bob) == []
        assert svc.unread_count(bob) == 0

    def test_unread_count_and_mark_read(self, db):
        user = uid()
        place = add_place(user)
        a1 = add_alert(db, user, place, hazard_key='a')
        add_alert(db, user, place, hazard_key='b')
        assert svc.unread_count(user) == 2
        svc.mark_alerts_read(user, [a1['id']])
        assert svc.unread_count(user) == 1
        svc.mark_alerts_read(user)
        assert svc.unread_count(user) == 0

    def test_cannot_mark_someone_elses_alert_read(self, db):
        owner, other = uid(), uid()
        alert = add_alert(db, owner, add_place(owner))
        svc.mark_alerts_read(other, [alert['id']])
        svc.mark_alerts_read(other)
        assert svc.unread_count(owner) == 1

    def test_marking_read_twice_keeps_the_first_time(self, db):
        user = uid()
        alert = add_alert(db, user, add_place(user))
        svc.mark_alerts_read(user)
        first = db.tables['geointel_alerts'][0]['read_at']
        svc.mark_alerts_read(user, [alert['id']])
        assert db.tables['geointel_alerts'][0]['read_at'] == first

    def test_empty_id_list_changes_nothing(self, db):
        user = uid()
        add_alert(db, user, add_place(user))
        svc.mark_alerts_read(user, [])
        assert svc.unread_count(user) == 1


class TestAlertSettings:
    def test_defaults(self, db):
        assert svc.get_alert_settings(uid()) == {'alert_email': True, 'alert_min_level': 'orange', 'alert_conditions': {}, 'unavailable_conditions': ['gust_kmh']}

    def test_set_one_field_keeps_the_other(self, db):
        user = uid()
        assert svc.set_alert_settings(user, alert_min_level='red') == {'alert_email': True, 'alert_min_level': 'red', 'alert_conditions': {}, 'unavailable_conditions': ['gust_kmh']}
        assert svc.set_alert_settings(user, alert_email=False) == {'alert_email': False, 'alert_min_level': 'red', 'alert_conditions': {}, 'unavailable_conditions': ['gust_kmh']}

    def test_does_not_clobber_hidden_outlets(self, db):
        user = uid()
        db.add('geointel_user_prefs', user_id=user, hidden_outlets=['bbc.com'])
        svc.set_alert_settings(user, alert_email=False)
        assert db.tables['geointel_user_prefs'][0]['hidden_outlets'] == ['bbc.com']

    @pytest.mark.parametrize('kwargs', [{'alert_email': 'yes'}, {'alert_email': 1}, {'alert_min_level': 'purple'},
                                        {'alert_min_level': 'RED'}, {}])
    def test_invalid_settings(self, db, kwargs):
        with pytest.raises(svc.InvalidAlertSettings):
            svc.set_alert_settings(uid(), **kwargs)

    def test_supabase_failure(self, db):
        db.fail = True
        with pytest.raises(SupabaseUnavailable):
            svc.get_alert_settings(uid())


# --- HTTP -------------------------------------------------------------------

def token(user_id):
    return jwt.encode({'sub': user_id, 'aud': 'authenticated', 'exp': int(time.time()) + 3600},
                      SECRET, algorithm='HS256')


@pytest.fixture()
def secret(monkeypatch):
    monkeypatch.setenv('SUPABASE_JWT_SECRET', SECRET)


def call(client, method, path, user=None, plan='active', **kwargs):
    headers = dict(kwargs.pop('headers', {}))
    if user:
        headers['Authorization'] = f'Bearer {token(user)}'
        cache_delete(f'plan:{user}')
    row = {'status': plan} if plan else None
    with patch.object(entitlements, '_fetch_subscription', return_value=row):
        return getattr(client, method)(path, headers=headers, **kwargs)


STORMS = {'storms': [{'id': 7, 'event_type': 'TC', 'hazard': 'Tropical cyclone', 'name': 'POLO', 'alert_level': 'Red',
                      'lat': 29.9, 'lon': -95.0}]}

PREMIUM_ONLY = [('get', '/api/me/watch'), ('post', '/api/me/watch'), ('get', '/api/me/alerts'),
                ('get', '/api/me/alert-settings'), ('put', '/api/me/alert-settings'), ('get', '/api/me/geo/search?q=oslo')]
SIGNED_IN_ONLY = [('delete', f'/api/me/watch/{uuid.uuid4()}'), ('post', '/api/me/alerts/read')]


class TestAccessControl:
    @pytest.mark.parametrize('method,path', PREMIUM_ONLY + SIGNED_IN_ONLY)
    def test_anonymous_is_401(self, client, secret, db, method, path):
        assert call(client, method, path, json={}).status_code == 401
        assert db.calls == []

    @pytest.mark.parametrize('method,path', PREMIUM_ONLY)
    def test_free_user_is_403_and_nothing_is_touched(self, client, secret, db, method, path):
        res = call(client, method, path, uid(), plan=None, json={})
        assert res.status_code == 403
        assert res.get_json()['error'] == 'premium_required'
        assert db.calls == []

    def test_lapsed_member_can_still_delete_and_mark_read(self, client, secret, db):
        user = uid()
        place = add_place(user)
        assert call(client, 'delete', f"/api/me/watch/{place['id']}", user, plan=None).status_code == 204
        assert call(client, 'post', '/api/me/alerts/read', user, plan=None, json={'all': True}).status_code == 204


class TestWatchEndpoints:
    def test_add_list_delete(self, client, secret, db):
        user = uid()
        body = {'name': 'Port of Houston', 'lat': 29.73, 'lon': -95.27, 'radius_km': 200}
        created = call(client, 'post', '/api/me/watch', user, json=body)
        assert created.status_code == 201
        place = created.get_json()['place']
        assert place['name'] == 'Port of Houston'

        with patch('blueprints.watchlist.get_active_storms', return_value=STORMS):
            listed = call(client, 'get', '/api/me/watch', user).get_json()
        assert listed['limit'] == 25 and listed['hazards_available'] is True
        assert listed['places'][0]['nearby'][0]['name'] == 'POLO'

        assert call(client, 'delete', f"/api/me/watch/{place['id']}", user).status_code == 204
        with patch('blueprints.watchlist.get_active_storms', return_value=STORMS):
            assert call(client, 'get', '/api/me/watch', user).get_json()['places'] == []

    def test_list_without_hazard_feed_is_honest(self, client, secret, db):
        user = uid()
        add_place(user)
        with patch('blueprints.watchlist.get_active_storms', return_value=None):
            body = call(client, 'get', '/api/me/watch', user).get_json()
        assert body['hazards_available'] is False
        assert body['places'][0]['nearby'] == []

    @pytest.mark.parametrize('body', [None, [], 'x', {}, {'name': 'a'}, {'name': 'a', 'lat': 1, 'lon': 1, 'radius_km': 5},
                                      {'name': 'a', 'lat': 100, 'lon': 1, 'radius_km': 50}])
    def test_invalid_places_are_400(self, client, secret, db, body):
        res = call(client, 'post', '/api/me/watch', uid(), json=body)
        assert res.status_code == 400
        assert res.get_json()['error'] == 'invalid_place'

    def test_duplicate_and_limit_are_409(self, client, secret, db):
        user = uid()
        good = {'name': 'Port', 'lat': 1, 'lon': 1, 'radius_km': 50}
        assert call(client, 'post', '/api/me/watch', user, json=good).status_code == 201
        dup = call(client, 'post', '/api/me/watch', user, json={**good, 'name': 'port'})
        assert (dup.status_code, dup.get_json()['error']) == (409, 'place_exists')
        for i in range(24):
            assert call(client, 'post', '/api/me/watch', user, json={**good, 'name': f'P{i}'}).status_code == 201
        full = call(client, 'post', '/api/me/watch', user, json={**good, 'name': 'extra'})
        assert (full.status_code, full.get_json()['error']) == (409, 'place_limit_reached')

    def test_users_only_see_their_own_places(self, client, secret, db):
        alice, bob = uid(), uid()
        add_place(alice)
        with patch('blueprints.watchlist.get_active_storms', return_value=STORMS):
            assert call(client, 'get', '/api/me/watch', bob).get_json()['places'] == []

    def test_cannot_delete_another_users_place_over_http(self, client, secret, db):
        owner, other = uid(), uid()
        place = add_place(owner)
        assert call(client, 'delete', f"/api/me/watch/{place['id']}", other).status_code == 204
        assert len(svc.list_places(owner)) == 1

    def test_malformed_id_is_404(self, client, secret, db):
        assert call(client, 'delete', '/api/me/watch/nope', uid()).status_code == 404

    def test_supabase_down_is_503(self, client, secret, db):
        db.fail = True
        res = call(client, 'get', '/api/me/watch', uid())
        assert res.status_code == 503
        assert res.get_json()['error'] == 'user_data_unavailable'


class TestAlertEndpoints:
    def test_list_and_mark_read(self, client, secret, db):
        user = uid()
        place = add_place(user)
        alert = add_alert(db, user, place)
        body = call(client, 'get', '/api/me/alerts', user).get_json()
        assert body['unread'] == 1 and body['alerts'][0]['place_name'] == 'Port of Houston'
        assert call(client, 'post', '/api/me/alerts/read', user, json={'ids': [alert['id']]}).status_code == 204
        assert call(client, 'get', '/api/me/alerts', user).get_json()['unread'] == 0

    @pytest.mark.parametrize('body', [None, [], {}, {'ids': 'x'}, {'ids': [1]}, {'all': 'yes'}])
    def test_bad_read_bodies_are_400(self, client, secret, db, body):
        assert call(client, 'post', '/api/me/alerts/read', uid(), json=body).status_code == 400

    def test_settings_round_trip(self, client, secret, db):
        user = uid()
        assert call(client, 'get', '/api/me/alert-settings', user).get_json() == {
            'alert_email': True, 'alert_min_level': 'orange', 'alert_conditions': {}, 'unavailable_conditions': ['gust_kmh']}
        res = call(client, 'put', '/api/me/alert-settings', user, json={'alert_email': False, 'alert_min_level': 'red'})
        assert res.get_json() == {'alert_email': False, 'alert_min_level': 'red', 'alert_conditions': {}, 'unavailable_conditions': ['gust_kmh']}

    def test_conditions_round_trip_merge_and_switch_off(self, client, secret, db):
        user = uid()
        res = call(client, 'put', '/api/me/alert-settings', user, json={'alert_conditions': {'heat_c': 38, 'rain_mm': 80}})
        assert res.get_json()['alert_conditions'] == {'heat_c': 38.0, 'rain_mm': 80.0}
        res = call(client, 'put', '/api/me/alert-settings', user, json={'alert_conditions': {'cold_c': -10, 'heat_c': None}})
        assert res.get_json()['alert_conditions'] == {'rain_mm': 80.0, 'cold_c': -10.0}
        saved = call(client, 'get', '/api/me/alert-settings', user).get_json()['alert_conditions']
        assert saved == {'rain_mm': 80.0, 'cold_c': -10.0}

    @pytest.mark.parametrize('conditions', [
        {'heat_c': 99}, {'heat_c': 5}, {'nonsense': 1}, {'rain_mm': 'lots'}, {'gust_kmh': True}, 'hot', [1],
    ])
    def test_bad_conditions_are_400(self, client, secret, db, conditions):
        res = call(client, 'put', '/api/me/alert-settings', uid(), json={'alert_conditions': conditions})
        assert res.status_code == 400

    @pytest.mark.parametrize('body', [None, [], {}, {'alert_min_level': 'purple'}, {'alert_email': 'no'}])
    def test_bad_settings_are_400(self, client, secret, db, body):
        assert call(client, 'put', '/api/me/alert-settings', uid(), json=body).status_code == 400


class TestSearchEndpoint:
    def test_returns_results(self, client, secret, db):
        results = [{'name': 'Oslo', 'country': 'Norway', 'admin1': 'Oslo', 'lat': 59.9, 'lon': 10.7}]
        with patch('blueprints.watchlist.search_places', return_value=results):
            body = call(client, 'get', '/api/me/geo/search?q=oslo', uid()).get_json()
        assert body == {'results': results}

    def test_short_query_is_400(self, client, secret, db):
        assert call(client, 'get', '/api/me/geo/search?q=o', uid()).status_code == 400

    def test_provider_failure_is_503(self, client, secret, db):
        with patch('blueprints.watchlist.search_places', side_effect=ForecastUnavailable('down')):
            res = call(client, 'get', '/api/me/geo/search?q=oslo', uid())
        assert (res.status_code, res.get_json()['error']) == (503, 'search_unavailable')

    def test_search_is_rate_limited(self, client, secret, db):
        user = uid()
        with patch('blueprints.watchlist.search_places', return_value=[]):
            codes = [call(client, 'get', '/api/me/geo/search?q=oslo', user).status_code for _ in range(21)]
        assert codes[:20] == [200] * 20 and codes[20] == 429
