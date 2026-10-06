"""Link weather hazards and events by place and time, with plain rules.

A link says an event happened inside or near a hazard's footprint while it was
active. It never says one caused the other. Rules:

  * Place: the event's pin is inside the hazard's affected area (floods, fires)
    or its current 60 km/h wind zone (cyclones). When GDACS publishes no footprint
    for the hazard, a fixed radius around its point is used and the link is marked
    approximate. A cyclone's track is NOT used: GDACS does not time-stamp its
    segments, so being near the track could mean being near where it was days ago.
    Cyclone links also need the event to be within WIND_ZONE_HOURS of the wind
    zone's own time.
  * Time: the event's date falls between the hazard's start and its end plus
    WINDOW_AFTER_DAYS.
  * Kind: physical events only; talks and statements are never linked.
  * Precision: only pins at city level or better (location_confidence of 85 or
    more), so a country-centre pin can never match a hazard by accident.
  * Merged duplicates are skipped; the story's primary event carries the link.

Links are computed when asked for, from the hazard geometry GDACS publishes
(services/hazard_detail.py, cached) and the events table.
"""
import logging
import math
from datetime import datetime, timedelta

from cache import cache_get, cache_set
from models import Session, Crisis
from services.geo import distance_km
from services.hazard_detail import get_hazard_detail
from services.weather import get_active_storms

logger = logging.getLogger(__name__)

WINDOW_AFTER_DAYS = 3
MIN_LOCATION_CONFIDENCE = 85
WIND_ZONE_HOURS = 24
BBOX_PAD_KM = 100
CACHE_TTL = 10 * 60
MAX_EVENTS_PER_HAZARD = 50
MAX_CANDIDATES = 600
# Used only when GDACS publishes no footprint for the hazard (the link is marked approximate).
FALLBACK_RADIUS_KM = {'TC': 300, 'FL': 50, 'WF': 25}
# Hazards whose point is further than this from an event are not worth fetching geometry for.
PREFILTER_KM = {'TC': 2500, 'FL': 300, 'WF': 150}


# --- geometry -------------------------------------------------------------------

def _in_ring(lon, lat, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _in_polygon(lon, lat, rings):
    """Inside the outer ring and outside every hole."""
    if not rings or not _in_ring(lon, lat, rings[0]):
        return False
    return not any(_in_ring(lon, lat, hole) for hole in rings[1:])


def point_in_geometry(lon, lat, geometry):
    if not isinstance(geometry, dict):
        return False
    coords = geometry.get('coordinates')
    if geometry.get('type') == 'Polygon':
        return _in_polygon(lon, lat, coords)
    if geometry.get('type') == 'MultiPolygon':
        return any(_in_polygon(lon, lat, polygon) for polygon in coords or [])
    return False


def _segment_km(lat, lon, a, b):
    """Distance in km from a point to the segment a-b (lon/lat pairs), using a local flat projection
    (accurate to well under a percent at the distances used here)."""
    k_lat = 111.195
    k_lon = 111.195 * math.cos(math.radians(lat))

    def wrap(degrees):
        return (degrees + 180) % 360 - 180

    # Wrap the point's longitude difference once, then the segment's own span relative to its first
    # end, so a segment is never bent the long way round the globe.
    lon_a = wrap(a[0] - lon)
    lon_b = lon_a + wrap(b[0] - a[0])
    x1, y1 = lon_a * k_lon, (a[1] - lat) * k_lat
    x2, y2 = lon_b * k_lon, (b[1] - lat) * k_lat
    dx, dy = x2 - x1, y2 - y1
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, -(x1 * dx + y1 * dy) / length))
    return math.hypot(x1 + t * dx, y1 + t * dy)


def distance_to_track_km(lat, lon, track):
    best = None
    for feature in track or []:
        coords = (feature.get('geometry') or {}).get('coordinates') or []
        for a, b in zip(coords, coords[1:]):
            d = _segment_km(lat, lon, a, b)
            best = d if best is None else min(best, d)
    return best


def _bbox(detail, storm, pad_km):
    """(min_lat, max_lat, min_lon, max_lon) around everything GDACS published for the hazard, padded."""
    lats, lons = [], []

    def walk(coords):
        if coords and isinstance(coords[0], (int, float)):
            lons.append(coords[0])
            lats.append(coords[1])
        else:
            for c in coords or []:
                walk(c)

    for key in ('track', 'wind_zones', 'cone', 'area'):
        for feature in (detail or {}).get(key) or []:
            walk((feature.get('geometry') or {}).get('coordinates'))
    if not lats and storm.get('lat') is not None and storm.get('lon') is not None:
        pad_km = max(pad_km, FALLBACK_RADIUS_KM.get(storm.get('event_type'), 0))
        lats, lons = [storm['lat']], [storm['lon']]
    if not lats:
        return None
    pad_lat = pad_km / 111.0
    mid = (min(lats) + max(lats)) / 2
    pad_lon = min(180.0, pad_km / (111.0 * max(0.05, math.cos(math.radians(mid)))))
    return min(lats) - pad_lat, max(lats) + pad_lat, min(lons) - pad_lon, max(lons) + pad_lon


def _zone_time_ok(zone, when):
    """A wind zone describes one moment (its as_of time); an event only counts near that moment."""
    as_of = _parse((zone.get('properties') or {}).get('as_of'))
    return when is not None and as_of is not None and abs((when - as_of).total_seconds()) <= WIND_ZONE_HOURS * 3600


def locate(lat, lon, storm, detail, when=None):
    """(distance_km, basis, approximate) when the point is in or near the hazard, else None."""
    event_type = storm.get('event_type')
    if detail:
        for key, text in (('area', 'inside the affected area GDACS outlines'),
                          ('wind_zones', 'inside the 60 km/h wind zone')):
            features = detail.get(key) or []
            if key == 'wind_zones':      # nested zones: the lowest-speed one is the outermost
                features = [f for f in features if str((f.get('properties') or {}).get('label', '')).startswith('60')] or features[:1]
                features = [f for f in features if _zone_time_ok(f, when)]
            if any(point_in_geometry(lon, lat, f.get('geometry')) for f in features):
                return 0.0, text, False
        if detail.get('area') or detail.get('wind_zones') or detail.get('track'):
            return None                   # a published footprint exists and the point is not in it
    radius = FALLBACK_RADIUS_KM.get(event_type)
    if radius and storm.get('lat') is not None and storm.get('lon') is not None:
        d = distance_km(lat, lon, storm['lat'], storm['lon'])
        if d <= radius:
            return round(d, 1), f'within {radius} km of the hazard point (GDACS has not published its footprint)', True
    return None


# --- time -----------------------------------------------------------------------

def _parse(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '')[:19])
    except ValueError:
        return None


def time_gap_hours(when, storm):
    """0 when the event falls inside the hazard's active window, hours after its end when within
    the grace period, else None (no link)."""
    start, end = _parse(storm.get('from_date')), _parse(storm.get('to_date'))
    if when is None or start is None:
        return None
    end = end or start
    if when < start:
        return None
    if when <= end:
        return 0
    gap = (when - end).total_seconds() / 3600
    return round(gap) if gap <= WINDOW_AFTER_DAYS * 24 else None


# --- eligibility and queries -----------------------------------------------------

def _eligible(crisis):
    return (
        crisis.event_kind == 'physical'
        and crisis.is_active
        and not crisis.merged_into
        and (crisis.location_confidence or 0) >= MIN_LOCATION_CONFIDENCE
        and crisis.latitude is not None and crisis.longitude is not None
    )


def _hazard_summary(storm):
    return {
        'id': storm['id'], 'event_type': storm['event_type'], 'name': storm.get('name'),
        'hazard': storm.get('hazard'), 'alert_level': storm.get('alert_level'),
        'country': storm.get('country'), 'lat': storm.get('lat'), 'lon': storm.get('lon'),
    }


def _active_storms():
    result = get_active_storms()
    return None if result is None else result['storms']


def hazards_for_event(crisis_id):
    """{'links': [...]} for an event, or None when it does not exist. An event that is not
    eligible (statement, coarse pin, merged duplicate) has no links, stated in `reason`."""
    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if crisis is None:
            return None
        if not _eligible(crisis):
            reason = ('statement' if crisis.event_kind != 'physical'
                      else 'merged' if crisis.merged_into
                      else 'approximate_location' if (crisis.location_confidence or 0) < MIN_LOCATION_CONFIDENCE
                      else 'inactive')
            return {'links': [], 'reason': reason}
        lat, lon, when = crisis.latitude, crisis.longitude, crisis.date_start
    finally:
        session.close()

    storms = _active_storms()
    if storms is None:
        return {'links': [], 'reason': 'hazards_unavailable'}

    links = []
    for storm in storms:
        limit = PREFILTER_KM.get(storm.get('event_type'))
        if not limit or storm.get('lat') is None or storm.get('lon') is None:
            continue
        if distance_km(lat, lon, storm['lat'], storm['lon']) > limit:
            continue
        gap = time_gap_hours(when, storm)
        if gap is None:
            continue
        detail = get_hazard_detail(storm['event_type'], storm['id'])
        detail = detail if isinstance(detail, dict) else None
        found = locate(lat, lon, storm, detail, when)
        if found is None:
            continue
        km, basis, approximate = found
        links.append({'hazard': _hazard_summary(storm), 'distance_km': km, 'basis': basis,
                      'approximate': approximate, 'hours_after_hazard_ended': gap})
    links.sort(key=lambda link: link['distance_km'])
    return {'links': links, 'reason': None}


def events_for_hazard(event_type, event_id):
    """{'events': [...], 'truncated': bool} for an active hazard, or a string error code:
    'not_found' (not an active hazard) or 'unavailable' (the GDACS list is down)."""
    storms = _active_storms()
    if storms is None:
        return 'unavailable'
    storm = next((s for s in storms if s.get('event_type') == event_type and str(s.get('id')) == str(event_id)), None)
    if storm is None or event_type not in FALLBACK_RADIUS_KM:
        return 'not_found'

    key = f"weather:links:{event_type}:{event_id}:{storm.get('date_modified')}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    detail = get_hazard_detail(event_type, event_id)
    detail = detail if isinstance(detail, dict) else None
    box = _bbox(detail, storm, BBOX_PAD_KM)
    start = _parse(storm.get('from_date'))
    if box is None or start is None:
        return {'events': [], 'truncated': False, 'approximate': True}
    end = (_parse(storm.get('to_date')) or start) + timedelta(days=WINDOW_AFTER_DAYS)

    session = Session()
    try:
        rows = (session.query(Crisis)
                .filter(Crisis.is_active.is_(True), Crisis.event_kind == 'physical', Crisis.merged_into.is_(None),
                        Crisis.location_confidence >= MIN_LOCATION_CONFIDENCE,
                        Crisis.latitude.between(box[0], box[1]),
                        Crisis.date_start >= start, Crisis.date_start <= end)
                .limit(MAX_CANDIDATES).all())
        candidates = [(c.id, c.title, c.country, c.severity, c.severity_level, c.source_count, c.latitude,
                       c.longitude, c.date_start, c.type, c.scope, c.source_url, c.location_confidence)
                      for c in rows if _in_lon(c.longitude, box)]
    finally:
        session.close()

    events = []
    for cid, title, country, severity, level, sources, lat, lon, when, ctype, scope, source_url, confidence in candidates:
        gap = time_gap_hours(when, storm)
        if gap is None:
            continue
        found = locate(lat, lon, storm, detail, when)
        if found is None:
            continue
        km, basis, approximate = found
        events.append({'id': cid, 'title': title, 'country': country, 'type': ctype, 'scope': scope,
                       'source_url': source_url, 'location_confidence': confidence,
                       'severity': severity, 'severity_level': level,
                       'source_count': sources or 1, 'lat': lat, 'lon': lon,
                       'date': when.isoformat() if when else None, 'distance_km': km, 'basis': basis,
                       'approximate': approximate, 'hours_after_hazard_ended': gap})
    events.sort(key=lambda e: (-(e['severity'] or 0), e['distance_km']))
    result = {'events': events[:MAX_EVENTS_PER_HAZARD], 'truncated': len(events) > MAX_EVENTS_PER_HAZARD,
              'approximate': bool(detail is None or not (detail.get('area') or detail.get('wind_zones') or detail.get('track')))}
    cache_set(key, result, ttl=CACHE_TTL)
    return result


def _in_lon(lon, box):
    """Longitude inside the box, allowing the box to wrap the antimeridian."""
    lo, hi = box[2], box[3]
    if hi - lo >= 360:
        return True
    def norm(x):
        return (x + 180) % 360 - 180
    lo_n, hi_n = norm(lo), norm(hi)
    if lo_n <= hi_n:
        return lo_n <= lon <= hi_n
    return lon >= lo_n or lon <= hi_n
