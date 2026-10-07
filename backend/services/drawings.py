"""Saved drawings (premium): the shapes, layers and notes a user draws on the map, stored per user in Supabase.

The table (backend/supabase/006_geointel_drawings.sql) has row level security with no policies, so only this backend's
service-role key reaches it. Every function takes the *verified* user id and scopes every query by it; premium is enforced
by the caller (@require_premium). Nothing the browser sends is stored as it came: `clean_drawing` rebuilds the drawing from
a short list of allowed shapes, fields and values, so what is stored (and later sent back to other pages) is only ever
plain geometry, a few styling choices and text."""
import json
import logging
import re
import uuid
from datetime import datetime, timezone

from services.supabase_rest import SupabaseUnavailable, check_uuid, rest

logger = logging.getLogger(__name__)

MAX_DRAWINGS = 50
MAX_BYTES = 1_000_000  # of JSON, per drawing
MAX_FEATURES = 500
MAX_VERTICES = 20_000  # across the whole drawing
MAX_LAYERS = 20
MAX_NAME = 80
MAX_LAYER_NAME = 60
MAX_LABEL = 80
MAX_NOTE = 2000
DATA_VERSION = 1

# These mirror frontend/src/globe/draw/style.ts: the palette and the steps the tool offers.
COLORS = {'#3b82f6', '#ef4444', '#22c55e', '#a855f7', '#0f172a', '#ffffff'}
WIDTHS = {2, 3, 5}
FILLS = {0, 0.2, 0.4}
DASHES = {'solid', 'dashed'}
MODES = {'point', 'text', 'linestring', 'arrow', 'angle', 'polygon', 'rectangle', 'circle', 'freehand'}
GEOMETRIES = {'Point', 'LineString', 'Polygon'}

_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
_CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_CONTROL_NAME = re.compile(r'[\x00-\x1f\x7f]')

UserDataUnavailable = SupabaseUnavailable


class InvalidDrawing(ValueError):
    """The drawing (or its name) is not acceptable. `reason` is a short machine-readable code."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class DrawingLimitReached(Exception):
    pass


def _text(value, limit, *, multiline):
    if not isinstance(value, str):
        return None
    cleaned = (_CONTROL if multiline else _CONTROL_NAME).sub('' if multiline else ' ', value)
    cleaned = cleaned[:limit]
    return cleaned if cleaned.strip() else None


def clean_name(value):
    name = _text(value, MAX_NAME, multiline=False)
    name = name.strip() if name else None
    if not name:
        raise InvalidDrawing('name')
    return name


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) != float('inf')


def _position(value):
    if not isinstance(value, (list, tuple)) or len(value) not in (2, 3):
        raise InvalidDrawing('coordinates')
    if not all(_number(v) for v in value):
        raise InvalidDrawing('coordinates')
    lon, lat = value[0], value[1]
    # A drawing made across the date line on a flat map can run past 180; anything wilder is not a place.
    if not (-540 <= lon <= 540 and -90 <= lat <= 90):
        raise InvalidDrawing('coordinates')
    return [lon, lat]


def _geometry(geometry):
    if not isinstance(geometry, dict) or geometry.get('type') not in GEOMETRIES:
        raise InvalidDrawing('geometry')
    kind, coords = geometry['type'], geometry.get('coordinates')
    if kind == 'Point':
        points = [_position(coords)]
        return {'type': kind, 'coordinates': points[0]}, 1
    if kind == 'LineString':
        if not isinstance(coords, list) or len(coords) < 2:
            raise InvalidDrawing('geometry')
        line = [_position(p) for p in coords]
        return {'type': kind, 'coordinates': line}, len(line)
    if not isinstance(coords, list) or not coords or len(coords) > 10:
        raise InvalidDrawing('geometry')
    rings, count = [], 0
    for ring in coords:
        if not isinstance(ring, list) or len(ring) < 4:
            raise InvalidDrawing('geometry')
        cleaned = [_position(p) for p in ring]
        count += len(cleaned)
        rings.append(cleaned)
    return {'type': kind, 'coordinates': rings}, count


def _properties(props, layer_ids, default_layer):
    props = props if isinstance(props, dict) else {}
    mode = props.get('mode')
    if not isinstance(mode, str) or mode not in MODES:
        raise InvalidDrawing('mode')
    out = {'mode': mode}
    if isinstance(props.get('color'), str) and props['color'] in COLORS:
        out['color'] = props['color']
    # bool is an int in Python, so True would pass for a width of 1 without this check.
    if _number(props.get('width')) and props['width'] in WIDTHS:
        out['width'] = props['width']
    if _number(props.get('fill')) and props['fill'] in FILLS:
        out['fill'] = props['fill']
    if isinstance(props.get('dash'), str) and props['dash'] in DASHES:
        out['dash'] = props['dash']
    label = _text(props.get('label'), MAX_LABEL, multiline=False)
    if label:
        out['label'] = label.strip()
    note = _text(props.get('note'), MAX_NOTE, multiline=True)
    if note:
        out['note'] = note
    layer = props.get('layer')
    out['layer'] = layer if isinstance(layer, str) and layer in layer_ids else default_layer
    return out


def _layers(value):
    if not isinstance(value, list):
        raise InvalidDrawing('layers')
    layers, seen = [], set()
    for item in value[:MAX_LAYERS]:
        if not isinstance(item, dict):
            continue
        layer_id = item.get('id')
        if not isinstance(layer_id, str) or not _ID_RE.match(layer_id) or layer_id in seen:
            continue
        seen.add(layer_id)
        name = _text(item.get('name'), MAX_LAYER_NAME, multiline=False)
        layers.append({
            'id': layer_id,
            'name': name.strip() if name else f'Layer {len(layers) + 1}',
            'visible': item.get('visible') is not False,
            'note': _text(item.get('note'), MAX_NOTE, multiline=True) or '',
        })
    if not layers:
        raise InvalidDrawing('layers')
    return layers


def clean_drawing(data):
    """The drawing rebuilt from allowed parts only. Raises InvalidDrawing (with a reason code) if it cannot be."""
    if not isinstance(data, dict) or data.get('version') != DATA_VERSION:
        raise InvalidDrawing('version')
    try:
        size = len(json.dumps(data, separators=(',', ':')))
    except (TypeError, ValueError) as e:
        raise InvalidDrawing('format') from e
    if size > MAX_BYTES:
        raise InvalidDrawing('too_large')
    layers = _layers(data.get('layers'))
    layer_ids = {layer['id'] for layer in layers}
    raw = data.get('features')
    if not isinstance(raw, list):
        raise InvalidDrawing('features')
    if len(raw) > MAX_FEATURES:
        raise InvalidDrawing('too_many_shapes')
    features, vertices = [], 0
    for item in raw:
        if not isinstance(item, dict) or item.get('type') != 'Feature':
            raise InvalidDrawing('features')
        geometry, count = _geometry(item.get('geometry'))
        vertices += count
        if vertices > MAX_VERTICES:
            raise InvalidDrawing('too_many_vertices')
        feature = {'type': 'Feature', 'geometry': geometry, 'properties': _properties(item.get('properties'), layer_ids, layers[0]['id'])}
        feature_id = item.get('id')
        if isinstance(feature_id, str) and _ID_RE.match(feature_id):
            feature['id'] = feature_id
        features.append(feature)
    return {'version': DATA_VERSION, 'layers': layers, 'features': features}


_SUMMARY = 'id,name,shape_count,layer_count,created_at,updated_at'
_FULL = 'id,name,data,shape_count,layer_count,created_at,updated_at'


def _drawing_id(value):
    """The canonical drawing id, or None if it is not a UUID (so a bad id is a 404, never a query)."""
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        return None


def list_drawings(user_id):
    """The user's drawings, most recently changed first, without their contents."""
    uid = check_uuid(user_id)
    return rest('GET', 'geointel_drawings', params={
        'user_id': f'eq.{uid}', 'select': _SUMMARY, 'order': 'updated_at.desc', 'limit': str(MAX_DRAWINGS),
    }).json()


def get_drawing(user_id, drawing_id):
    uid = check_uuid(user_id)
    did = _drawing_id(drawing_id)
    if did is None:
        return None
    rows = rest('GET', 'geointel_drawings', params={
        'user_id': f'eq.{uid}', 'id': f'eq.{did}', 'select': _FULL, 'limit': '1',
    }).json()
    return rows[0] if rows else None


def create_drawing(user_id, name, data):
    uid = check_uuid(user_id)
    clean = clean_drawing(data)
    title = clean_name(name)
    existing = rest('GET', 'geointel_drawings', params={
        'user_id': f'eq.{uid}', 'select': 'id', 'limit': str(MAX_DRAWINGS + 1),
    }).json()
    if len(existing) >= MAX_DRAWINGS:
        raise DrawingLimitReached()
    rows = rest('POST', 'geointel_drawings', params={'select': _FULL}, json_body=[{
        'user_id': uid, 'name': title, 'data': clean,
        'shape_count': len(clean['features']), 'layer_count': len(clean['layers']),
    }], prefer='return=representation').json()
    return rows[0] if rows else None


def update_drawing(user_id, drawing_id, name=None, data=None):
    """Renames and/or replaces the contents of one of the user's drawings. None if it is not theirs or does not exist."""
    uid = check_uuid(user_id)
    did = _drawing_id(drawing_id)
    if did is None:
        return None
    change = {'updated_at': datetime.now(timezone.utc).isoformat()}
    if name is not None:
        change['name'] = clean_name(name)
    if data is not None:
        clean = clean_drawing(data)
        change.update({'data': clean, 'shape_count': len(clean['features']), 'layer_count': len(clean['layers'])})
    rows = rest('PATCH', 'geointel_drawings', params={'user_id': f'eq.{uid}', 'id': f'eq.{did}', 'select': _FULL},
                json_body=change, prefer='return=representation').json()
    return rows[0] if rows else None


def delete_drawing(user_id, drawing_id):
    uid = check_uuid(user_id)
    did = _drawing_id(drawing_id)
    if did is None:
        return
    rest('DELETE', 'geointel_drawings', params={'user_id': f'eq.{uid}', 'id': f'eq.{did}'})
