"""Clock-change alerts: a watched place hears, up to a week ahead, that the clocks there are about to change (daylight saving
starting or ending). The place's own time zone comes from the bundled zone boundaries (services/timezone_lookup.py) and the
change from the system time zone database, so nothing is kept by hand. One alert per place and change: the key carries the
zone and the local date of the change, and the database's unique key on place and key stops repeats.

evaluate_clock_changes() runs with the hourly forecast job; a change a week out is found once and never alerted twice.
"""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.place_alert_prefs import clock_enabled
from services.supabase_rest import SupabaseUnavailable, rest
from services.timezone_lookup import zone_at

logger = logging.getLogger(__name__)

DAYS_AHEAD = 7
MAX_PLACES_SCANNED = 5000
INSERT_CHUNK = 200


def next_change(tzid, now, days=DAYS_AHEAD):
    """The next change of clock offset for a zone within `days` of `now` (a UTC datetime), as a dict, or None.
    Found by stepping an hour at a time and narrowing to the minute."""
    try:
        zone = ZoneInfo(tzid)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    step = timedelta(hours=1)
    start = now.astimezone(timezone.utc)
    before = start.astimezone(zone).utcoffset()
    t = start
    end = start + timedelta(days=days)
    while t < end:
        after_time = t + step
        after = after_time.astimezone(zone).utcoffset()
        if after != before:
            lo, hi = t, after_time
            while hi - lo > timedelta(minutes=1):
                mid = lo + (hi - lo) / 2
                if mid.astimezone(zone).utcoffset() == before:
                    lo = mid
                else:
                    hi = mid
            instant = hi.replace(second=0, microsecond=0)
            local_before = (instant - timedelta(minutes=1)).astimezone(zone)
            local_after = instant.astimezone(zone)
            return {
                'tzid': tzid, 'instant': instant, 'direction': 'forward' if after > before else 'back',
                'shift_minutes': int(abs((after - before).total_seconds()) // 60),
                'local_before': local_before.strftime('%H:%M'), 'local_after': local_after.strftime('%H:%M'),
                'local_date': local_after.strftime('%Y-%m-%d'), 'local_day': local_after.strftime('%a %d %b'),
            }
        t, before = after_time, after
    return None


def alert_row(place, change):
    amount = change['shift_minutes']
    size = f"{amount // 60} hour{'s' if amount // 60 != 1 else ''}" if amount % 60 == 0 else f'{amount} minutes'
    what = 'forward' if change['direction'] == 'forward' else 'back'
    return {
        'user_id': place['user_id'],
        'place_id': place['id'],
        'hazard_key': f"CLK-{change['tzid']}-{change['local_date']}",
        'hazard_type': 'CLK',
        'title': (f"Clocks go {what} {size} in {place['name']} on {change['local_day']}: "
                  f"{change['local_before']} becomes {change['local_after']} ({change['tzid']})"),
        'alert_level': 'Green',
        'distance_km': 0,
    }


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def evaluate_clock_changes(now=None):
    """One pass. Returns a summary and never raises, so the scheduler job stays healthy."""
    summary = {'places': 0, 'new_alerts': 0, 'skipped': None}
    now = now or datetime.now(timezone.utc)
    try:
        try:
            places = rest('GET', 'geointel_watch_places', params={
                'select': 'id,user_id,name,lat,lon,alert_prefs', 'order': 'created_at.asc', 'limit': str(MAX_PLACES_SCANNED),
            }).json()
        except SupabaseUnavailable as e:
            if e.reason == 'column_missing':        # 007 not applied: nobody can have switched this on yet
                summary['skipped'] = 'no_prefs_column'
                return summary
            raise
        places = [p for p in places if clock_enabled(p.get('alert_prefs'))]
        summary['places'] = len(places)
        changes, rows = {}, []
        for place in places:
            tzid = zone_at(place['lat'], place['lon'])
            if not tzid:
                continue
            if tzid not in changes:
                changes[tzid] = next_change(tzid, now)
            if changes[tzid]:
                rows.append(alert_row(place, changes[tzid]))
        for chunk in _chunks(rows, INSERT_CHUNK):
            inserted = rest('POST', 'geointel_alerts',
                            params={'on_conflict': 'place_id,hazard_key', 'select': 'id'},
                            json_body=chunk,
                            prefer='resolution=ignore-duplicates,return=representation').json()
            summary['new_alerts'] += len(inserted)
    except SupabaseUnavailable as e:
        logger.error(f"Clock-change alerts skipped: {e.reason}")
        summary['skipped'] = e.reason
    except Exception as e:  # keep the scheduler job alive whatever happens
        logger.error(f"Clock-change alert evaluation failed: {e}")
        summary['skipped'] = 'error'
    if summary['new_alerts']:
        logger.info(f"Clock-change alerts: {summary}")
    return summary
