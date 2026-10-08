"""
Data blocks for the event Analysis tab that are not the AI briefing: "the pattern here" (violent, non-statement reports in the
event's country, the last 7 days against the 7 before, plus a weekly trend) and the related events nearby. Everything is counted from
this app's own events; it is a trend of reports in the area, not of one event's stored score.
"""
import math
from datetime import datetime, timedelta

from cache import cache_get, cache_set
from models import Session, Crisis, Actor
from services.country_detail import VIOLENT_TYPES, _country_names
import json
from pathlib import Path

WEEKS = 8
RELATED_LIMIT = 5
_NAME_INDEX = None


def _iso2_for(country):
    """The ISO-2 code whose known names include this country name (case-insensitive), or None."""
    global _NAME_INDEX
    if _NAME_INDEX is None:
        path = Path(__file__).resolve().parent.parent / 'data_sources' / 'country_names.json'
        raw = json.loads(path.read_text(encoding='utf-8'))
        _NAME_INDEX = {n.lower(): iso for iso, names in raw.items() for n in names}
    return _NAME_INDEX.get((country or '').strip().lower())


def build_pattern(session, crisis, now=None):
    """Counts of violent, non-statement reports in the event's country. None when the country is unknown or has no reports at all."""
    from sqlalchemy import func, or_
    iso2 = _iso2_for(crisis.country)
    names = _country_names(iso2) if iso2 else {(crisis.country or '').lower()}
    if not names or names == {''}:
        return None
    now = now or datetime.utcnow()
    rows = (session.query(Crisis.date_start)
            .filter(Crisis.is_active.is_(True), Crisis.merged_into.is_(None), Crisis.type.in_(VIOLENT_TYPES),
                    func.lower(Crisis.country).in_(names), or_(Crisis.event_kind.is_(None), Crisis.event_kind != 'statement'),
                    Crisis.date_start >= now - timedelta(weeks=WEEKS)).all())
    dates = [r[0] for r in rows if r[0]]
    if not dates:
        return None
    buckets = [0] * WEEKS
    for d in dates:
        index = WEEKS - 1 - int((now - d).total_seconds() // (7 * 86400))
        if 0 <= index < WEEKS:
            buckets[index] += 1
    this_week, before = buckets[-1], buckets[-2]
    if this_week + before < 4:
        direction = 'too_few'      # too little to call a direction
    elif this_week >= before * 1.25:
        direction = 'rising'
    elif this_week <= before * 0.75:
        direction = 'falling'
    else:
        direction = 'steady'
    start = (now - timedelta(weeks=WEEKS - 1)).date()
    return {
        'country': crisis.country,
        'last_7_days': this_week,
        'previous_7_days': before,
        'direction': direction,
        'weekly': [[(start + timedelta(weeks=i)).isoformat(), c] for i, c in enumerate(buckets)],
        'counted': 'violent reports (conflict, military, civil unrest, proxy), statements excluded',
        'source': 'GeoIntel events (GDELT news feed)',
    }


def build_related(session, crisis, limit=RELATED_LIMIT):
    """Other active events in the same country, or within about 5 degrees, of the same type, within 60 days, nearest in time first."""
    candidates = (session.query(Crisis)
                  .filter(Crisis.id != crisis.id, Crisis.is_active.is_(True), Crisis.merged_into.is_(None), Crisis.type == crisis.type)
                  .order_by(Crisis.date_start.desc()).limit(400).all())
    scored = []
    for c in candidates:
        if not (crisis.date_start and c.date_start) or abs((crisis.date_start - c.date_start).days) > 60:
            continue
        same_country = bool(crisis.country and c.country and crisis.country.lower() == c.country.lower())
        near = math.hypot(crisis.latitude - c.latitude, crisis.longitude - c.longitude) < 5
        if not (same_country or near):
            continue
        days = abs((crisis.date_start - c.date_start).days)
        scored.append((days - (30 if same_country else 0), c))
    scored.sort(key=lambda pair: pair[0])
    return [c.to_dict() for _, c in scored[:limit]]


def build_parties(session, crisis):
    """The actors the event involves: code, name and, for states, the country code that opens the country analysis."""
    codes = [c for c in (crisis.stakeholders or '').split(',') if c]
    if not codes:
        return []
    found = {a.id: a for a in session.query(Actor).filter(Actor.id.in_(codes)).all()}
    out = []
    for code in codes:
        actor = found.get(code)
        if not actor:
            continue
        is_state = (actor.category or '').upper() == 'STATE' and len(code) == 2
        out.append({'code': code, 'name': actor.name, 'country_code': code if is_state else None})
    return out


def get_event_analysis(crisis_id):
    """{'pattern', 'related'} for the event, or None when it does not exist. Cached briefly."""
    key = f'event_analysis:v2:{crisis_id}'
    cached = cache_get(key)
    if cached is not None:
        return cached
    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            return None
        result = {'crisis_id': crisis_id, 'country_code': _iso2_for(crisis.country), 'pattern': build_pattern(session, crisis),
                  'related': build_related(session, crisis), 'parties': build_parties(session, crisis)}
    finally:
        session.close()
    cache_set(key, result, ttl=15 * 60)
    return result
