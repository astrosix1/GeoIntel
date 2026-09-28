"""
Point-in-country checks against the vendored world-atlas topojson
(config/geo/countries-50m.json — the same borders the frontend draws).

Pure Python: the topojson's delta-encoded arcs are decoded once per process,
each country's rings are unwrapped across the antimeridian (Russia, Fiji),
and lookups use a bounding-box prefilter before ray casting. Tolerances are
in kilometres so a coastal city or port that the 1:50m coastline leaves just
offshore still counts as inside its country.
"""
import json
import math
import os
from functools import lru_cache

_TOPO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'geo', 'countries-50m.json'
)
# Must match scripts/build_countries.py.
_PSEUDO_CODES = {'Kosovo': 'XKX', 'Somaliland': 'SOL', 'N. Cyprus': 'CYN'}
_KM_PER_DEG_LAT = 110.57


def _unwrap(points):
    out, offset, prev = [], 0.0, None
    for x, y in points:
        if prev is not None:
            if x + offset - prev > 180:
                offset -= 360
            elif x + offset - prev < -180:
                offset += 360
        out.append((x + offset, y))
        prev = x + offset
    return out


@lru_cache(maxsize=1)
def _countries():
    """code -> {'polygons': [[outer, *holes], ...], 'bbox': (minx, miny, maxx, maxy)}"""
    with open(_TOPO_PATH, 'r', encoding='utf-8') as f:
        topo = json.load(f)
    sx, sy = topo['transform']['scale']
    tx, ty = topo['transform']['translate']
    arcs = []
    for arc in topo['arcs']:
        x = y = 0
        points = []
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x * sx + tx, y * sy + ty))
        arcs.append(points)

    def ring(indexes):
        points = []
        for i in indexes:
            arc = arcs[i] if i >= 0 else arcs[~i][::-1]
            points.extend(arc if not points else arc[1:])
        return _unwrap(points)

    out = {}
    for g in topo['objects']['countries']['geometries']:
        code = g.get('id') or _PSEUDO_CODES.get(g['properties']['name'])
        if not code:
            continue
        if g['type'] == 'Polygon':
            polys = [[ring(r) for r in g['arcs']]]
        elif g['type'] == 'MultiPolygon':
            polys = [[ring(r) for r in poly] for poly in g['arcs']]
        else:
            continue
        xs = [x for poly in polys for x, _ in poly[0]]
        ys = [y for poly in polys for _, y in poly[0]]
        out[code] = {'polygons': polys, 'bbox': (min(xs), min(ys), max(xs), max(ys))}
    return out


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _lon_variants(lon):
    return (lon, lon + 360, lon - 360)


def contains(code, lat, lon):
    country = _countries().get(str(code))
    if not country:
        return False
    minx, miny, maxx, maxy = country['bbox']
    if not (miny <= lat <= maxy):
        return False
    for x in _lon_variants(lon):
        if not (minx <= x <= maxx):
            continue
        for poly in country['polygons']:
            if _in_ring(x, lat, poly[0]) and not any(_in_ring(x, lat, hole) for hole in poly[1:]):
                return True
    return False


def country_at(lat, lon):
    """Code of the country containing the point, or None (open sea)."""
    for code in _countries():
        if contains(code, lat, lon):
            return code
    return None


def _segment_km(px, py, ax, ay, bx, by, kx):
    # Local equirectangular projection around the point, in km.
    ax, ay, bx, by = (ax - px) * kx, (ay - py) * _KM_PER_DEG_LAT, (bx - px) * kx, (by - py) * _KM_PER_DEG_LAT
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length2))
    return math.hypot(ax + t * dx, ay + t * dy)


def distance_km(code, lat, lon, cap_km=2000.0):
    """Approximate distance from the point to the country's border (0 when
    inside). Returns cap_km when the country is further than that."""
    if contains(code, lat, lon):
        return 0.0
    country = _countries().get(str(code))
    if not country:
        return cap_km
    kx = 111.32 * max(math.cos(math.radians(lat)), 0.01)
    margin_lat = cap_km / _KM_PER_DEG_LAT
    minx, miny, maxx, maxy = country['bbox']
    if lat < miny - margin_lat or lat > maxy + margin_lat:
        return cap_km
    best = cap_km
    for x in _lon_variants(lon):
        if x < minx - cap_km / kx or x > maxx + cap_km / kx:
            continue
        for poly in country['polygons']:
            for ring in poly:
                for (ax, ay), (bx, by) in zip(ring, ring[1:]):
                    d = _segment_km(x, lat, ax, ay, bx, by, kx)
                    if d < best:
                        best = d
    return best


def point_in_country(lat, lon, code, tolerance_km=25.0):
    return contains(code, lat, lon) or distance_km(code, lat, lon, cap_km=tolerance_km + 1) <= tolerance_km
