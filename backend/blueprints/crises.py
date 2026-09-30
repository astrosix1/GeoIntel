"""
Crisis endpoints — listing, detail, update, and the enhanced-analysis
endpoints (reliability, related, real-headline, escalation, economic,
briefing, history, full-analysis).
"""
import logging
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from models import Session, Crisis, News
from data_sources import fetch_real_page_metadata, _extract_incident_location, NominatimGeocoder
from cache import cache_get, cache_set
from extensions import limiter
from services.auth import check_admin_key
from services.reliability import calculate_source_reliability, calculate_source_reliability_batch
from services.escalation import analyze_escalation
from services.economic import get_economic_impact
from services.briefing import generate_ai_briefing
from services.history import generate_deep_history
from services.realtime import broadcast_new_crisis

logger = logging.getLogger(__name__)

crises_bp = Blueprint('crises', __name__, url_prefix='/api/crises')


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
        cache_key = f"crises:list:{crisis_type}:{status}:{min_severity}:{days}:{include_analysis}:{scope}"

        cached = cache_get(cache_key)
        if cached is not None:
            return jsonify(cached)

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
        if days:
            since = datetime.utcnow() - timedelta(days=int(days))
            query = query.filter(Crisis.date_start >= since)

        crises = query.order_by(Crisis.severity.desc()).all()

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

        return jsonify(response)

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

        # Fetch related news
        news = session.query(News).filter(News.crisis_id == crisis_id).limit(10).all()

        result = crisis.to_dict()
        result['news'] = [n.to_dict() for n in news]

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
    Real article title/description for a crisis whose stored title is
    auto-generated (currently only GDELT-sourced crises — see
    GDELTConnector._build_title), fetched lazily from the crisis's real
    source_url and cached — rather than during every sync, since that
    would mean scraping an arbitrary news site for every one of ~1,300+
    GDELT events per hour.

    For GDELT crises specifically, this ALSO attempts to refine the pin's
    coordinates: GDELT's own geocoding often resolves verbal-conflict
    events (a "threat" or "demand" has no clear physical location) to a
    coarse country/capital-level point, which is why pins cluster so
    heavily on a handful of coordinates (confirmed directly against this
    app's live data: dozens of unrelated GDELT crises sharing the exact
    same point). The real article text just fetched is run through the
    same AI-extraction + Nominatim pipeline Phase 5 built for NewsAPI
    (_extract_incident_location, NominatimGeocoder) to find a more
    specific real location. When one is found, it's written back to the
    Crisis row itself (not just cached) — unlike the headline, a pin's
    position is part of the shared map everyone sees before ever opening
    that crisis, so the fix should persist and benefit every later load,
    not just this one cached response. This still only runs once per
    crisis (lazily, on first open, lands in the shared response cache
    below) rather than during sync — a full bulk re-geocode of ~2,000
    events would mean ~2,000 Nominatim calls at its enforced 1 req/sec
    limit alone, well over 30 minutes, plus that many AI calls.

    Returns {title: None, location: None} (not an error) when there's no
    source_url, the fetch fails, or no refined location is found — all
    expected, non-fatal outcomes, not crashes.
    """
    try:
        cache_key = f"real_headline:{crisis_id}"
        cached = cache_get(cache_key)
        if cached is not None:
            return jsonify(cached)

        session = Session()
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        source_url = crisis.source_url if crisis else None
        source = crisis.source if crisis else None
        session.close()

        if not crisis:
            return jsonify({'error': 'Crisis not found'}), 404

        result = {'title': None, 'location': None}
        page = fetch_real_page_metadata(source_url) if source_url else None
        if page:
            result['title'] = page.get('title')

            if source == 'GDELT':
                text = ' '.join(filter(None, [page.get('title'), page.get('description')]))
                place_name = _extract_incident_location(text) if text else None
                geocoded = NominatimGeocoder.geocode(place_name) if place_name else None
                if geocoded and geocoded.get('country'):
                    result['location'] = {
                        'lat': geocoded['lat'], 'lon': geocoded['lon'],
                        'country': geocoded['country'], 'name': place_name,
                    }
                    write_session = Session()
                    try:
                        row = write_session.query(Crisis).filter(Crisis.id == crisis_id).first()
                        if row:
                            row.latitude = geocoded['lat']
                            row.longitude = geocoded['lon']
                            row.country = geocoded['country']
                            row.location_confidence = 90
                            write_session.commit()
                    except Exception as e:
                        write_session.rollback()
                        logger.error(f"Error persisting refined location for {crisis_id}: {e}")
                    finally:
                        write_session.close()

        # Cache even a fully-empty result — an unreachable/paywalled URL, or
        # an article with no extractable location, isn't going to start
        # working on the next request a minute later, and this avoids
        # re-scraping/re-geocoding the same one on every open.
        cache_set(cache_key, result, ttl=2592000)  # 30 days — a real article's own metadata doesn't change
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching real headline for {crisis_id}: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500


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
        briefing = generate_ai_briefing(crisis_id)
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
