"""Hazard-event links: every matching rule on its own, then the two queries and endpoints."""
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from cache import cache_clear_prefix
from extensions import limiter
from models import Crisis
from services import hazard_links as hl

BOX = [[10, 10], [10, 11], [11, 11], [11, 10], [10, 10]]      # lon 10-11, lat 10-11
HOLE = [[10.4, 10.4], [10.4, 10.6], [10.6, 10.6], [10.6, 10.4], [10.4, 10.4]]
NOW = datetime(2026, 10, 5, 12, 0)


def feat(geometry, **props):
    return {'type': 'Feature', 'geometry': geometry, 'properties': props}


def poly(*rings):
    return {'type': 'Polygon', 'coordinates': list(rings)}


class TestGeometry:
    def test_inside_outside_and_hole(self):
        assert hl.point_in_geometry(10.2, 10.2, poly(BOX))
        assert not hl.point_in_geometry(12, 10.2, poly(BOX))
        assert not hl.point_in_geometry(10.5, 10.5, poly(BOX, HOLE))
        assert hl.point_in_geometry(10.2, 10.2, poly(BOX, HOLE))

    def test_multipolygon_and_bad_input(self):
        multi = {'type': 'MultiPolygon', 'coordinates': [[BOX], [[[20, 20], [20, 21], [21, 21], [21, 20], [20, 20]]]]}
        assert hl.point_in_geometry(20.5, 20.5, multi)
        assert not hl.point_in_geometry(1, 1, None)
        assert not hl.point_in_geometry(1, 1, {'type': 'Point', 'coordinates': [1, 1]})

    def test_distance_to_track(self):
        track = [feat({'type': 'LineString', 'coordinates': [[0, 0], [2, 0]]})]
        assert hl.distance_to_track_km(0.5, 1, track) == pytest.approx(55.6, abs=1)
        assert hl.distance_to_track_km(0, 3, track) == pytest.approx(111.2, abs=1)    # beyond the end: to the end point
        assert hl.distance_to_track_km(0, 0, []) is None


STORM_FL = {'id': 1, 'event_type': 'FL', 'lat': 10.5, 'lon': 10.5, 'from_date': '2026-10-04T00:00:00',
            'to_date': '2026-10-06T00:00:00'}
STORM_TC = {'id': 2, 'event_type': 'TC', 'lat': 0.0, 'lon': 1.0, 'from_date': '2026-10-01T00:00:00',
            'to_date': '2026-10-08T00:00:00'}


class TestLocate:
    def test_inside_affected_area(self):
        detail = {'area': [feat(poly(BOX), label='Affected area')]}
        assert hl.locate(10.2, 10.2, STORM_FL, detail) == (0.0, 'inside the affected area GDACS outlines', False)

    def test_outside_a_published_footprint_is_no_link_even_if_the_pin_is_close(self):
        detail = {'area': [feat(poly(BOX))]}
        assert hl.locate(10.2, 11.2, {**STORM_FL, 'lat': 11.19, 'lon': 10.2}, detail) is None

    def test_cyclone_wind_zone_uses_the_outermost_60_zone_near_its_own_time(self):
        zones = [feat(poly([[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]), label='120 km/h', as_of='2026-10-05T12:00:00'),
                 feat(poly(BOX), label='60 km/h', as_of='2026-10-05T12:00:00')]
        found = hl.locate(10.2, 10.2, STORM_TC, {'wind_zones': zones}, NOW)
        assert found and found[1] == 'inside the 60 km/h wind zone'

    @pytest.mark.parametrize('when,linked', [
        (NOW, True), (NOW + timedelta(hours=24), True), (NOW - timedelta(hours=24), True),
        (NOW + timedelta(hours=25), False), (NOW - timedelta(days=4), False), (None, False),
    ])
    def test_cyclone_zone_only_counts_within_a_day_of_its_own_time(self, when, linked):
        zones = [feat(poly(BOX), label='60 km/h', as_of='2026-10-05T12:00:00')]
        assert bool(hl.locate(10.2, 10.2, STORM_TC, {'wind_zones': zones}, when)) is linked

    def test_a_zone_with_no_time_never_links(self):
        assert hl.locate(10.2, 10.2, STORM_TC, {'wind_zones': [feat(poly(BOX), label='60 km/h')]}, NOW) is None

    def test_the_track_is_not_used_because_its_segments_have_no_times(self):
        track = [feat({'type': 'LineString', 'coordinates': [[0, 0], [2, 0]]})]
        assert hl.locate(0.5, 1, STORM_TC, {'track': track}, NOW) is None

    def test_segment_across_the_antimeridian_is_not_bent_round_the_globe(self):
        far = [[-125.8, 15.5], [-153.7, 14.0]]
        assert hl._segment_km(15.0, 45.0, *far) > 10000
        across = [[179.5, 10.0], [-179.5, 10.0]]
        assert hl._segment_km(10.0, 180.0, *across) < 1

    def test_no_footprint_falls_back_to_a_radius_and_is_marked_approximate(self):
        close = hl.locate(10.6, 10.5, STORM_FL, None)
        assert close and close[2] is True and 'not published' in close[1]
        assert hl.locate(12, 10.5, STORM_FL, None) is None
        assert hl.locate(10.6, 10.5, STORM_FL, {'track': None, 'wind_zones': None, 'cone': None, 'area': None})

    def test_unknown_hazard_type_has_no_radius(self):
        assert hl.locate(0, 0, {'event_type': 'DR', 'lat': 0, 'lon': 0}, None) is None


class TestTime:
    @pytest.mark.parametrize('when,expected', [
        (datetime(2026, 10, 3, 23), None),               # before the hazard started
        (datetime(2026, 10, 4, 0), 0),                   # at the start
        (datetime(2026, 10, 5, 12), 0),                  # while active
        (datetime(2026, 10, 6, 0), 0),                   # at the end
        (datetime(2026, 10, 7, 0), 24),                  # a day after
        (datetime(2026, 10, 9, 0), 72),                  # edge of the grace period
        (datetime(2026, 10, 9, 1), None),                # just past it
        (None, None),
    ])
    def test_window(self, when, expected):
        assert hl.time_gap_hours(when, STORM_FL) == expected

    def test_a_hazard_without_dates_never_links(self):
        assert hl.time_gap_hours(NOW, {'from_date': None, 'to_date': None}) is None


def seed(db_session, **extra):
    cid = f'hl-{uuid.uuid4().hex[:8]}'
    values = dict(id=cid, type='conflict', title='Collapse near the river', country='Testland', latitude=10.2,
                  longitude=10.2, severity=60, severity_level=4, source='GDELT', is_active=True,
                  event_kind='physical', location_confidence=90, date_start=NOW, source_count=2)
    values.update(extra)
    db_session.add(Crisis(**values))
    db_session.commit()
    return cid


@pytest.fixture(autouse=True)
def clean(app_module, db_session):
    limiter.reset()
    cache_clear_prefix('weather:')
    db_session.query(Crisis).delete()
    db_session.commit()
    yield
    cache_clear_prefix('weather:')


DETAIL = {'area': [feat(poly(BOX), label='Affected area')], 'track': None, 'wind_zones': None, 'cone': None}


def hazards(storms=(STORM_FL,), detail=DETAIL):
    return patch.object(hl, 'get_active_storms', return_value={'storms': list(storms)}), \
        patch.object(hl, 'get_hazard_detail', return_value=detail)


class TestHazardsForEvent:
    def run(self, cid, storms=(STORM_FL,), detail=DETAIL):
        a, b = hazards(storms, detail)
        with a, b:
            return hl.hazards_for_event(cid)

    def test_links_an_event_inside_the_footprint_during_the_hazard(self, db_session):
        result = self.run(seed(db_session))
        assert len(result['links']) == 1
        link = result['links'][0]
        assert link['hazard']['id'] == 1 and link['distance_km'] == 0.0 and link['approximate'] is False
        assert link['basis'] == 'inside the affected area GDACS outlines' and link['hours_after_hazard_ended'] == 0

    def test_unknown_event(self):
        assert self.run('nope') is None

    @pytest.mark.parametrize('extra,reason', [
        ({'event_kind': 'statement'}, 'statement'),
        ({'event_kind': None}, 'statement'),
        ({'location_confidence': 55}, 'approximate_location'),
        ({'location_confidence': 70}, 'approximate_location'),
        ({'merged_into': 'other'}, 'merged'),
        ({'is_active': False}, 'inactive'),
    ])
    def test_ineligible_events_have_no_links_and_say_why(self, db_session, extra, reason):
        assert self.run(seed(db_session, **extra)) == {'links': [], 'reason': reason}

    def test_event_before_the_hazard_or_outside_it_is_not_linked(self, db_session):
        assert self.run(seed(db_session, date_start=datetime(2026, 10, 1)))['links'] == []
        assert self.run(seed(db_session, latitude=10.2, longitude=30.0))['links'] == []

    def test_far_hazards_are_not_even_fetched(self, db_session):
        cid = seed(db_session)
        far = {**STORM_FL, 'lat': 60.0, 'lon': 60.0}
        a, b = hazards((far,))
        with a, patch.object(hl, 'get_hazard_detail') as detail:
            hl.hazards_for_event(cid)
        assert detail.call_count == 0

    def test_hazard_feed_down_is_stated(self, db_session):
        cid = seed(db_session)
        with patch.object(hl, 'get_active_storms', return_value=None):
            assert hl.hazards_for_event(cid) == {'links': [], 'reason': 'hazards_unavailable'}

    def test_failed_geometry_falls_back_to_the_radius_marked_approximate(self, db_session):
        result = self.run(seed(db_session, latitude=10.6, longitude=10.5), detail='unavailable')
        assert result['links'][0]['approximate'] is True


class TestEventsForHazard:
    def run(self, storms=(STORM_FL,), detail=DETAIL, hazard=('FL', 1)):
        a, b = hazards(storms, detail)
        with a, b:
            return hl.events_for_hazard(*hazard)

    def test_lists_matching_events_worst_first(self, db_session):
        low = seed(db_session, severity=30, severity_level=2)
        high = seed(db_session, severity=70, severity_level=4)
        result = self.run()
        assert [e['id'] for e in result['events']] == [high, low]
        assert result['events'][0]['basis'] == 'inside the affected area GDACS outlines'
        assert result['approximate'] is False and result['truncated'] is False

    def test_excludes_everything_the_rules_exclude(self, db_session):
        seed(db_session, event_kind='statement')
        seed(db_session, location_confidence=70)
        seed(db_session, merged_into='x')
        seed(db_session, is_active=False)
        seed(db_session, date_start=datetime(2026, 9, 1))
        seed(db_session, longitude=30.0)
        seed(db_session, latitude=40.0)
        assert self.run()['events'] == []

    def test_unknown_unsupported_or_down(self):
        assert self.run(hazard=('FL', 999)) == 'not_found'
        assert self.run(storms=({**STORM_FL, 'event_type': 'DR'},), hazard=('DR', 1)) == 'not_found'
        with patch.object(hl, 'get_active_storms', return_value=None):
            assert hl.events_for_hazard('FL', 1) == 'unavailable'

    def test_without_a_footprint_it_is_marked_approximate(self, db_session):
        cid = seed(db_session, latitude=10.6, longitude=10.5)
        result = self.run(detail='unavailable')
        assert [e['id'] for e in result['events']] == [cid] and result['approximate'] is True

    def test_result_is_capped(self, db_session):
        with patch.object(hl, 'MAX_EVENTS_PER_HAZARD', 2):
            for _ in range(3):
                seed(db_session)
            result = self.run()
        assert len(result['events']) == 2 and result['truncated'] is True


class TestEndpoints:
    def test_event_hazards(self, client, db_session):
        cid = seed(db_session)
        with patch('blueprints.crises.hazards_for_event', return_value={'links': [], 'reason': None}) as links:
            response = client.get(f'/api/crises/{cid}/hazards')
        assert response.status_code == 200 and links.call_args.args == (cid,)

    def test_event_hazards_follow_a_merged_id_and_404(self, client, db_session):
        primary = seed(db_session)
        merged = seed(db_session, merged_into=primary, is_active=False)
        with patch('blueprints.crises.hazards_for_event', return_value={'links': []}) as links:
            client.get(f'/api/crises/{merged}/hazards')
        assert links.call_args.args == (primary,)
        with patch('blueprints.crises.hazards_for_event', return_value=None):
            assert client.get('/api/crises/nope/hazards').status_code == 404

    @pytest.mark.parametrize('result,status', [({'events': []}, 200), ('not_found', 404), ('unavailable', 503)])
    def test_hazard_events(self, client, result, status):
        with patch('blueprints.weather.events_for_hazard', return_value=result):
            assert client.get('/api/weather/storms/FL/1/events').status_code == status

    @pytest.mark.parametrize('path', ['/api/weather/storms/XX/1/events', '/api/weather/storms/FL/abc/events'])
    def test_bad_ids(self, client, path):
        with patch('blueprints.weather.events_for_hazard') as lookup:
            assert client.get(path).status_code == 400
        assert lookup.call_count == 0

    def test_errors_do_not_leak(self, client, db_session):
        with patch('blueprints.weather.events_for_hazard', side_effect=RuntimeError('secret')):
            response = client.get('/api/weather/storms/FL/1/events')
        assert response.status_code == 500 and 'secret' not in response.get_data(as_text=True)
