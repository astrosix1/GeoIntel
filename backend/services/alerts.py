"""Hazard alerts for watchlist places.

evaluate_alerts() runs on the scheduler (every 15 minutes). It compares the
live GDACS hazards with every user's watch places, records an alert for each
hazard that is within a place's radius at or above the user's minimum alert
level, and emails each user one digest of their alerts that haven't been
emailed yet.

Dedupe is the database's job: geointel_alerts is unique on (place_id,
hazard_key) and hazard_key includes the alert level, so the same hazard at the
same level never alerts twice for a place, while an escalation (Green to
Orange) alerts again. Emailing works off "alerts with no emailed_at", so a
failed send is retried on the next run without creating a duplicate alert.
"""
import html
import logging
import os
from datetime import datetime, timedelta, timezone

from services.geo import distance_km
from services.place_alert_prefs import hazard_settings
from services.mailer import is_configured, send_email
from services.supabase_rest import SupabaseUnavailable, auth_user_email, check_uuid, rest
from services.weather import get_active_storms

logger = logging.getLogger(__name__)

LEVELS = {'green': 0, 'orange': 1, 'red': 2}
DEFAULT_MIN_LEVEL = 'orange'
MAX_PLACES_SCANNED = 5000
EMAIL_RETRY_WINDOW = timedelta(hours=24)
MAX_DIGEST_ITEMS = 20
USERS_PER_QUERY = 50
INSERT_CHUNK = 200


def _app_url():
    return os.getenv('APP_BASE_URL', 'https://geointel.asix.live').rstrip('/')


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _load_prefs(user_ids):
    """{user_id: {'alert_email', 'alert_min_level'}} with defaults filled in."""
    prefs = {}
    ids = sorted(user_ids)
    for chunk in _chunks(ids, USERS_PER_QUERY):
        rows = rest('GET', 'geointel_user_prefs', params={
            'user_id': f'in.({",".join(chunk)})',
            'select': 'user_id,alert_email,alert_min_level',
            'limit': str(USERS_PER_QUERY),
        }).json()
        for row in rows:
            prefs[row['user_id']] = row
    return {
        uid: {
            'alert_email': prefs.get(uid, {}).get('alert_email', True) is not False,
            'alert_min_level': prefs.get(uid, {}).get('alert_min_level') or DEFAULT_MIN_LEVEL,
        }
        for uid in ids
    }


def _candidates(places, hazards, prefs):
    """Alert rows (not yet saved) for every place/hazard pair that matches."""
    rows = []
    for place in places:
        user_prefs = prefs[place['user_id']]
        # This place's own choices (hazard types and minimum level); the account's minimum level is the fallback.
        wanted_types, min_level = hazard_settings(place.get('alert_prefs'), user_prefs['alert_min_level'])
        minimum = LEVELS.get(min_level, LEVELS[DEFAULT_MIN_LEVEL])
        for hazard in hazards:
            if hazard['event_type'] not in wanted_types:
                continue
            level = LEVELS[hazard['alert_level'].lower()]
            if level < minimum:
                continue
            distance = distance_km(place['lat'], place['lon'], hazard['lat'], hazard['lon'])
            if distance > place['radius_km']:
                continue
            rows.append({
                'user_id': place['user_id'],
                'place_id': place['id'],
                'hazard_key': f"{hazard['event_type']}-{hazard['id']}-{hazard['alert_level'].lower()}",
                'hazard_type': hazard['event_type'],
                'title': hazard.get('name') or hazard.get('hazard') or 'Weather hazard',
                'alert_level': hazard['alert_level'],
                'distance_km': round(distance, 1),
            })
    return rows


def _digest(alerts, place_names):
    """(subject, html, text) for one user's pending alerts."""
    shown = alerts[:MAX_DIGEST_ITEMS]
    extra = len(alerts) - len(shown)
    plural = 's' if len(alerts) != 1 else ''
    if all(a.get('hazard_type') == 'WX' for a in alerts):
        subject = f"GeoIntel forecast alert: {len(alerts)} forecast limit{plural} passed for your places"
    else:
        subject = f"GeoIntel weather alert: {len(alerts)} hazard{plural} near your places"

    lines, items = [], []
    for a in shown:
        place = place_names.get(a['place_id'], 'your place')
        line = (f"{a['title']} at {place}" if a.get('hazard_type') == 'WX'
                else f"{a['alert_level']} alert: {a['title']} is {a['distance_km']} km from {place}")
        lines.append(f'- {line}')
        if a.get('hazard_type') == 'WX':
            items.append(f"<li>{html.escape(a['title'])} at {html.escape(place)}</li>")
        else:
            items.append(f"<li><strong>{html.escape(a['alert_level'])} alert:</strong> {html.escape(a['title'])} "
                         f"is {html.escape(str(a['distance_km']))} km from {html.escape(place)}</li>")
    if extra > 0:
        lines.append(f'...and {extra} more in your dashboard.')
        items.append(f'<li>...and {extra} more in your dashboard.</li>')

    url = _app_url()
    footer = ('You are receiving this because email alerts are on for your GeoIntel watchlist. '
              f'Turn them off in Dashboard > Alerts at {url}')
    text = 'New hazards near your watchlist places:\n\n' + '\n'.join(lines) + f'\n\nOpen GeoIntel: {url}\n\n{footer}\n'
    body = (
        '<p>New hazards near your watchlist places:</p><ul>' + ''.join(items) + '</ul>'
        f'<p><a href="{html.escape(url)}">Open GeoIntel</a></p>'
        f'<p style="color:#666;font-size:12px">{html.escape(footer)}</p>'
    )
    return subject, body, text


def _email_pending(places_by_id, prefs_cache):
    """One digest per user for alerts with no emailed_at (last 24 h). Returns
    the number of emails sent."""
    cutoff = (datetime.now(timezone.utc) - EMAIL_RETRY_WINDOW).isoformat()
    pending = rest('GET', 'geointel_alerts', params={
        'emailed_at': 'is.null',
        'created_at': f'gt.{cutoff}',
        'select': 'id,user_id,place_id,hazard_type,title,alert_level,distance_km,created_at',
        'order': 'created_at.asc',
        'limit': '5000',
    }).json()
    if not pending:
        return 0

    by_user = {}
    for alert in pending:
        by_user.setdefault(alert['user_id'], []).append(alert)

    missing = [u for u in by_user if u not in prefs_cache]
    if missing:
        prefs_cache.update(_load_prefs(missing))

    sent = 0
    for user_id, alerts in by_user.items():
        if not prefs_cache[user_id]['alert_email']:
            continue
        try:
            address = auth_user_email(user_id)
        except SupabaseUnavailable:
            continue
        if not address:
            continue
        place_names = {a['place_id']: places_by_id.get(a['place_id'], {}).get('name') for a in alerts}
        place_names = {k: v for k, v in place_names.items() if v}
        subject, body, text = _digest(alerts, place_names)
        if not send_email(address, subject, body, text):
            continue
        ids = ','.join(check_uuid(a['id']) for a in alerts)
        rest('PATCH', 'geointel_alerts', params={'id': f'in.({ids})'},
             json_body={'emailed_at': datetime.now(timezone.utc).isoformat()})
        sent += 1
    return sent


def evaluate_alerts():
    """One evaluation pass. Returns a summary dict; never raises on a data
    problem (it logs and returns), so the scheduler job stays healthy."""
    summary = {'places': 0, 'new_alerts': 0, 'emails': 0, 'skipped': None}
    try:
        storms = get_active_storms()
        if storms is None:
            summary['skipped'] = 'hazard_feed_unavailable'
            return summary
        hazards = [
            s for s in storms['storms']
            if isinstance(s.get('lat'), (int, float)) and isinstance(s.get('lon'), (int, float))
            and isinstance(s.get('alert_level'), str) and s['alert_level'].lower() in LEVELS
            and s.get('id') is not None and s.get('event_type')
        ]

        scan = {'order': 'created_at.asc', 'limit': str(MAX_PLACES_SCANNED)}
        try:
            places = rest('GET', 'geointel_watch_places', params={**scan, 'select': 'id,user_id,name,lat,lon,radius_km,alert_prefs'}).json()
        except SupabaseUnavailable as e:
            if e.reason != 'column_missing':
                raise
            places = rest('GET', 'geointel_watch_places', params={**scan, 'select': 'id,user_id,name,lat,lon,radius_km'}).json()   # 007 not applied
        summary['places'] = len(places)
        places_by_id = {p['id']: p for p in places}

        prefs = _load_prefs({p['user_id'] for p in places}) if places else {}

        if places and hazards:
            candidates = _candidates(places, hazards, prefs)
            for chunk in _chunks(candidates, INSERT_CHUNK):
                inserted = rest('POST', 'geointel_alerts',
                                params={'on_conflict': 'place_id,hazard_key', 'select': 'id'},
                                json_body=chunk,
                                prefer='resolution=ignore-duplicates,return=representation').json()
                summary['new_alerts'] += len(inserted)

        if is_configured():
            summary['emails'] = _email_pending(places_by_id, prefs)
    except SupabaseUnavailable as e:
        logger.error(f"Alert evaluation skipped: {e.reason}")
        summary['skipped'] = e.reason
    except Exception as e:  # keep the scheduler job alive whatever happens
        logger.error(f"Alert evaluation failed: {e}")
        summary['skipped'] = 'error'
    if summary['new_alerts'] or summary['emails']:
        logger.info(f"Alerts: {summary}")
    return summary
