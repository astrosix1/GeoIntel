"""Saved drawings: validation and cleaning of what the browser sends, the service layer (against an in-memory fake of the
Supabase REST calls), and the premium-gated /api/me/drawings endpoints."""
import copy
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import jwt
import pytest
import requests

from services import drawings, entitlements, supabase_rest
from services.drawings import (
    DrawingLimitReached, InvalidDrawing, UserDataUnavailable, clean_drawing, clean_name,
    create_drawing, delete_drawing, get_drawing, list_drawings, update_drawing,
)

SECRET = 'jwt-signing-secret'
LAYER = 'layer-1'


_DEFAULT_GEOMETRY = object()


def shape(mode='polygon', geometry=_DEFAULT_GEOMETRY, **props):
    if geometry is _DEFAULT_GEOMETRY:
        geometry = {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    return {'type': 'Feature', 'id': str(uuid.uuid4()), 'geometry': geometry, 'properties': {'mode': mode, 'layer': LAYER, **props}}


def drawing(*features, layers=None):
    return {
        'version': 1,
        'layers': layers or [{'id': LAYER, 'name': 'Layer 1', 'visible': True, 'note': ''}],
        'features': list(features) or [shape()],
    }


class FakeSupabase:
    """Just enough PostgREST for the drawings table."""

    def __init__(self):
        self.rows = []
        self.calls = []
        self.fail = False
        self._clock = 0

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        table = url.rsplit('/', 1)[-1]
        self.calls.append((method, table))
        if self.fail:
            raise requests.ConnectionError('supabase down')
        params = params or {}

        def matches(row):
            return all(row.get(k) == v[3:] for k, v in params.items() if k in ('user_id', 'id') and v.startswith('eq.'))

        def project(row):
            select = params.get('select')
            return {c: row.get(c) for c in select.split(',')} if select else dict(row)

        if method == 'GET':
            found = [r for r in self.rows if matches(r)]
            if params.get('order') == 'updated_at.desc':
                found.sort(key=lambda r: r['updated_at'], reverse=True)
            if 'limit' in params:
                found = found[:int(params['limit'])]
            data = [project(r) for r in found]
        elif method == 'POST':
            data = []
            for incoming in json:
                self._clock += 1
                row = {'id': str(uuid.uuid4()), 'created_at': f'2026-10-01T00:00:{self._clock:02d}+00:00',
                       'updated_at': f'2026-10-01T00:00:{self._clock:02d}+00:00', **copy.deepcopy(incoming)}
                self.rows.append(row)
                data.append(project(row))
        elif method == 'PATCH':
            data = []
            for row in self.rows:
                if matches(row):
                    self._clock += 1
                    row.update(copy.deepcopy(json))
                    row['updated_at'] = f'2026-10-02T00:00:{self._clock:02d}+00:00'
                    data.append(project(row))
        elif method == 'DELETE':
            self.rows = [r for r in self.rows if not matches(r)]
            data = []
        else:
            raise AssertionError(method)
        return SimpleNamespace(json=lambda: data, raise_for_status=lambda: None, status_code=200)


@pytest.fixture()
def supabase(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://proj.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
    fake = FakeSupabase()
    with patch.object(supabase_rest.requests, 'request', fake.request):
        yield fake


def new_user():
    return str(uuid.uuid4())


class TestCleaning:
    def test_a_valid_drawing_comes_back_unchanged_in_substance(self):
        data = drawing(
            shape('linestring', {'type': 'LineString', 'coordinates': [[0, 0], [1, 1]]}, color='#ef4444', width=5, dash='dashed', label='Route', note='n'),
            shape('point', {'type': 'Point', 'coordinates': [5, 6]}),
        )
        out = clean_drawing(data)
        assert out['version'] == 1 and len(out['features']) == 2
        line = out['features'][0]
        assert line['properties'] == {'mode': 'linestring', 'color': '#ef4444', 'width': 5, 'dash': 'dashed', 'label': 'Route', 'note': 'n', 'layer': LAYER}
        assert out['layers'] == [{'id': LAYER, 'name': 'Layer 1', 'visible': True, 'note': ''}]

    def test_unknown_properties_and_keys_are_dropped(self):
        data = drawing(shape(evil='<script>', color='#123456', width=4, fill=0.9, dash='dotted'))
        data['extra'] = 'x'
        data['features'][0]['properties']['__proto__'] = {'a': 1}
        props = clean_drawing(data)['features'][0]['properties']
        assert props == {'mode': 'polygon', 'layer': LAYER}
        assert 'extra' not in clean_drawing(data)

    def test_booleans_and_lists_are_not_taken_for_valid_values(self):
        props = clean_drawing(drawing(shape(width=True, fill=True, color=['#3b82f6'], dash=['dashed'])))['features'][0]['properties']
        assert props == {'mode': 'polygon', 'layer': LAYER}

    def test_text_is_stripped_of_control_characters_and_cut(self):
        out = clean_drawing(drawing(shape(label='a\x00b\nc' + 'x' * 500, note='n\x07ote\nline')))['features'][0]['properties']
        assert '\x00' not in out['label'] and '\n' not in out['label'] and len(out['label']) <= drawings.MAX_LABEL
        assert out['note'] == 'note\nline'

    def test_markup_is_kept_as_plain_text_not_interpreted(self):
        out = clean_drawing(drawing(shape(label='<img src=x onerror=alert(1)>')))['features'][0]['properties']
        assert out['label'] == '<img src=x onerror=alert(1)>'

    def test_an_unknown_layer_is_moved_to_the_first(self):
        out = clean_drawing(drawing(shape(layer='nope')))
        assert out['features'][0]['properties']['layer'] == LAYER

    def test_layers_are_cleaned_and_at_least_one_is_required(self):
        out = clean_drawing(drawing(layers=[{'id': 'a', 'name': 'A', 'visible': False, 'note': 'x'}, {'id': 'a', 'name': 'dup'}, {'id': 'bad id'}, 5]))
        assert [(l['id'], l['visible']) for l in out['layers']] == [('a', False)]
        with pytest.raises(InvalidDrawing) as exc:
            clean_drawing(drawing(layers=[{'id': 'bad id'}]))
        assert exc.value.reason == 'layers'

    def test_layers_are_capped(self):
        many = [{'id': f'l{i}', 'name': f'L{i}'} for i in range(drawings.MAX_LAYERS + 10)]
        assert len(clean_drawing(drawing(layers=many))['layers']) == drawings.MAX_LAYERS

    @pytest.mark.parametrize('bad', [None, [], 'x', {'version': 2, 'layers': [], 'features': []}, {'layers': [], 'features': []}])
    def test_wrong_version_or_shape_is_rejected(self, bad):
        with pytest.raises(InvalidDrawing):
            clean_drawing(bad)

    @pytest.mark.parametrize('geometry', [
        None, {}, {'type': 'MultiPolygon', 'coordinates': []}, {'type': 'Point', 'coordinates': [200, 0, 5, 5]},
        {'type': 'Point', 'coordinates': ['a', 1]}, {'type': 'Point', 'coordinates': [True, 1]}, {'type': 'Point', 'coordinates': [0, 91]},
        {'type': 'Point', 'coordinates': [600, 0]}, {'type': 'Point', 'coordinates': [float('nan'), 0]}, {'type': 'Point', 'coordinates': [float('inf'), 0]},
        {'type': 'LineString', 'coordinates': [[0, 0]]}, {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 1], [0, 0]]]}, {'type': 'Polygon', 'coordinates': []},
    ])
    def test_bad_geometry_is_rejected(self, geometry):
        with pytest.raises(InvalidDrawing):
            clean_drawing(drawing(shape('polygon', geometry)))

    def test_a_mode_must_be_one_the_tool_knows(self):
        with pytest.raises(InvalidDrawing) as exc:
            clean_drawing(drawing(shape('freestyle')))
        assert exc.value.reason == 'mode'

    def test_limits_on_shapes_vertices_and_size(self, monkeypatch):
        monkeypatch.setattr(drawings, 'MAX_FEATURES', 2)
        with pytest.raises(InvalidDrawing) as exc:
            clean_drawing(drawing(shape(), shape(), shape()))
        assert exc.value.reason == 'too_many_shapes'
        monkeypatch.setattr(drawings, 'MAX_FEATURES', 500)
        monkeypatch.setattr(drawings, 'MAX_VERTICES', 6)
        with pytest.raises(InvalidDrawing) as exc:
            clean_drawing(drawing(shape(), shape()))
        assert exc.value.reason == 'too_many_vertices'
        monkeypatch.setattr(drawings, 'MAX_VERTICES', 20000)
        monkeypatch.setattr(drawings, 'MAX_BYTES', 200)
        with pytest.raises(InvalidDrawing) as exc:
            clean_drawing(drawing(shape(note='x' * 1000)))
        assert exc.value.reason == 'too_large'

    def test_names(self):
        assert clean_name('  Gulf scenarios  ') == 'Gulf scenarios'
        assert clean_name('a\nb\x00c') == 'a b c'
        assert len(clean_name('n' * 500)) == drawings.MAX_NAME
        for bad in ['', '   ', None, 5, ['x']]:
            with pytest.raises(InvalidDrawing):
                clean_name(bad)


class TestService:
    def test_create_stores_the_cleaned_drawing_with_counts(self, supabase):
        uid = new_user()
        saved = create_drawing(uid, ' Plan A ', drawing(shape(evil='x'), shape(), layers=[{'id': LAYER, 'name': 'L'}, {'id': 'b', 'name': 'B'}]))
        row = supabase.rows[0]
        assert row['user_id'] == uid and row['name'] == 'Plan A'
        assert row['shape_count'] == 2 and row['layer_count'] == 2
        assert 'evil' not in row['data']['features'][0]['properties']
        assert saved['id'] == row['id']

    def test_list_is_newest_first_without_contents_and_only_the_users_own(self, supabase):
        alice, bob = new_user(), new_user()
        create_drawing(alice, 'first', drawing())
        create_drawing(alice, 'second', drawing())
        create_drawing(bob, 'bobs', drawing())
        listed = list_drawings(alice)
        assert [d['name'] for d in listed] == ['second', 'first']
        assert all('data' not in d for d in listed)
        assert [d['name'] for d in list_drawings(bob)] == ['bobs']

    def test_get_returns_the_contents_and_never_another_users_drawing(self, supabase):
        alice, bob = new_user(), new_user()
        saved = create_drawing(alice, 'mine', drawing())
        assert get_drawing(alice, saved['id'])['data']['version'] == 1
        assert get_drawing(bob, saved['id']) is None

    def test_a_malformed_id_is_not_found_and_makes_no_request(self, supabase):
        assert get_drawing(new_user(), "x' or 1=1") is None
        assert update_drawing(new_user(), 'not-a-uuid', name='x') is None
        delete_drawing(new_user(), 'not-a-uuid')
        assert supabase.calls == []

    def test_update_renames_and_replaces_only_the_users_own(self, supabase):
        alice, bob = new_user(), new_user()
        saved = create_drawing(alice, 'old', drawing())
        assert update_drawing(bob, saved['id'], name='stolen') is None
        assert supabase.rows[0]['name'] == 'old'
        out = update_drawing(alice, saved['id'], name='new', data=drawing(shape(), shape(), shape()))
        assert out['name'] == 'new' and out['shape_count'] == 3
        renamed = update_drawing(alice, saved['id'], name='again')
        assert renamed['name'] == 'again' and renamed['shape_count'] == 3

    def test_update_validates_before_writing(self, supabase):
        uid = new_user()
        saved = create_drawing(uid, 'x', drawing())
        before = list(supabase.calls)
        with pytest.raises(InvalidDrawing):
            update_drawing(uid, saved['id'], data={'version': 1, 'layers': [], 'features': []})
        with pytest.raises(InvalidDrawing):
            update_drawing(uid, saved['id'], name='   ')
        assert supabase.calls == before

    def test_delete_removes_only_the_users_own(self, supabase):
        alice, bob = new_user(), new_user()
        saved = create_drawing(alice, 'x', drawing())
        delete_drawing(bob, saved['id'])
        assert len(supabase.rows) == 1
        delete_drawing(alice, saved['id'])
        assert supabase.rows == []

    def test_the_count_limit_blocks_new_drawings(self, supabase, monkeypatch):
        monkeypatch.setattr(drawings, 'MAX_DRAWINGS', 2)
        uid = new_user()
        create_drawing(uid, 'a', drawing())
        create_drawing(uid, 'b', drawing())
        with pytest.raises(DrawingLimitReached):
            create_drawing(uid, 'c', drawing())
        # another user is unaffected
        create_drawing(new_user(), 'c', drawing())

    def test_invalid_drawings_write_nothing(self, supabase):
        with pytest.raises(InvalidDrawing):
            create_drawing(new_user(), 'x', {'version': 9})
        assert supabase.calls == []

    def test_unconfigured_and_failing_storage(self, supabase, monkeypatch):
        supabase.fail = True
        with pytest.raises(UserDataUnavailable) as exc:
            list_drawings(new_user())
        assert exc.value.reason == 'request_failed'
        monkeypatch.delenv('SUPABASE_URL', raising=False)
        with pytest.raises(UserDataUnavailable) as exc:
            list_drawings(new_user())
        assert exc.value.reason == 'not_configured'

    def test_a_bad_user_id_makes_no_request(self, supabase):
        with pytest.raises(UserDataUnavailable):
            list_drawings("x' or 1=1")
        assert supabase.calls == []


def _token(uid):
    return jwt.encode({'sub': uid, 'aud': 'authenticated', 'exp': int(time.time()) + 3600}, SECRET, algorithm='HS256')


@pytest.fixture()
def secret(monkeypatch):
    monkeypatch.setenv('SUPABASE_JWT_SECRET', SECRET)


def call(client, method, path, uid=None, plan='active', **kwargs):
    headers = {'Authorization': f'Bearer {_token(uid)}'} if uid else {}
    row = {'status': plan} if plan else None
    with patch.object(entitlements, '_fetch_subscription', return_value=row):
        return getattr(client, method)(path, headers=headers, **kwargs)


ROUTES = [('get', '/api/me/drawings'), ('post', '/api/me/drawings'), ('get', '/api/me/drawings/x'),
          ('put', '/api/me/drawings/x'), ('delete', '/api/me/drawings/x')]


class TestEndpoints:
    @pytest.mark.parametrize('method,path', ROUTES)
    def test_anonymous_gets_401(self, client, secret, method, path):
        assert call(client, method, path).status_code == 401

    @pytest.mark.parametrize('method,path', ROUTES)
    def test_free_user_gets_403_and_touches_nothing(self, client, secret, supabase, method, path):
        res = call(client, method, path, new_user(), plan=None, json={'name': 'x', 'data': drawing()})
        assert res.status_code == 403
        assert supabase.calls == []

    def test_the_switch_that_opens_premium_still_needs_a_sign_in(self, client, secret, supabase, monkeypatch):
        monkeypatch.setenv('PREMIUM_FOR_ALL', 'true')
        assert call(client, 'get', '/api/me/drawings').status_code == 401
        assert call(client, 'get', '/api/me/drawings', new_user(), plan=None).status_code == 200

    def test_create_list_open_rename_delete_round_trip(self, client, secret, supabase):
        uid = new_user()
        res = call(client, 'post', '/api/me/drawings', uid, json={'name': 'Gulf', 'data': drawing(shape(label='Zone A'))})
        assert res.status_code == 201
        created = res.get_json()['drawing']
        assert created['name'] == 'Gulf' and 'user_id' not in created
        listed = call(client, 'get', '/api/me/drawings', uid).get_json()
        assert [d['name'] for d in listed['drawings']] == ['Gulf'] and listed['limit'] == drawings.MAX_DRAWINGS
        opened = call(client, 'get', f"/api/me/drawings/{created['id']}", uid).get_json()['drawing']
        assert opened['data']['features'][0]['properties']['label'] == 'Zone A'
        renamed = call(client, 'put', f"/api/me/drawings/{created['id']}", uid, json={'name': 'Gulf v2'}).get_json()['drawing']
        assert renamed['name'] == 'Gulf v2' and renamed['data']['features']
        assert call(client, 'delete', f"/api/me/drawings/{created['id']}", uid).status_code == 204
        assert call(client, 'get', '/api/me/drawings', uid).get_json()['drawings'] == []

    def test_users_cannot_reach_each_others_drawings(self, client, secret, supabase):
        alice, bob = new_user(), new_user()
        created = call(client, 'post', '/api/me/drawings', alice, json={'name': 'mine', 'data': drawing()}).get_json()['drawing']
        path = f"/api/me/drawings/{created['id']}"
        assert call(client, 'get', path, bob).status_code == 404
        assert call(client, 'put', path, bob, json={'name': 'x'}).status_code == 404
        call(client, 'delete', path, bob)
        assert call(client, 'get', path, alice).status_code == 200
        assert call(client, 'get', '/api/me/drawings', bob).get_json()['drawings'] == []

    def test_a_missing_or_malformed_drawing_is_404(self, client, secret, supabase):
        uid = new_user()
        assert call(client, 'get', f'/api/me/drawings/{uuid.uuid4()}', uid).status_code == 404
        assert call(client, 'get', '/api/me/drawings/not-a-uuid', uid).status_code == 404

    @pytest.mark.parametrize('body', [None, [], {}, {'name': 'x'}, {'data': 1}, {'name': '', 'data': None}])
    def test_a_bad_body_is_400(self, client, secret, supabase, body):
        res = call(client, 'post', '/api/me/drawings', new_user(), json=body)
        assert res.status_code == 400
        assert res.get_json()['error'] == 'invalid_drawing'

    @pytest.mark.parametrize('data,reason', [
        ({'version': 1, 'layers': [], 'features': []}, 'layers'),
        (drawing(shape('nope')), 'mode'),
        (drawing(shape('polygon', {'type': 'Point', 'coordinates': [999, 0]})), 'coordinates'),
    ])
    def test_an_invalid_drawing_is_400_with_a_reason(self, client, secret, supabase, data, reason):
        res = call(client, 'post', '/api/me/drawings', new_user(), json={'name': 'x', 'data': data})
        assert res.status_code == 400 and res.get_json()['reason'] == reason
        assert supabase.rows == []

    def test_an_empty_name_is_400(self, client, secret, supabase):
        res = call(client, 'post', '/api/me/drawings', new_user(), json={'name': '  ', 'data': drawing()})
        assert res.status_code == 400 and res.get_json()['reason'] == 'name'

    def test_the_limit_is_409(self, client, secret, supabase, monkeypatch):
        monkeypatch.setattr(drawings, 'MAX_DRAWINGS', 1)
        uid = new_user()
        call(client, 'post', '/api/me/drawings', uid, json={'name': 'a', 'data': drawing()})
        res = call(client, 'post', '/api/me/drawings', uid, json={'name': 'b', 'data': drawing()})
        assert res.status_code == 409 and res.get_json()['error'] == 'drawing_limit_reached'

    def test_a_huge_body_is_413_before_it_is_read(self, client, secret, supabase, monkeypatch):
        monkeypatch.setattr(drawings, 'MAX_BYTES', 500)
        monkeypatch.setattr('blueprints.drawings.MAX_BYTES', 500)
        res = call(client, 'post', '/api/me/drawings', new_user(), json={'name': 'x', 'data': drawing(shape(note='x' * 6000))})
        assert res.status_code == 413
        assert supabase.rows == []

    def test_a_drawing_over_the_limit_is_413(self, client, secret, supabase, monkeypatch):
        monkeypatch.setattr(drawings, 'MAX_BYTES', 400)
        res = call(client, 'post', '/api/me/drawings', new_user(), json={'name': 'x', 'data': drawing(shape(note='y' * 1500))})
        assert res.status_code == 413

    def test_storage_down_is_503(self, client, secret, supabase):
        supabase.fail = True
        res = call(client, 'get', '/api/me/drawings', new_user())
        assert res.status_code == 503 and res.get_json()['error'] == 'user_data_unavailable'


class TestHighlighter:
    def stroke(self, **props):
        return shape('highlighter', {'type': 'LineString', 'coordinates': [[0, 0], [1, 1], [2, 0]]}, **props)

    def test_a_highlighter_stroke_with_marker_colour_and_thickness_is_kept(self):
        out = clean_drawing(drawing(self.stroke(color='#f472b6', width=32, label='Zone')))['features'][0]['properties']
        assert out == {'mode': 'highlighter', 'color': '#f472b6', 'width': 32, 'label': 'Zone', 'layer': LAYER}

    @pytest.mark.parametrize('color,width', [('#123456', 13), ('red', 7), (['#facc15'], True)])
    def test_other_colours_and_thicknesses_are_still_dropped(self, color, width):
        out = clean_drawing(drawing(self.stroke(color=color, width=width)))['features'][0]['properties']
        assert out == {'mode': 'highlighter', 'layer': LAYER}

    def test_every_marker_value_is_accepted_and_nothing_else_was_loosened(self):
        for colour in drawings.HIGHLIGHT_COLORS:
            assert clean_drawing(drawing(self.stroke(color=colour)))['features'][0]['properties']['color'] == colour
        for width in drawings.HIGHLIGHT_WIDTHS:
            assert clean_drawing(drawing(self.stroke(width=width)))['features'][0]['properties']['width'] == width
        assert drawings.COLORS == {'#3b82f6', '#ef4444', '#22c55e', '#a855f7', '#0f172a', '#ffffff'}
        assert drawings.WIDTHS == {2, 3, 5}
