"""Situation alerts: a watched place hears about a situation (or a serious event) that starts inside its radius.

evaluate_situations() runs with the hazard evaluator, every 15 minutes. It reads the events and situations this app already
holds (no new feed): one candidate per pin, so a situation of twenty stories is one alert, not twenty. A place only alerts
if it switched this on (default off), above the severity it chose, and statements and talks only if it asked for them. The
alert key carries the severity level, so a situation that escalates alerts again and an unchanged one never does (the
database's unique key on place and key does the dedupe).
"""
import logging
import math
from datetime import datetime, timedelta

from models import Session, Crisis, Situation
from services.geo import distance_km
from services.place_alert_prefs import situation_settings
from services.supabase_rest import SupabaseUnavailable, rest

logger = logging.getLogger(__name__)

LOOKBACK = timedelta(hours=24)
MAX_PER_PLACE_PER_RUN = 5
MAX_PLACES_SCANNED = 5000
INSERT_CHUNK = 200
MIN_SEVERITY = 40


def alert_level(severity):
    """The alert level shown for an event: Critical is Red, Severe is Orange, Serious is Green."""
    return 'Red' if severity >= 80 else 'Orange' if severity >= 60 else 'Green'


def _events(session, now):
    """One candidate per pin from the last LOOKBACK: active, not merged away, a situation's lead or a story on its own."""
    rows = (session.query(Crisis)
            .filter(Crisis.is_active.is_(True), Crisis.merged_into.is_(None), Crisis.date_start >= now - LOOKBACK,
                    Crisis.severity >= MIN_SEVERITY)
            .all())
    leads = [r for r in rows if r.situation_id is None or r.situation_id == r.id]
    situations = {s.id: s for s in session.query(Situation).filter(Situation.id.in_([r.id for r in leads if r.situation_id])).all()} if leads else {}
    out = []
    for r in leads:
        sit = situations.get(r.id)
        out.append({
            'id': r.id,
            'title': (sit.title if sit and sit.title else r.title) or 'Situation',
            'stories': sit.story_count if sit else 1,
            'lat': r.latitude, 'lon': r.longitude,
            'severity': r.severity or 0,
            'statement': r.event_kind == 'statement',
            'date': r.date_start,
        })
    return out


def candidates(places, events):
    """Alert rows (not yet saved) for places that switched situation alerts on."""
    rows = []
    for place in places:
        enabled, floor, statements = situation_settings(place.get('alert_prefs'))
        if not enabled:
            continue
        lat_span = place['radius_km'] / 111.0
        lon_span = place['radius_km'] / max(1.0, 111.0 * math.cos(math.radians(place['lat'])))
        found = []
        for ev in events:
            if ev['severity'] < floor or (ev['statement'] and not statements):
                continue
            if abs(ev['lat'] - place['lat']) > lat_span or abs(ev['lon'] - place['lon']) > lon_span * 1.01:
                continue
            distance = distance_km(place['lat'], place['lon'], ev['lat'], ev['lon'])
            if distance <= place['radius_km']:
                found.append((ev, distance))
        found.sort(key=lambda pair: (-pair[0]['severity'], -pair[0]['date'].timestamp()))
        for ev, distance in found[:MAX_PER_PLACE_PER_RUN]:
            level = alert_level(ev['severity'])
            suffix = f" ({ev['stories']} stories)" if ev['stories'] > 1 else ''
            rows.append({
                'user_id': place['user_id'],
                'place_id': place['id'],
                'hazard_key': f"SIT-{ev['id']}-{level.lower()}",
                'hazard_type': 'SIT',
                'title': f"{ev['title'][:180]}{suffix}",
                'alert_level': level,
                'distance_km': round(distance, 1),
            })
    return rows


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def evaluate_situations(now=None):
    """One pass. Returns a summary and never raises, so the scheduler job stays healthy."""
    summary = {'places': 0, 'new_alerts': 0, 'skipped': None}
    try:
        try:
            places = rest('GET', 'geointel_watch_places', params={
                'select': 'id,user_id,name,lat,lon,radius_km,alert_prefs', 'order': 'created_at.asc', 'limit': str(MAX_PLACES_SCANNED),
            }).json()
        except SupabaseUnavailable as e:
            if e.reason == 'column_missing':      # 007 not applied: nobody can have switched this on yet
                summary['skipped'] = 'no_prefs_column'
                return summary
            raise
        places = [p for p in places if situation_settings(p.get('alert_prefs'))[0]]
        summary['places'] = len(places)
        if not places:
            return summary
        session = Session()
        try:
            events = _events(session, now or datetime.utcnow())
        finally:
            session.close()
        for chunk in _chunks(candidates(places, events), INSERT_CHUNK):
            inserted = rest('POST', 'geointel_alerts',
                            params={'on_conflict': 'place_id,hazard_key', 'select': 'id'},
                            json_body=chunk,
                            prefer='resolution=ignore-duplicates,return=representation').json()
            summary['new_alerts'] += len(inserted)
    except SupabaseUnavailable as e:
        logger.error(f"Situation alerts skipped: {e.reason}")
        summary['skipped'] = e.reason
    except Exception as e:  # keep the scheduler job alive whatever happens
        logger.error(f"Situation alert evaluation failed: {e}")
        summary['skipped'] = 'error'
    if summary['new_alerts']:
        logger.info(f"Situation alerts: {summary}")
    return summary
