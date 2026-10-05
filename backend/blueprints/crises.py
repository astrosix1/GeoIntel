"""
Crisis endpoints — listing, detail, update, and the enhanced-analysis
endpoints (reliability, related, real-headline, escalation, economic,
briefing, history, full-analysis).
"""
import logging
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from models import Session, Crisis, News
from data_sources import fetch_real_page_metadata
from cache import cache_get, cache_set
from extensions import limiter
from services.auth import check_admin_key
from services.reliability import calculate_source_reliability, calculate_source_reliability_batch
from services.escalation import analyze_escalation
from services.economic import get_economic_impact
from services.briefing import generate_ai_briefing
from services.history import generate_deep_history
from services.scenarios import generate_scenarios, ScenariosUnavailable
from services.location_refine import refine_crisis_location
from services.stories import canonical_id
from services.gating import require_premium
from services.realtime import broadcast_new_crisis

logger = logging.getLogger(__name__)

crises_bp = Blueprint('crises', __name__, url_prefix='/api/crises')

# List sizing. GDELT adds ~11k events/day, so a window longer than
# SHORT_WINDOW_DAYS is ranked by severity and capped at LONG_WINDOW_CAP;
# MAX_LIST_LIMIT is a hard ceiling on any single response.
SHORT_WINDOW_DAYS = 2
LONG_WINDOW_CAP = 10000
MAX_LIST_LIMIT = 30000


def _list_response(payload, view):
    """jsonify the list payload; the lean map view carries no per-user data,
    so it's safe for Vercel's edge to cache (s-maxage) instead of every
    visitor hitting Flask after the 60s in-process cache lapses."""
    response = jsonify(payload)
    if view == 'map':
        response.headers['Cache-Control'] = 'public, max-age=30, s-maxage=60, stale-while-revalidate=300'
    return response


@crises_bp.route('', methods=['GET'])
def get_crises():
    """Get all active crises with enhanced data"""
    try:
        # Build a deterministic cache key from query params
        crisis_type     = request.args.get('type', '')
        status          = request.args.get('status', '')
        min_severity    = request.args.get('min_severity', '0')
        days            = request.args.get('days', '')
        include_analysis = request.args.get('include_analysis', 'false').lower()
        # 'all' (the default) preserves existing behavior for every caller
        # that doesn't pass this param — only an explicit ?scope=global or
        # ?scope=local narrows the result set.
        scope           = request.args.get('scope', 'all').lower()
        # view=map returns only the fields the globe/list actually read
        # (~250 B/row instead of ~815 B) — the full row stays available via
        # GET /api/crises/<id>. Any other value keeps the full shape.
        view            = request.args.get('view', 'full').lower()
        limit_arg       = request.args.get('limit', '')
        try:
            days_int = int(days) if days else None
            limit_int = int(limit_arg) if limit_arg else None
        except ValueError:
            return jsonify({'error': 'days and limit must be integers'}), 400
        cache_key = f"crises:list:{crisis_type}:{status}:{min_severity}:{days}:{include_analysis}:{scope}:{view}:{limit_arg}"

        cached = cache_get(cache_key)
        if cached is not None:
            return _list_response(cached, view)

        session = Session()
        min_severity_int = int(min_severity)

        query = session.query(Crisis).filter(Crisis.is_active == True)

        if crisis_type:
            query = query.filter(Crisis.type == crisis_type)

        if status:
            query = query.filter(Crisis.status == status)

        query = query.filter(Crisis.severity >= min_severity_int)

        if scope in ('global', 'local'):
            query = query.filter(Crisis.scope == scope)

        # Only apply date window if caller explicitly requests it
        if days_int is not None:
            since = datetime.utcnow() - timedelta(days=days_int)
            query = query.filter(Crisis.date_start >= since)

        # Ordering and cap. Unwindowed requests keep the original behavior
        # (severity desc, no cap). A short window (<= 2 days) is newest-first
        # so the cap, if hit, drops the oldest; a longer window is ranked
        # severity-then-recency and capped, since GDELT adds ~11k events/day
        # and an uncapped week is far more than a phone can render.
        limit = limit_int
        if days_int is None:
            query = query.order_by(Crisis.severity.desc())
        elif days_int <= SHORT_WINDOW_DAYS:
            query = query.order_by(Crisis.date_start.desc(), Crisis.severity.desc())
            limit = min(limit or MAX_LIST_LIMIT, MAX_LIST_LIMIT)
        else:
            query = query.order_by(Crisis.severity.desc(), Crisis.date_start.desc())
            limit = min(limit or LONG_WINDOW_CAP, LONG_WINDOW_CAP)
        if limit is not None:
            query = query.limit(min(limit, MAX_LIST_LIMIT))

        if view == 'map':
            # Column tuples straight from the DB — skips ORM object
            # hydration and to_dict() for what can be tens of thousands of rows.
            rows = query.with_entities(
                Crisis.id, Crisis.title, Crisis.country, Crisis.type, Crisis.severity,
                Crisis.scope, Crisis.date_start, Crisis.latitude, Crisis.longitude,
                Crisis.source_url, Crisis.location_confidence, Crisis.event_kind, Crisis.source_count,
            ).all()
            result = [
                {
                    'id': r.id,
                    'title': r.title,
                    'country': r.country,
                    'type': r.type,
                    'severity': r.severity,
                    'scope': r.scope or 'global',
                    'date': r.date_start.isoformat() if r.date_start else None,
                    'lat': r.latitude,
                    'lon': r.longitude,
                    'source_url': r.source_url,
                    'location_confidence': r.location_confidence,
                    # Only present when true, to keep the payload small.
                    **({'statement': True} if r.event_kind == 'statement' else {}),
                    **({'sources': r.source_count} if (r.source_count or 1) > 1 else {}),
                }
                for r in rows
            ]
        else:
            crises = query.all()

            # When analysis is requested, fetch reliability data for all crises in
            # one batched query instead of one query per crisis (N+1 avoidance).
            reliability_by_id = {}
            if include_analysis == 'true':
                reliability_by_id = calculate_source_reliability_batch([c.id for c in crises])

            result = []
            for c in crises:
                crisis_dict = c.to_dict()

                # Add enhanced analysis if requested
                if include_analysis == 'true':
                    crisis_dict['source_reliability'] = reliability_by_id.get(c.id)
                    # Pass the already-loaded crisis row to skip a redundant lookup query
                    crisis_dict['escalation'] = analyze_escalation(c.id, _crisis=c)

                result.append(crisis_dict)

        session.close()

        response = {
            'count': len(result),
            'crises': result,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Cache for 60s (crises don't change second-to-second)
        cache_set(cache_key, response, ttl=60)

        return _list_response(response, view)

    except Exception as e:
        logger.error(f"Error fetching crises: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@crises_bp.route('/balanced', methods=['GET'])
def get_balanced_crises():
    """Return crises geographically balanced across 5 world regions.

    No single region can exceed 30% of the total result set.
    Useful for the globe view to ensure worldwide coverage.
    """
    try:
        days = request.args.get('days', '30')
        per_region = request.args.get('per_region', '40')
        cache_key = f"crises:balanced:{days}:{per_region}"

        cached = cache_get(cache_key)
        if cached is not None:
            return jsonify(cached)

        session = Session()
        days = int(days)
        per_region = int(per_region)

        REGIONS = {
            'americas':    {'lat_min': -60, 'lat_max': 80,  'lon_min': -180, 'lon_max': -30},
            'europe':      {'lat_min': 35,  'lat_max': 71,  'lon_min': -25,  'lon_max': 45},
            'africa':      {'lat_min': -35, 'lat_max': 37,  'lon_min': -20,  'lon_max': 52},
            'asia_pacific':{'lat_min': -50, 'lat_max': 55,  'lon_min': 50,   'lon_max': 180},
            'mena':        {'lat_min': 12,  'lat_max': 43,  'lon_min': -18,  'lon_max': 65},
        }

        since = datetime.utcnow() - timedelta(days=days)
        all_crises = []
        seen_ids = set()

        for region_name, bounds in REGIONS.items():
            region_crises = (
                session.query(Crisis)
                .filter(
                    Crisis.is_active == True,
                    Crisis.date_start >= since,
                    Crisis.latitude  >= bounds['lat_min'],
                    Crisis.latitude  <= bounds['lat_max'],
                    Crisis.longitude >= bounds['lon_min'],
                    Crisis.longitude <= bounds['lon_max'],
                )
                .order_by(Crisis.severity.desc())
                .limit(per_region)
                .all()
            )

            for c in region_crises:
                if c.id not in seen_ids:
                    d = c.to_dict()
                    d['region'] = region_name
                    all_crises.append(d)
                    seen_ids.add(c.id)

        session.close()

        # Sort combined results by severity
        all_crises.sort(key=lambda x: x.get('severity', 0), reverse=True)

        response = {
            'count': len(all_crises),
            'crises': all_crises,
            'regions': list(REGIONS.keys()),
            'timestamp': datetime.utcnow().isoformat(),
        }

        # Globe view — cache for 90s (heavier query, changes slowly)
        cache_set(cache_key, response, ttl=90)

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error fetching balanced crises: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@crises_bp.route('/<crisis_id>', methods=['GET'])
def get_crisis_detail(crisis_id):
    """Get detailed info on specific crisis"""
    try:
        session = Session()

        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            session.close()
            return jsonify({'error': 'Crisis not found'}), 404

        # An event that was merged into a story opens as that story, so old links,
        # saved ids and bookmarks keep working.
        requested_id = crisis_id
        if crisis.merged_into:
            story = session.query(Crisis).filter(Crisis.id == crisis.merged_into).first()
            if story:
                crisis, crisis_id = story, story.id

        # Every source behind the story, earliest first.
        news = (session.query(News).filter(News.crisis_id == crisis_id)
                .order_by(News.published_at.asc()).limit(50).all())

        result = crisis.to_dict()
        result['news'] = [n.to_dict() for n in news]
        if requested_id != crisis_id:
            result['merged_from'] = requested_id

        session.close()

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching crisis detail: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@crises_bp.route('/<crisis_id>', methods=['PATCH'])
@limiter.limit("10 per minute")
def update_crisis(crisis_id):
    """Update crisis data (admin endpoint)"""
    if not check_admin_key():
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        session = Session()

        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            session.close()
            return jsonify({'error': 'Crisis not found'}), 404

        data = request.get_json()

        # Allow updates to severity, analysis, impact, stakeholders
        allowed_fields = ['severity', 'confidence', 'analysis', 'impact', 'stakeholders', 'is_verified', 'status']

        for field in allowed_fields:
            if field in data:
                setattr(crisis, field, data[field])

        if 'date_scheduled' in data:
            crisis.date_scheduled = datetime.fromisoformat(data['date_scheduled']) if data['date_scheduled'] else None

        crisis.date_updated = datetime.utcnow()
        session.commit()

        result = crisis.to_dict()

        session.close()

        # Broadcast update to clients
        broadcast_new_crisis(result)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error updating crisis: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@crises_bp.route('/<crisis_id>/reliability', methods=['GET'])
def get_crisis_reliability(crisis_id):
    """Get source reliability analysis for a crisis"""
    try:
        reliability = calculate_source_reliability(crisis_id)
        return jsonify(reliability)
    except Exception as e:
        logger.error(f"Error analyzing reliability: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@crises_bp.route('/<crisis_id>/related', methods=['GET'])
def get_related_crises(crisis_id):
    """
    Other real crises related to this one — replaces the old News tab's
    per-crisis article list (which silently fabricated headlines via
    _generate_contextual_news when nothing real was indexed). No
    similarity model here either, just real, already-available signals:
    a shared stakeholder (an actual matched Actor in both crises' real
    `stakeholders` field) is the strongest real relatedness signal
    available, so it's weighted highest; same `type`, geographic
    proximity, and temporal proximity follow, each a weaker signal than
    the last. Every match is traceable back to a real column, never
    invented.
    """
    try:
        session = Session()
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            session.close()
            return jsonify({'error': 'Crisis not found'}), 404

        my_stakeholders = set(filter(None, (crisis.stakeholders or '').split(',')))
        candidates = session.query(Crisis).filter(
            Crisis.id != crisis_id,
            Crisis.is_active == True,
        ).all()

        import math
        scored = []
        for c in candidates:
            score = 0.0

            their_stakeholders = set(filter(None, (c.stakeholders or '').split(',')))
            shared = my_stakeholders & their_stakeholders
            if shared:
                score += 50 * len(shared)

            if c.type == crisis.type:
                score += 20

            if crisis.country and c.country and crisis.country == c.country:
                score += 15
            elif None not in (crisis.latitude, crisis.longitude, c.latitude, c.longitude):
                dist = math.sqrt((crisis.latitude - c.latitude) ** 2 + (crisis.longitude - c.longitude) ** 2)
                if dist < 5:
                    score += 10 * (1 - dist / 5)

            if crisis.date_start and c.date_start:
                days_apart = abs((crisis.date_start - c.date_start).days)
                if days_apart <= 60:
                    score += 5 * (1 - days_apart / 60)

            if score > 0:
                scored.append((score, c))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        result = [c.to_dict() for _, c in scored[:8]]

        session.close()
        return jsonify({'crisis_id': crisis_id, 'count': len(result), 'related': result})
    except Exception as e:
        logger.error(f"Error fetching related crises for {crisis_id}: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@crises_bp.route('/<crisis_id>/real-headline', methods=['GET'])
@limiter.limit("30 per minute")
def get_crisis_real_headline(crisis_id):
    """
    Real article title for a crisis whose stored title is auto-generated,
    fetched from the crisis's real source_url and cached. (GDELT titles are
    now resolved at sync time; this remains for older rows.) Locations are
    refined separately, see refine_crisis_location / POST .../refine-location.

    Returns {title: None} (not an error) when there's no source_url or the
    fetch fails.
    """
    try:
        cache_key = f"real_headline:{crisis_id}"
        cached = cache_get(cache_key)
        if cached is not None:
            return jsonify(cached)

        session = Session()
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        source_url = crisis.source_url if crisis else None
        session.close()

        if not crisis:
            return jsonify({'error': 'Crisis not found'}), 404

        result = {'title': None, 'location': None}
        page = fetch_real_page_metadata(source_url) if source_url else None
        if page:
            result['title'] = page.get('title')

        # Cache even an empty result: an unreachable or paywalled URL will not
        # start working a minute later.
        cache_set(cache_key, result, ttl=2592000)  # 30 days
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching real headline for {crisis_id}: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@crises_bp.route('/<crisis_id>/refine-location', methods=['POST'])
@limiter.limit("20 per minute")
@require_premium
def post_refine_location(crisis_id):
    """Refine one event's pin from its source article (premium: it can cost an
    AI call and a geocoder lookup). Idempotent: an event that already has a
    definite answer returns it without any external call. Returns
    {status: 'refined'|'none', location?}; 503 when the AI or geocoder is
    unavailable right now (try again later)."""
    try:
        result = refine_crisis_location(crisis_id)
    except Exception as e:
        logger.error(f"Error refining location for {crisis_id}: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500
    if result['status'] == 'not_found':
        return jsonify({'error': 'Crisis not found'}), 404
    if result['status'] == 'unavailable':
        return jsonify({'error': 'location_refinement_unavailable', 'reason': result.get('reason')}), 503
    return jsonify(result)


@crises_bp.route('/<crisis_id>/escalation', methods=['GET'])
def get_crisis_escalation(crisis_id):
    """Get escalation trajectory analysis for a crisis"""
    try:
        escalation = analyze_escalation(crisis_id)
        if escalation:
            return jsonify(escalation)
        else:
            return jsonify({'error': 'Crisis not found'}), 404
    except Exception as e:
        logger.error(f"Error analyzing escalation: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@crises_bp.route('/<crisis_id>/economic', methods=['GET'])
def get_crisis_economic_impact(crisis_id):
    """Get economic impact analysis for a crisis"""
    try:
        economic = get_economic_impact(crisis_id)
        if economic:
            return jsonify(economic)
        else:
            return jsonify({'error': 'Crisis not found'}), 404
    except Exception as e:
        logger.error(f"Error analyzing economic impact: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@crises_bp.route('/<crisis_id>/briefing', methods=['GET'])
def get_crisis_briefing(crisis_id):
    """Get AI-generated briefing summary for a crisis"""
    try:
        briefing = generate_ai_briefing(canonical_id(crisis_id))
        if briefing:
            return jsonify(briefing)
        else:
            return jsonify({
                'error': 'AI briefing unavailable',
                'message': 'ANTHROPIC_API_KEY not configured'
            }), 503
    except Exception as e:
        logger.error(f"Error generating briefing: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@crises_bp.route('/<crisis_id>/scenarios', methods=['GET'])
@limiter.limit("10 per minute")
@require_premium
def get_crisis_scenarios(crisis_id):
    """Premium: AI-generated branch scenarios for a crisis. Enforced here on
    the server (401 sign-in / 403 upgrade from require_premium), not just by a
    locked button. 503 when the model isn't configured or fails — there is no
    static fallback, so the UI shows an honest 'unavailable'."""
    try:
        result = generate_scenarios(canonical_id(crisis_id))
        if result is None:
            return jsonify({'error': 'Crisis not found'}), 404
        return jsonify(result)
    except ScenariosUnavailable as e:
        return jsonify({'error': 'scenarios_unavailable', 'reason': e.reason}), 503
    except Exception as e:
        logger.error(f"Error generating scenarios: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@crises_bp.route('/<crisis_id>/history', methods=['GET'])
def get_crisis_history(crisis_id):
    """Get AI-generated deep historical background, timeline, and historical-analogy match for a crisis"""
    try:
        history = generate_deep_history(crisis_id)
        if history:
            return jsonify(history)
        else:
            return jsonify({
                'error': 'Deep history unavailable',
                'message': 'Crisis not found or generation failed'
            }), 503
    except Exception as e:
        logger.error(f"Error generating deep history: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


@crises_bp.route('/<crisis_id>/full-analysis', methods=['GET'])
def get_crisis_full_analysis(crisis_id):
    """Get complete analysis package for a crisis (all features)"""
    try:
        session = Session()
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()

        if not crisis:
            session.close()
            return jsonify({'error': 'Crisis not found'}), 404

        crisis_dict = crisis.to_dict()
        news = session.query(News).filter(News.crisis_id == crisis_id).limit(10).all()

        session.close()

        result = crisis_dict
        result['news'] = [n.to_dict() for n in news]
        result['reliability'] = calculate_source_reliability(crisis_id)
        result['escalation'] = analyze_escalation(crisis_id)
        result['economic'] = get_economic_impact(crisis_id)
        result['briefing'] = generate_ai_briefing(crisis_id)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error generating full analysis: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500
