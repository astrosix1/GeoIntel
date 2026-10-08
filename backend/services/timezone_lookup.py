"""
Which time zone a point is in, from the zone boundary file (backend/data/timezones.geojson, a copy of the one the map draws:
timezone-boundary-builder, OpenStreetMap-based, ODbL). A forecast source that speaks only UTC needs this to show a place's own
clock and to cut its days at local midnight. Same method as frontend/src/lib/zoneLookup.ts: a bounding-box check, then a
point-in-polygon test that allows for holes. Returns None over open sea.
"""
import json
import threading
from functools import lru_cache
from pathlib import Path

GEOJSON = Path(__file__).resolve().parent.parent / 'data' / 'timezones.geojson'
_lock = threading.Lock()
_entries = None


def _bbox(ring):
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return min(lons), min(lats), max(lons), max(lats)


def _load():
    global _entries
    with _lock:
        if _entries is not None:
            return _entries
        entries = []
        try:
            data = json.loads(GEOJSON.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _entries = entries
            return entries
        for feature in data.get('features', []):
            tzid = (feature.get('properties') or {}).get('tzid')
            geometry = feature.get('geometry') or {}
            if not isinstance(tzid, str):
                continue
            if geometry.get('type') == 'Polygon':
                polygons = [geometry.get('coordinates')]
            elif geometry.get('type') == 'MultiPolygon':
                polygons = geometry.get('coordinates')
            else:
                continue
            for rings in polygons or []:
                if rings and rings[0]:
                    entries.append((tzid, _bbox(rings[0]), rings))
        _entries = entries
        return entries


def _in_ring(lon, lat, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


@lru_cache(maxsize=4096)
def zone_at(lat, lon):
    """The tz database id for a point (for example 'Europe/Paris'), or None where no zone polygon contains it."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    for tzid, (min_lon, min_lat, max_lon, max_lat), rings in _load():
        if lon < min_lon or lon > max_lon or lat < min_lat or lat > max_lat:
            continue
        if not _in_ring(lon, lat, rings[0]):
            continue
        if any(_in_ring(lon, lat, hole) for hole in rings[1:]):
            continue
        return tzid
    return None
