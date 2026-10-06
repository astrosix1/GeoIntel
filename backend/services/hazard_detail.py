"""Detail for one active hazard: its track, footprint and people exposed.

All of it comes from GDACS's own per-event data (the geometry and impact links
the event feed points to). Nothing is estimated here:
  * a hazard type with no track or footprint in the feed simply has none;
  * a population number that GDACS leaves blank is returned as null, not 0;
  * a part that cannot be fetched is reported as unavailable on its own, so one
    failing link does not hide the rest.

Only hazards in the current active list can be asked for, and only fixed GDACS
hosts are ever contacted (the ids are rebuilt into URLs here, never taken from
the caller).
"""
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

from cache import cache_get, cache_set
from services.weather import get_active_storms

logger = logging.getLogger(__name__)

API = 'https://www.gdacs.org/gdacsapi/api'
TIMEOUT = 15
CACHE_TTL = 15 * 60
# Coordinates are simplified to roughly this many degrees (about 1 km) so a flood
# outline of 350 KB becomes a few KB.
SIMPLIFY_DEGREES = 0.01
MAX_RING_POINTS = 400

# Wind zones GDACS draws around a cyclone: its polygon labels end in "km/h".
_WIND_LABEL_SUFFIX = 'km/h'
_AREA_CLASSES = ('Poly_Affected', 'Poly_area')
_TC_BUFFERS = (
    ('buffer74', 'Within hurricane-force winds (119 km/h or more)'),
    ('buffer39', 'Within tropical-storm-force winds (63 km/h or more)'),
)


# --- geometry helpers -----------------------------------------------------------

def _perpendicular(point, start, end):
    (x, y), (x1, y1), (x2, y2) = point, start, end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def simplify_line(points, tolerance=SIMPLIFY_DEGREES):
    """Ramer-Douglas-Peucker, iterative so a huge outline cannot overflow the stack."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        lo, hi = stack.pop()
        worst, index = 0.0, None
        for i in range(lo + 1, hi):
            d = _perpendicular(points[i], points[lo], points[hi])
            if d > worst:
                worst, index = d, i
        if index is not None and worst > tolerance:
            keep[index] = True
            stack.append((lo, index))
            stack.append((index, hi))
    return [p for p, k in zip(points, keep) if k]


def simplify_ring(ring):
    """A closed ring simplified, or None when too little of it is left to draw."""
    tolerance = SIMPLIFY_DEGREES
    points = [[float(p[0]), float(p[1])] for p in ring if len(p) >= 2]
    simple = simplify_line(points, tolerance)
    while len(simple) > MAX_RING_POINTS:
        tolerance *= 1.6
        simple = simplify_line(points, tolerance)
    simple = [[round(x, 3), round(y, 3)] for x, y in simple]
    return simple if len(simple) >= 4 else None


def simplify_polygons(geometry):
    """A Polygon or MultiPolygon geometry with every ring simplified (rings that
    collapse are dropped). None when nothing drawable is left."""
    if not isinstance(geometry, dict):
        return None
    kind, coords = geometry.get('type'), geometry.get('coordinates')
    if kind == 'Polygon':
        polygons = [coords]
    elif kind == 'MultiPolygon':
        polygons = coords
    else:
        return None
    result = []
    for polygon in polygons or []:
        rings = [simplify_ring(r) for r in polygon or []]
        if rings and rings[0]:
            result.append([r for r in rings if r])
    if not result:
        return None
    return {'type': 'Polygon', 'coordinates': result[0]} if len(result) == 1 else \
        {'type': 'MultiPolygon', 'coordinates': result}


def _feature(geometry, **properties):
    return {'type': 'Feature', 'geometry': geometry, 'properties': properties}


# --- parsing GDACS payloads ----------------------------------------------------

def parse_geometry(payload, event_type):
    """{'track', 'wind_zones', 'cone', 'area'} from a GDACS geometry payload; each
    is a list of GeoJSON features or None when the feed has none for this event."""
    features = payload.get('features') if isinstance(payload, dict) else None
    track, zones, cone, area = [], [], [], []
    for feat in features or []:
        props = feat.get('properties') or {}
        geometry = feat.get('geometry') or {}
        cls = props.get('Class') or ''
        gtype = geometry.get('type')
        if event_type == 'TC' and gtype == 'LineString' and cls.startswith('Line_'):
            coords = geometry.get('coordinates') or []
            if len(coords) >= 2:
                track.append(_feature({'type': 'LineString', 'coordinates': coords},
                                      forecast=bool(props.get('forecast')), category=props.get('polygonlabel')))
        elif event_type == 'TC' and cls in ('Poly_Green', 'Poly_Orange', 'Poly_Red'):
            label = props.get('polygonlabel') or ''
            if label.endswith(_WIND_LABEL_SUFFIX):     # the current wind zones, not the per-time-step ones
                simple = simplify_polygons(geometry)
                if simple:
                    zones.append(_feature(simple, label=label, level=cls.split('_')[1], as_of=props.get('polygondate')))
        elif event_type == 'TC' and cls == 'Poly_Cones':
            simple = simplify_polygons(geometry)
            if simple:
                cone.append(_feature(simple, label='Forecast uncertainty'))
        elif cls in _AREA_CLASSES:
            simple = simplify_polygons(geometry)
            if simple:
                area.append(_feature(simple, label=props.get('polygonlabel') or 'Affected area'))
    return {'track': track or None, 'wind_zones': zones or None, 'cone': cone or None, 'area': area or None}


def _population(scalars):
    """Int from a GDACS scalar list value, or None when blank / not a number."""
    for item in (scalars or {}).get('scalar') or []:
        value = item.get('value')
        if isinstance(value, str) and value.strip().lstrip('-').isdigit():
            return int(value.strip())
    return None


def _scalar(datums, alias, name):
    for datum in datums or []:
        if (datum.get('alias') or '').lower() != alias.lower():
            continue
        for entry in datum.get('datum') or []:
            for item in (entry.get('scalars') or {}).get('scalar') or []:
                if item.get('name') == name:
                    value = item.get('value')
                    if isinstance(value, str) and value.strip().isdigit():
                        return int(value.strip())
    return None


def parse_buffer_population(payload):
    """People within a cyclone wind buffer, or None when GDACS left it blank."""
    for datum in (payload or {}).get('datums') or []:
        if (datum.get('alias') or '') == 'Population':
            for entry in datum.get('datum') or []:
                return _population(entry.get('scalars'))
    return None


def parse_fire_population(payload):
    value = _scalar((payload or {}).get('datums'), 'POP', 'POPAFFECTED')
    return value


def parse_sendai(details):
    """Authority-reported impact lines for a flood (e.g. people displaced)."""
    items = []
    for entry in (details.get('sendai') or []) if isinstance(details, dict) else []:
        if not isinstance(entry, dict):
            continue
        name, value = entry.get('sendainame'), entry.get('sendaivalue')
        if not name or value in (None, ''):
            continue
        items.append({
            'label': str(name).capitalize(),
            'value': int(value) if str(value).isdigit() else None,
            'note': (entry.get('description') or '')[:200] or None,
            'basis': 'reported by authorities via GDACS',
        })
    return items[:6]


# --- fetching -----------------------------------------------------------------

def _get_json(url):
    response = requests.get(url, timeout=TIMEOUT, headers={'User-Agent': 'GeoIntel/1.0'})
    response.raise_for_status()
    return response.json()


def _fetch_geometry(storm):
    url = f"{API}/polygons/getgeometry?eventtype={storm['event_type']}&eventid={int(storm['id'])}&episodeid={int(storm['episode_id'])}"
    return parse_geometry(_get_json(url), storm['event_type'])


def _fetch_exposure(storm):
    """List of {label, value, note, basis}; raises on an unreachable details feed."""
    event_type = storm['event_type']
    details = _get_json(f"{API}/events/geteventdata?eventtype={event_type}&eventid={int(storm['id'])}")
    props = details.get('properties') or {}
    items = []
    impacts = props.get('impacts') or []
    resources = (impacts[0].get('resource') or {}) if impacts and isinstance(impacts[0], dict) else {}
    if event_type == 'TC':
        for key, label in _TC_BUFFERS:
            url = resources.get(key)
            if not url:
                continue
            try:
                value = parse_buffer_population(_get_json(url))
            except Exception as e:
                logger.info(f"[hazard_detail] {key} unavailable: {e}")
                continue
            items.append({'label': label, 'value': value, 'note': None, 'basis': 'GDACS population estimate'})
    elif event_type == 'WF':
        url = resources.get('impact')
        if url:
            try:
                value = parse_fire_population(_get_json(url))
            except Exception as e:
                logger.info(f"[hazard_detail] fire impact unavailable: {e}")
                value = None
            if value is not None:
                items.append({'label': 'People affected', 'value': value, 'note': None, 'basis': 'GDACS population estimate'})
    elif event_type == 'FL':
        items.extend(parse_sendai(props))
    return items


def _hazard(event_type, event_id):
    result = get_active_storms()
    if result is None:
        return None, 'unavailable'
    for storm in result['storms']:
        if storm.get('event_type') == event_type and str(storm.get('id')) == str(event_id):
            return storm, None
    return None, 'not_found'


def get_hazard_detail(event_type, event_id):
    """{'id', 'event_type', 'track', 'wind_zones', 'cone', 'area', 'exposure',
    'unavailable': [...], 'generated_at'}, or a string error code:
    'not_found' (not an active hazard) or 'unavailable' (the GDACS list is down)."""
    storm, error = _hazard(event_type, event_id)
    if storm is None:
        return error
    if storm.get('episode_id') is None:
        return 'unavailable'

    key = f"weather:detail:{event_type}:{event_id}:{storm['episode_id']}:{storm.get('date_modified')}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    with ThreadPoolExecutor(max_workers=2) as pool:
        geometry_future = pool.submit(_fetch_geometry, storm)
        exposure_future = pool.submit(_fetch_exposure, storm)
        unavailable, geometry, exposure = [], {}, None
        try:
            geometry = geometry_future.result()
        except Exception as e:
            logger.info(f"[hazard_detail] geometry unavailable for {event_type} {event_id}: {e}")
            unavailable.append('geometry')
        try:
            exposure = exposure_future.result()
        except Exception as e:
            logger.info(f"[hazard_detail] exposure unavailable for {event_type} {event_id}: {e}")
            unavailable.append('exposure')

    result = {
        'id': storm['id'],
        'event_type': event_type,
        'track': geometry.get('track'),
        'wind_zones': geometry.get('wind_zones'),
        'cone': geometry.get('cone'),
        'area': geometry.get('area'),
        'exposure': exposure,
        'unavailable': unavailable,
        'source': 'gdacs.org',
        'generated_at': datetime.utcnow().isoformat(),
    }
    if not unavailable:                      # a partial failure is retried, not cached
        cache_set(key, result, ttl=CACHE_TTL)
    return result
