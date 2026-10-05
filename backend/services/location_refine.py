"""Refine a GDELT event's pin from its source article.

GDELT places an event at the centre of the place its article names (a city, a
state, often just the country), not at the site, so pins pile up on a few
points. The article's headline usually names the actual place: the AI picks
it, Nominatim geocodes it, and the event's coordinates are updated.

The place is read from the story's extracted facts (services/story_facts.py), so
one model call serves location, severity and analysis.

Rules that keep this honest:
  * Only a result in the SAME country as the event is accepted. Anything else
    (an ambiguous place name, a mismatch we can't explain) is thrown away, so
    we get fewer refinements but never a pin in the wrong country.
  * An attempt that finished with a definite answer, refined or "nothing
    usable", is recorded on the row (location_refined_at) and never repeated,
    so the paid lookup runs once per event, even across restarts.
  * A transient failure (no API key, model or geocoder outage) is not recorded
    and is retried later.
"""
import logging
import os
import threading
import time
from datetime import datetime

from cache import cache_clear_prefix
from data_sources import NominatimGeocoder
from models import Session, Crisis
from services.story_facts import ensure_facts, facts_available

logger = logging.getLogger(__name__)

# The refined position is stored with this confidence (the feed's own city-level
# positions are 85).
REFINED_CONFIDENCE = 90
DEFAULT_PER_RUN = 60
RUN_TIME_BUDGET_SECONDS = 8 * 60
STOP_AFTER_CONSECUTIVE_UNAVAILABLE = 3

# --- country comparison -------------------------------------------------------
# GDELT and Nominatim both use English country names but not always the same
# ones. Each group below is one country under several names.
_COUNTRY_GROUPS = [
    ('united states', 'united states of america', 'usa', 'us'),
    ('united kingdom', 'uk', 'great britain'),
    ('russia', 'russian federation'),
    ('czechia', 'czech republic'),
    ('turkey', 'turkiye', 'türkiye'),
    ('myanmar', 'burma', 'myanmar (burma)'),
    ('palestine', 'palestinian territories', 'palestinian territory', 'state of palestine', 'west bank', 'gaza strip'),
    ('south korea', 'korea, south', 'republic of korea'),
    ('north korea', 'korea, north', 'democratic people\'s republic of korea'),
    ('democratic republic of the congo', 'congo (kinshasa)', 'congo, democratic republic of the', 'dr congo', 'drc'),
    ('republic of the congo', 'congo (brazzaville)', 'congo-brazzaville', 'congo'),
    ('ivory coast', "côte d'ivoire", "cote d'ivoire"),
    ('eswatini', 'swaziland'),
    ('north macedonia', 'macedonia'),
    ('east timor', 'timor-leste'),
    ('cape verde', 'cabo verde'),
    ('bahamas', 'the bahamas'),
    ('gambia', 'the gambia'),
    ('vatican city', 'holy see', 'vatican'),
]
_CANONICAL = {name: group[0] for group in _COUNTRY_GROUPS for name in group}


def canonical_country(name):
    """A comparable form of a country name, or None for a blank one."""
    if not isinstance(name, str):
        return None
    cleaned = ' '.join(name.lower().split())
    if not cleaned:
        return None
    return _CANONICAL.get(cleaned, _CANONICAL.get(cleaned.removeprefix('the '), cleaned.removeprefix('the ')))


def same_country(a, b):
    ca, cb = canonical_country(a), canonical_country(b)
    return ca is not None and ca == cb


# --- single event -------------------------------------------------------------
_in_progress = set()
_guard = threading.Lock()


def _stored_outcome(row):
    if row['location_refined_name']:
        return {
            'status': 'refined',
            'location': {'lat': row['latitude'], 'lon': row['longitude'], 'name': row['location_refined_name'],
                         'country': row['country']},
        }
    return {'status': 'none'}


def _record(crisis_id, **changes):
    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if crisis is None:
            return
        for key, value in changes.items():
            setattr(crisis, key, value)
        crisis.location_refined_at = datetime.utcnow()
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Could not record location refinement for {crisis_id}: {e}")
        raise
    finally:
        session.close()


def refine_crisis_location(crisis_id):
    """{'status': 'refined'|'none'|'unavailable'|'not_found', 'location'?}.

    Idempotent: an event that already has a definite answer returns it without
    any network call. Safe to call from several threads; a second caller for the
    same event while one is running gets 'unavailable' and can try again.
    """
    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if crisis is None:
            return {'status': 'not_found'}
        row = {
            'source': crisis.source, 'source_url': crisis.source_url, 'country': crisis.country,
            'latitude': crisis.latitude, 'longitude': crisis.longitude,
            'location_refined_at': crisis.location_refined_at,
            'location_refined_name': crisis.location_refined_name,
            'event_kind': crisis.event_kind,
        }
    finally:
        session.close()

    if row['location_refined_at'] is not None:
        return _stored_outcome(row)
    if row['source'] != 'GDELT':
        return {'status': 'none'}   # other sources carry their own coordinates
    if row['event_kind'] == 'statement':
        # Talks, criticism and threats have no physical site: nothing to refine
        # to. Not recorded, so no paid lookup is ever spent on them.
        return {'status': 'none', 'reason': 'statement'}
    if not facts_available():
        return {'status': 'unavailable', 'reason': 'ai_not_configured'}

    with _guard:
        if crisis_id in _in_progress:
            return {'status': 'unavailable', 'reason': 'in_progress'}
        _in_progress.add(crisis_id)
    try:
        return _refine(crisis_id, row)
    finally:
        with _guard:
            _in_progress.discard(crisis_id)


def _refine(crisis_id, row):
    # The place comes from the story's extracted facts: one model call per story,
    # shared with severity and analysis, and never repeated.
    outcome = ensure_facts(crisis_id)
    if outcome['status'] == 'unavailable':
        return {'status': 'unavailable', 'reason': outcome.get('reason', 'ai_failed')}
    facts = outcome.get('facts')
    if not facts or facts.get('is_statement') or not facts.get('place'):
        # Nothing usable, or a statement with no physical site.
        _record(crisis_id)
        return {'status': 'none'}
    place = facts['place']

    if same_country(place, row['country']):
        _record(crisis_id)      # just the country: no more precise than today
        return {'status': 'none'}

    geocoded, geocode_failed = NominatimGeocoder.geocode_status(place)
    if geocode_failed:
        return {'status': 'unavailable', 'reason': 'geocoder_failed'}
    if not geocoded or not same_country(geocoded.get('country'), row['country']):
        _record(crisis_id)
        return {'status': 'none'}

    _record(crisis_id, latitude=geocoded['lat'], longitude=geocoded['lon'],
            location_confidence=REFINED_CONFIDENCE, location_refined_name=place[:200])
    cache_clear_prefix('crises:')
    return {
        'status': 'refined',
        'location': {'lat': geocoded['lat'], 'lon': geocoded['lon'], 'name': place[:200], 'country': row['country']},
    }


# --- background batch ---------------------------------------------------------

def per_run_limit():
    try:
        return max(0, int(os.getenv('LOCATION_REFINE_PER_RUN', DEFAULT_PER_RUN)))
    except ValueError:
        return DEFAULT_PER_RUN


def refine_pending(limit=None):
    """Refine not-yet-refined physical events (GDELT, active, global; statements
    have no site to find), stories with the most sources first, then newest. Stops early when the AI or geocoder looks down or the
    time budget is spent. Returns a summary and never raises."""
    limit = per_run_limit() if limit is None else limit
    summary = {'attempted': 0, 'refined': 0, 'none': 0, 'unavailable': 0, 'stopped': None}
    if limit <= 0:
        summary['stopped'] = 'disabled'
        return summary
    try:
        session = Session()
        try:
            ids = [
                row.id for row in session.query(Crisis.id)
                .filter(Crisis.source == 'GDELT', Crisis.is_active.is_(True), Crisis.scope == 'global',
                        Crisis.event_kind == 'physical', Crisis.location_refined_at.is_(None))
                .order_by(Crisis.source_count.desc(), Crisis.date_start.desc())
                .limit(limit)
            ]
        finally:
            session.close()

        started = time.monotonic()
        consecutive_unavailable = 0
        for crisis_id in ids:
            if time.monotonic() - started > RUN_TIME_BUDGET_SECONDS:
                summary['stopped'] = 'time_budget'
                break
            result = refine_crisis_location(crisis_id)
            status = result['status']
            summary['attempted'] += 1
            if status in ('refined', 'none'):
                summary[status] += 1
                consecutive_unavailable = 0
            elif status == 'unavailable':
                summary['unavailable'] += 1
                consecutive_unavailable += 1
                if consecutive_unavailable >= STOP_AFTER_CONSECUTIVE_UNAVAILABLE:
                    summary['stopped'] = 'unavailable'
                    break
    except Exception as e:  # keep the scheduler job alive whatever happens
        logger.error(f"Location refinement run failed: {e}")
        summary['stopped'] = 'error'
    if summary['refined'] or summary['none']:
        logger.info(f"Location refinement: {summary}")
    return summary
