"""Hazard detail: GDACS payload parsing, simplification, partial failure, caching and the endpoint.
The GDACS network calls are always mocked; payload shapes mirror the real feed."""
import math
from unittest.mock import patch

import pytest

from cache import cache_clear_prefix
from extensions import limiter
from services import hazard_detail as hd

SQUARE = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]


def feature(cls, geometry, **props):
    return {'type': 'Feature', 'geometry': geometry, 'properties': {'Class': cls, **props}}


def polygon(ring=SQUARE):
    return {'type': 'Polygon', 'coordinates': [ring]}


TC_GEOMETRY = {'features': [
    feature('Point_Centroid', {'type': 'Point', 'coordinates': [1, 2]}),
    feature('Poly_Green', polygon(), polygonlabel='60 km/h'),
    feature('Poly_Orange', polygon(), polygonlabel='90 km/h'),
    feature('Poly_Red', polygon(), polygonlabel='05/10 21:00'),         # a per-time-step footprint: skipped
    feature('Line_Line_0', {'type': 'LineString', 'coordinates': [[-106.6, 17.0], [-107.2, 17.6]]},
            forecast=False, polygonlabel='HU'),
    feature('Line_Line_1', {'type': 'LineString', 'coordinates': [[-107.2, 17.6], [-108.0, 18.1]]},
            forecast=True, polygonlabel='TS'),
    feature('Point_Polygon_Point_0', polygon(), polygonlabel='27/09 09:00 UTC'),
    feature('Poly_Cones', polygon(), polygonlabel='Uncertainty Cones'),
]}


class TestSimplify:
    def test_collinear_points_are_dropped(self):
        line = [[x / 100, 0.0] for x in range(0, 101)]
        assert hd.simplify_line(line) == [[0.0, 0.0], [1.0, 0.0]]

    def test_real_corners_are_kept(self):
        assert len(hd.simplify_line([[0, 0], [0.5, 0.5], [1, 0]])) == 3

    def test_huge_ring_is_capped_and_closed(self):
        ring = [[math.cos(t / 3000 * 6.2832) * 5, math.sin(t / 3000 * 6.2832) * 5] for t in range(3001)]
        simple = hd.simplify_ring(ring)
        assert 4 <= len(simple) <= hd.MAX_RING_POINTS and simple[0] == simple[-1]

    def test_collapsed_ring_is_dropped(self):
        assert hd.simplify_ring([[0, 0], [0, 0.001], [0, 0]]) is None

    def test_multipolygon_and_bad_geometry(self):
        multi = {'type': 'MultiPolygon', 'coordinates': [[SQUARE], [SQUARE]]}
        assert hd.simplify_polygons(multi)['type'] == 'MultiPolygon'
        assert hd.simplify_polygons({'type': 'Point', 'coordinates': [1, 2]}) is None
        assert hd.simplify_polygons(None) is None


class TestParseGeometry:
    def test_cyclone_parts(self):
        parsed = hd.parse_geometry(TC_GEOMETRY, 'TC')
        assert [f['properties']['forecast'] for f in parsed['track']] == [False, True]
        assert [f['properties']['label'] for f in parsed['wind_zones']] == ['60 km/h', '90 km/h']
        assert len(parsed['cone']) == 1 and parsed['area'] is None

    def test_flood_and_fire_area(self):
        for cls in ('Poly_Affected', 'Poly_area'):
            parsed = hd.parse_geometry({'features': [feature(cls, polygon(), polygonlabel='Affected area')]}, 'FL')
            assert parsed['area'] and parsed['track'] is None and parsed['wind_zones'] is None

    def test_nothing_published_is_null_not_empty(self):
        assert hd.parse_geometry({'features': []}, 'TC') == {'track': None, 'wind_zones': None, 'cone': None, 'area': None}
        assert hd.parse_geometry(None, 'FL')['area'] is None


class TestExposureParsing:
    def test_buffer_population(self):
        payload = {'datums': [{'alias': 'Population', 'datum': [{'scalars': {'scalar': [{'name': 'SUMPOP50.0', 'value': '1030'}]}}]}]}
        assert hd.parse_buffer_population(payload) == 1030

    @pytest.mark.parametrize('value', ['', 'n/a', None])
    def test_blank_population_is_null_not_zero(self, value):
        payload = {'datums': [{'alias': 'Population', 'datum': [{'scalars': {'scalar': [{'name': 'x', 'value': value}]}}]}]}
        assert hd.parse_buffer_population(payload) is None

    def test_fire_population(self):
        payload = {'datums': [{'alias': 'POP', 'datum': [{'scalars': {'scalar': [{'name': 'POPAFFECTED', 'value': '2'}]}}]}]}
        assert hd.parse_fire_population(payload) == 2
        assert hd.parse_fire_population({'datums': []}) is None

    def test_sendai_lines(self):
        details = {'sendai': [{'sendainame': 'displaced', 'sendaivalue': '51', 'description': '51 evacuated'},
                              {'sendainame': 'x', 'sendaivalue': ''}, 'junk']}
        items = hd.parse_sendai(details)
        assert items == [{'label': 'Displaced', 'value': 51, 'note': '51 evacuated',
                          'basis': 'reported by authorities via GDACS'}]


STORM = {'id': 1001329, 'episode_id': 35, 'event_type': 'TC', 'date_modified': '2026-10-06T01:16:11', 'name': 'RACHEL-26'}


@pytest.fixture(autouse=True)
def clean():
    cache_clear_prefix('weather:')
    yield
    cache_clear_prefix('weather:')


def feed(storms=(STORM,)):
    return patch.object(hd, 'get_active_storms', return_value={'storms': list(storms)})


class TestGetHazardDetail:
    def test_assembles_geometry_and_exposure(self):
        with feed(), patch.object(hd, '_fetch_geometry', return_value=hd.parse_geometry(TC_GEOMETRY, 'TC')), \
                patch.object(hd, '_fetch_exposure', return_value=[{'label': 'x', 'value': None}]):
            result = hd.get_hazard_detail('TC', '1001329')
        assert result['track'] and result['exposure'] == [{'label': 'x', 'value': None}]
        assert result['unavailable'] == [] and result['source'] == 'gdacs.org'

    def test_unknown_hazard_and_feed_down(self):
        with feed():
            assert hd.get_hazard_detail('TC', '999') == 'not_found'
            assert hd.get_hazard_detail('FL', '1001329') == 'not_found'
        with patch.object(hd, 'get_active_storms', return_value=None):
            assert hd.get_hazard_detail('TC', '1001329') == 'unavailable'

    def test_missing_episode_is_unavailable(self):
        with feed([{**STORM, 'episode_id': None}]):
            assert hd.get_hazard_detail('TC', '1001329') == 'unavailable'

    def test_one_failing_part_does_not_hide_the_other_and_is_not_cached(self):
        geometry = hd.parse_geometry(TC_GEOMETRY, 'TC')
        with feed(), patch.object(hd, '_fetch_geometry', return_value=geometry), \
                patch.object(hd, '_fetch_exposure', side_effect=RuntimeError('down')) as exposure:
            first = hd.get_hazard_detail('TC', '1001329')
            assert first['unavailable'] == ['exposure'] and first['track'] and first['exposure'] is None
            hd.get_hazard_detail('TC', '1001329')
            assert exposure.call_count == 2          # retried, because a partial result is never cached

    def test_complete_result_is_cached_until_the_hazard_is_modified(self):
        geometry = hd.parse_geometry(TC_GEOMETRY, 'TC')
        with feed(), patch.object(hd, '_fetch_geometry', return_value=geometry) as fetch, \
                patch.object(hd, '_fetch_exposure', return_value=[]):
            hd.get_hazard_detail('TC', '1001329')
            hd.get_hazard_detail('TC', '1001329')
            assert fetch.call_count == 1
        with feed([{**STORM, 'date_modified': '2026-10-06T07:00:00'}]), \
                patch.object(hd, '_fetch_geometry', return_value=geometry) as fetch, \
                patch.object(hd, '_fetch_exposure', return_value=[]):
            hd.get_hazard_detail('TC', '1001329')
            assert fetch.call_count == 1             # modified hazard: refetched

    def test_urls_are_rebuilt_from_ids_only(self):
        seen = []
        with patch.object(hd, '_get_json', side_effect=lambda url: seen.append(url) or {'features': []}):
            hd._fetch_geometry({**STORM, 'id': '1001329; evil'.split(';')[0]})
        assert seen == [f'{hd.API}/polygons/getgeometry?eventtype=TC&eventid=1001329&episodeid=35']


class TestEndpoint:
    @pytest.fixture(autouse=True)
    def reset(self, app_module):
        limiter.reset()

    def test_ok(self, client):
        with patch('blueprints.weather.get_hazard_detail', return_value={'id': 1, 'track': None}):
            response = client.get('/api/weather/storms/TC/1')
        assert response.status_code == 200 and response.get_json()['id'] == 1

    @pytest.mark.parametrize('path', ['/api/weather/storms/XX/1', '/api/weather/storms/TC/abc'])
    def test_bad_ids_are_rejected_before_any_lookup(self, client, path):
        with patch('blueprints.weather.get_hazard_detail') as lookup:
            assert client.get(path).status_code == 400
        assert lookup.call_count == 0

    @pytest.mark.parametrize('result,status', [('not_found', 404), ('unavailable', 503)])
    def test_error_codes(self, client, result, status):
        with patch('blueprints.weather.get_hazard_detail', return_value=result):
            assert client.get('/api/weather/storms/TC/1').status_code == status

    def test_unexpected_error_is_a_500_without_details(self, client):
        with patch('blueprints.weather.get_hazard_detail', side_effect=RuntimeError('secret')):
            response = client.get('/api/weather/storms/TC/1')
        assert response.status_code == 500 and 'secret' not in response.get_data(as_text=True)
