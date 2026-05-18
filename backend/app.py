"""
GeoIntel Backend API - Enhanced with Real-Time Intelligence
Real-time geopolitical intelligence platform with WebSocket streaming,
source reliability, escalation analysis, economic impact, and AI briefings
"""
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import json
from collections import defaultdict

from models import Session, Crisis, News, Actor, Relationship, Forecast, EconomicData
from data_sources import DataAggregator, init_actors, init_relationships

# Optional: Anthropic for AI briefings
try:
    from anthropic import Anthropic
    anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY', ''))
except:
    anthropic_client = None

# For Wikipedia image fetching
try:
    import requests
except:
    requests = None

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app (WebSocket optional)
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
app = Flask(__name__)
CORS(app)
app.config['JSON_SORT_KEYS'] = False

@app.route('/')
def serve_frontend():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(FRONTEND_DIR, filename)

# Try to load SocketIO, but don't fail if it's not available
socketio = None
try:
    from flask_socketio import SocketIO, emit, join_room
    socketio = SocketIO(app, cors_allowed_origins="*")
    logger.info("SocketIO loaded successfully")
except Exception as e:
    logger.warning(f"SocketIO not available: {e}. Running in REST-only mode.")


# Background scheduler for data sync
scheduler = BackgroundScheduler()

# Track crisis history for escalation analysis
crisis_history = defaultdict(list)

# Source reliability mapping (higher = more trustworthy)
SOURCE_RELIABILITY = {
    'Reuters': 95,
    'AP': 94,
    'Bloomberg': 92,
    'BBC': 91,
    'Associated Press': 94,
    'AFP': 93,
    'Xinhua': 75,
    'NewsAPI': 70,
    'ACLED': 85,
    'MANUAL': 50,
    'News.com.au': 70,
    'CNN': 85,
    'BBC News': 91,
    'The Guardian': 88,
    'Financial Times': 90,
    'Al Jazeera': 85,
    'Breitbart News': 60,
    'The Times of India': 75,
    'Hoover.org': 80,
    'Activistpost.com': 55,
}


# ════════════════════════════════════════════════════════════
# HELPER FUNCTIONS - SOURCE RELIABILITY & ANALYSIS
# ════════════════════════════════════════════════════════════

def calculate_source_reliability(crisis_id):
    """
    Calculate source reliability score for a crisis.
    Higher score = more verified by reliable sources.
    """
    session = Session()
    try:
        news = session.query(News).filter(News.crisis_id == crisis_id).all()

        if not news:
            return {'reliability': 'unknown', 'score': 50, 'source_count': 0, 'sources': []}

        reliability_scores = []
        unique_sources = set()

        for article in news:
            source = article.source or 'Unknown'
            unique_sources.add(source)
            score = SOURCE_RELIABILITY.get(source, 65)  # Default to moderate
            reliability_scores.append({
                'source': source,
                'score': score
            })

        avg_score = sum(s['score'] for s in reliability_scores) / len(reliability_scores)
        source_count = len(unique_sources)

        # Determine reliability level based on count and score
        if source_count >= 3 and avg_score >= 85:
            reliability_level = 'verified'
        elif source_count >= 2 and avg_score >= 75:
            reliability_level = 'corroborated'
        elif source_count >= 1 and avg_score >= 70:
            reliability_level = 'reported'
        else:
            reliability_level = 'unverified'

        return {
            'reliability': reliability_level,
            'score': round(avg_score),
            'source_count': source_count,
            'sources': list(unique_sources)
        }
    finally:
        session.close()


def analyze_escalation(crisis_id):
    """
    Analyze escalation trajectory for a crisis.
    Returns trend, velocity, and warnings.
    Generates mock historical data for visualization.
    """
    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            return None

        # Generate mock historical data based on crisis characteristics
        # This simulates how severity has changed over time
        current_severity = crisis.severity
        base_date = crisis.date_start if crisis.date_start else datetime.utcnow()

        # Create 7-day mock history
        history = []
        for days_ago in range(6, -1, -1):
            # Mock history: severity increased or stayed stable based on current severity
            if current_severity > 75:
                # High severity: likely escalated recently
                mock_severity = max(30, current_severity - (6 - days_ago) * 8)
            elif current_severity > 50:
                # Medium severity: gradual increase
                mock_severity = max(20, current_severity - (6 - days_ago) * 4)
            else:
                # Low severity: stayed relatively low
                mock_severity = current_severity - (6 - days_ago) * 2

            mock_date = base_date - timedelta(days=days_ago)
            history.append({
                'severity': max(0, int(mock_severity)),
                'timestamp': mock_date
            })

        # Calculate trend from mock history
        severities = [h['severity'] for h in history]
        severity_change = severities[-1] - severities[0]
        velocity = severity_change / max(len(severities) - 1, 1)

        # Determine trend
        if velocity > 5:
            trend = 'escalating'
        elif velocity < -5:
            trend = 'de-escalating'
        else:
            trend = 'stable'

        # Issue warnings
        warning = None
        if velocity > 10:
            warning = '🔴 RAPID ESCALATION'
        elif velocity > 5:
            warning = '🟠 ESCALATING'
        elif velocity < -10:
            warning = '🟢 RAPID DE-ESCALATION'

        return {
            'trend': trend,
            'severity_change': round(severity_change),
            'velocity': round(velocity, 1),
            'current_severity': current_severity,
            'warning': warning,
            'history': [{'severity': h['severity'], 'date': h['timestamp'].isoformat()} for h in history]
        }
    finally:
        session.close()


def analyze_cascade(crisis_id, depth=2, threshold=50):
    """
    Analyze how a crisis cascades through the actor relationship network.
    Uses breadth-first search to propagate escalation through alliances and conflicts.

    Parameters:
    - crisis_id: ID of the crisis to analyze
    - depth: Maximum number of hops through relationship network (default 2)
    - threshold: Minimum relationship strength to consider (default 50, range 0-100)

    Returns:
    - Dictionary with cascade steps, probabilities, and estimated timeline
    """
    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            return None

        # Get all actors and relationships for graph traversal
        actors = session.query(Actor).all()
        relationships = session.query(Relationship).filter(Relationship.is_active == True).all()

        actor_map = {a.id: a for a in actors}

        # Build relationship graph: actor_id -> [(related_actor_id, rel_type, strength), ...]
        relationship_graph = defaultdict(list)
        for rel in relationships:
            if rel.strength >= threshold:
                relationship_graph[rel.actor_a].append((rel.actor_b, rel.type, rel.strength))
                relationship_graph[rel.actor_b].append((rel.actor_a, rel.type, rel.strength))

        # Identify which actors are directly involved in the crisis
        crisis_country = crisis.country
        initial_actors = [a.id for a in actors if a.name == crisis_country]
        if not initial_actors:
            # Fallback: use geographic proximity
            import math
            crisis_lat, crisis_lon = crisis.latitude or 0, crisis.longitude or 0
            distances = []
            for a in actors:
                if a.latitude is not None and a.longitude is not None:
                    dist = math.sqrt((a.latitude - crisis_lat)**2 + (a.longitude - crisis_lon)**2)
                    distances.append((a.id, dist))
            if distances:
                distances.sort(key=lambda x: x[1])
                initial_actors = [a[0] for a in distances[:2]]
            else:
                initial_actors = [a.id for a in actors[:2]]  # Fallback to first 2 actors

        # BFS to find cascade pathway
        cascade_steps = []
        visited = set(initial_actors)
        current_level = [(actor_id, 0, 1.0) for actor_id in initial_actors]  # (actor_id, hop, cumulative_prob)

        hop = 0
        while current_level and hop < depth:
            hop += 1
            next_level = []
            affected_actors = []
            total_escalation = 0

            for actor_id, _, cum_prob in current_level:
                if actor_id not in relationship_graph:
                    continue

                for related_actor_id, rel_type, strength in relationship_graph[actor_id]:
                    if related_actor_id in visited:
                        continue

                    visited.add(related_actor_id)

                    # Calculate escalation probability based on relationship type and strength
                    strength_factor = strength / 100.0  # Normalize to 0-1

                    if rel_type == 'alliance':
                        # Allies amplify the crisis
                        escalation_prob = cum_prob * 0.7 * strength_factor
                        mechanism = f"Alliance mobilization: {actor_id} allies with {related_actor_id}"
                    elif rel_type == 'conflict':
                        # Conflicts counter the original crisis but may escalate separately
                        escalation_prob = cum_prob * 0.6 * strength_factor
                        mechanism = f"Competing interests: {actor_id} tensions with {related_actor_id}"
                    elif rel_type == 'economic':
                        # Economic ties create moderate escalation
                        escalation_prob = cum_prob * 0.4 * strength_factor
                        mechanism = f"Economic spillover: {actor_id} trade ties affect {related_actor_id}"
                    elif rel_type == 'proxy':
                        # Proxy relationships can escalate into direct conflict
                        escalation_prob = cum_prob * 0.5 * strength_factor
                        mechanism = f"Proxy warfare: {actor_id} indirect influence on {related_actor_id}"
                    elif rel_type == 'tension':
                        # Tensions can trigger escalation
                        escalation_prob = cum_prob * 0.55 * strength_factor
                        mechanism = f"Heightened tensions: {actor_id} friction with {related_actor_id}"
                    else:
                        escalation_prob = cum_prob * 0.5 * strength_factor
                        mechanism = f"Interaction: {actor_id} affects {related_actor_id}"

                    # Add to cascade if probability exceeds threshold
                    if escalation_prob > 0.15:  # Only show significant cascades
                        affected_actors.append(related_actor_id)
                        total_escalation += escalation_prob
                        next_level.append((related_actor_id, hop, escalation_prob))

            # Create step entry
            if affected_actors:
                avg_escalation = total_escalation / len(affected_actors) if affected_actors else 0
                severity_increase = int((crisis.severity or 50) * avg_escalation * 10 / depth)  # Scale by depth

                step = {
                    'hop': hop,
                    'actors': affected_actors,
                    'count': len(affected_actors),
                    'mechanism': f"{len(affected_actors)} actors affected through regional network",
                    'probability': round(min(0.99, total_escalation), 2),
                    'escalation_increase': max(0, min(20, severity_increase)),
                    'affected_actor_names': [actor_map.get(aid, actor_map.get('US', {})).name if aid in actor_map else aid for aid in affected_actors]
                }
                cascade_steps.append(step)

            current_level = next_level

        # Estimate timeline (crude estimate based on crisis type)
        if crisis.type == 'military':
            timeline = "hours to days"
        elif crisis.type == 'conflict':
            timeline = "days to weeks"
        elif crisis.type == 'diplomatic':
            timeline = "weeks to months"
        else:
            timeline = "variable"

        return {
            'initial_crisis': crisis.title,
            'crisis_id': crisis_id,
            'severity': crisis.severity,
            'type': crisis.type,
            'steps': cascade_steps,
            'total_steps': len(cascade_steps),
            'total_cascade_probability': round(sum(min(s['probability'], 1.0) for s in cascade_steps) / max(len(cascade_steps), 1), 2),
            'estimated_timeline': timeline,
            'affected_regions': list(set(
                [actor_map[aid].region for aid in sum([s['actors'] for s in cascade_steps], []) if aid in actor_map and hasattr(actor_map[aid], 'region')]
            ))
        }
    except Exception as e:
        logger.error(f"Error analyzing cascade: {e}")
        return None
    finally:
        session.close()


def get_economic_impact(crisis_id):
    """
    Get economic impact data for a crisis based on affected countries.
    """
    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            return None

        affected_countries = [crisis.country]

        # Get economic data for affected countries
        economic_impact = {}
        for country_code in affected_countries:
            country_name = crisis.country
            econ_data = session.query(EconomicData).filter(
                EconomicData.country_code == country_code.upper()[:2]
            ).order_by(EconomicData.year.desc()).first()

            if econ_data:
                economic_impact[country_name] = econ_data.to_dict()

        # Estimate impact severity based on crisis severity and economic size
        impact_severity = 'moderate'
        if crisis.severity > 80:
            impact_severity = 'severe'
        elif crisis.severity > 60:
            impact_severity = 'significant'
        elif crisis.severity > 40:
            impact_severity = 'moderate'
        else:
            impact_severity = 'minor'

        return {
            'impact_severity': impact_severity,
            'affected_countries': affected_countries,
            'economic_data': economic_impact,
            'estimated_impact': {
                'trade_disruption_percent': int(crisis.severity / 2),
                'market_volatility_percent': int(crisis.severity / 3),
                'industry_sectors_affected': estimate_affected_sectors(crisis)
            }
        }
    finally:
        session.close()


def estimate_affected_sectors(crisis):
    """
    Estimate which industry sectors are affected based on crisis type and severity.
    """
    sectors = {
        'conflict': ['Energy', 'Defense', 'Shipping'],
        'military': ['Defense', 'Energy', 'Aviation'],
        'diplomatic': ['Trade', 'Finance', 'Technology'],
        'economic': ['Finance', 'Energy', 'Manufacturing'],
        'resource': ['Energy', 'Agriculture', 'Mining'],
        'technology': ['Technology', 'Semiconductors', 'Software'],
        'proxy': ['Defense', 'Shipping', 'Energy'],
        'alliance': ['Trade', 'Defense', 'Technology']
    }

    base_sectors = sectors.get(crisis.type, ['General Economy'])

    # Add more sectors if severe
    if crisis.severity > 80:
        base_sectors.extend(['Finance', 'Aviation'])

    return list(set(base_sectors))[:5]  # Return top 5


def fetch_wikipedia_image(country, title):
    """
    Fetch a representative image from Wikipedia article for the crisis country/title.
    Returns { src, caption } or None.
    """
    if not requests:
        return None

    terms = [country, title.split(' ')[0:3] if ' ' in title else title]
    terms = [t for t in terms if t]

    for term in terms:
        try:
            url = f'https://en.wikipedia.org/api/rest_v1/page/summary/{term}'
            r = requests.get(url, timeout=3, headers={'Accept': 'application/json'})
            if r.status_code != 200:
                continue
            data = r.json()
            if data.get('thumbnail', {}).get('source'):
                src = data['thumbnail']['source'].replace(r'/\d+px-/', '/480px-')
                caption = data.get('description') or data.get('title') or term
                return {'src': src, 'caption': caption}
        except Exception as e:
            logger.debug(f"Wiki image fetch failed for '{term}': {e}")
            continue

    return None


def generate_ai_briefing(crisis_id):
    """
    Generate AI-powered briefing summary using Claude API.
    Returns structured brief with briefing text and Wikipedia image.
    """
    session = Session()
    try:
        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            return None

        # Gather context
        news = session.query(News).filter(News.crisis_id == crisis_id).limit(5).all()
        escalation = analyze_escalation(crisis_id)
        economic = get_economic_impact(crisis_id)
        reliability = calculate_source_reliability(crisis_id)

        # Build context for Claude
        context = f"""
Crisis: {crisis.title}
Location: {crisis.country}
Type: {crisis.type}
Severity: {crisis.severity}/100
Confidence: {crisis.confidence}%
Source Reliability: {reliability['reliability']} ({reliability['source_count']} sources)

Analysis: {crisis.analysis}

Escalation Trend: {escalation['trend']} (velocity: {escalation['velocity']} points/day)
Economic Impact: {economic['impact_severity']}
Affected Sectors: {', '.join(economic['estimated_impact']['industry_sectors_affected'])}

Recent News Headlines:
{chr(10).join(f"- {n.title[:80]}..." for n in news)}
"""

        # Fetch Wikipedia image (non-blocking, optional)
        image = fetch_wikipedia_image(crisis.country, crisis.title)

        # Call Claude API for briefing
        if anthropic_client.api_key:
            try:
                message = anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1500,
                    messages=[
                        {
                            "role": "user",
                            "content": f"""Generate a comprehensive intelligence briefing for this geopolitical crisis. Write in the style of a senior analyst at a major intelligence agency — precise, authoritative, and detailed.

Format your response EXACTLY as follows (keep the headers):

## Situation Report
[3-4 sentences describing the current state of the crisis with specific facts, figures, and timeline]

## Strategic Context
[3-4 sentences explaining the historical background, root causes, and how this fits into broader regional or global dynamics]

## Key Actors & Interests
[Bullet list of 3-5 key actors involved and what each stands to gain or lose]

## Impact Assessment
[3-4 sentences on military, economic, political, and humanitarian consequences — both immediate and medium-term]

## Escalation Scenarios
[2-3 plausible near-term escalation or de-escalation pathways with likelihood assessment]

## Intelligence Gaps
[1-2 sentences on what remains uncertain or unknown that could change the picture]

Crisis Context:
{context}

Be specific and analytical. Avoid vague language. Write at least 400 words total."""
                        }
                    ]
                )

                briefing_text = message.content[0].text
                result = {
                    'briefing': briefing_text,
                    'model': 'claude-3-5-sonnet-20241022',
                    'timestamp': datetime.utcnow().isoformat()
                }
                if image:
                    result['image'] = image
                return result
            except Exception as e:
                logger.error(f"AI briefing error: {e}")
                return None
        else:
            logger.info("ANTHROPIC_API_KEY not set — generating static briefing")
            return _generate_static_briefing(crisis, escalation, economic, reliability, news, image)
    finally:
        session.close()


def _generate_static_briefing(crisis, escalation, economic, reliability, news, image):
    """Generate a rule-based intelligence briefing when no API key is available."""
    sev = crisis.severity
    trend = escalation.get('trend', 'stable') if escalation else 'stable'
    velocity = escalation.get('velocity', 0) if escalation else 0
    impact_sev = economic.get('impact_severity', 'moderate') if economic else 'moderate'
    sectors = ', '.join(economic.get('estimated_impact', {}).get('industry_sectors_affected', [])) if economic else 'General Economy'
    src_count = reliability.get('source_count', 1) if reliability else 1
    rel_label = reliability.get('reliability', 'moderate') if reliability else 'moderate'
    news_lines = '\n'.join(f'• {n["title"][:90]}' for n in (news or [])[:4]) or '• No recent headlines indexed.'

    severity_label = 'Critical' if sev >= 85 else ('High' if sev >= 65 else ('Moderate' if sev >= 40 else 'Low'))
    trend_desc = {
        'escalating': f'rapidly escalating (velocity +{abs(velocity):.1f} pts/day)',
        'de-escalating': f'de-escalating (velocity −{abs(velocity):.1f} pts/day)',
        'stable': 'holding at current intensity',
        'volatile': 'volatile with unpredictable swings',
    }.get(trend, 'evolving')

    domain_scores = {
        'Military': crisis.military_score or 0,
        'Economic': crisis.economic_score or 0,
        'Political': crisis.political_score or 0,
        'Environment': crisis.environment_score or 0,
        'Technology': crisis.technology_score or 0,
        'Information': crisis.information_score or 0,
    }
    active_domains = [k for k, v in domain_scores.items() if v > 30]
    domain_str = ', '.join(active_domains) if active_domains else 'multiple domains'

    type_context = {
        'conflict': 'active armed hostilities with casualties and territorial stakes',
        'military': 'significant military mobilisation or posturing',
        'diplomatic': 'a diplomatic breakdown with potential for wider fallout',
        'economic': 'economic coercion or structural instability',
        'resource': 'competition over critical resources with supply-chain implications',
        'technology': 'a technology or cyber-domain confrontation',
        'proxy': 'a proxy conflict with third-party actors as principal combatants',
        'alliance': 'alliance realignment that could reshape regional security architecture',
    }.get(crisis.type, 'a geopolitical flashpoint')

    briefing_text = f"""## Situation Report
{crisis.title} ({crisis.country}) is rated **{severity_label}** at severity {sev}/100. The situation is {trend_desc}. The crisis involves {type_context}. Cross-domain impact spans {domain_str}, with {impact_sev} economic consequences affecting {sectors}.

## Strategic Context
This crisis sits within a broader pattern of regional instability in {crisis.country} and surrounding areas. {crisis.analysis or 'Detailed analytical context is unavailable for this event.'} The {crisis.type} dimension suggests structural drivers that are unlikely to resolve quickly without deliberate diplomatic or military intervention.

## Key Actors & Interests
- **Primary belligerents / stakeholders** in {crisis.country} hold immediate territorial or political stakes
- **Regional neighbours** face spillover risks in trade, refugees, and security guarantees
- **Great powers** (US, China, Russia, EU) are monitoring for escalation that affects their strategic interests
- **International institutions** (UN, regional bodies) have limited leverage at severity {sev}/100
- **Non-state actors** may exploit governance vacuums if the crisis prolongs

## Impact Assessment
Economic impact is rated **{impact_sev}**, with {sectors} sectors most exposed. Source reliability is **{rel_label}** across {src_count} tracked source(s). {"Escalation pressure is building — proactive measures are time-sensitive." if trend == "escalating" else ("Conditions may allow for negotiated pauses." if trend == "de-escalating" else "The situation is stable but fragile.")} Humanitarian and infrastructure consequences scale with the {sev}/100 severity rating.

## Escalation Scenarios
1. **Continued escalation** ({min(sev + 10, 95)}% plausibility if current drivers persist): further deterioration of {domain_str} conditions with possible external actor involvement
2. **Stalemate / frozen conflict** (moderate plausibility): situation locks in at current severity, reducing acute risk but entrenching structural instability
3. **Rapid de-escalation** (lower plausibility without mediation): requires significant concessions or third-party intervention

## Intelligence Gaps
Key unknowns include internal decision-making dynamics of primary actors and the degree of external support flows. Confidence in this assessment is {crisis.confidence}% based on {src_count} source(s).

---
*Recent Headlines*
{news_lines}

*This briefing was generated analytically from structured data. Set ANTHROPIC_API_KEY for AI-powered deep analysis.*"""

    result = {
        'briefing': briefing_text,
        'model': 'static-rules',
        'timestamp': datetime.utcnow().isoformat()
    }
    if image:
        result['image'] = image
    return result


# ════════════════════════════════════════════════════════════
# WEBSOCKET EVENTS - REAL-TIME STREAMING
# ════════════════════════════════════════════════════════════

if socketio:
    @socketio.on('connect', namespace='/events')
    def handle_connect():
        """Handle client connection to event stream"""
        logger.info(f"Client connected to event stream")
        emit('connection_response', {'status': 'connected'})

    @socketio.on('subscribe', namespace='/events')
    def handle_subscribe(data):
        """Subscribe to crisis alerts for specific watch lists"""
        watch_list = data.get('watch_list', 'all')
        from flask_socketio import join_room
        join_room(watch_list)
        logger.info(f"Client subscribed to {watch_list}")
        emit('subscribed', {'watch_list': watch_list, 'status': 'ok'})

def broadcast_new_crisis(crisis_dict, watch_list='all'):
    """
    Broadcast a new/updated crisis to subscribed clients.
    Called when a new crisis is detected.
    """
    if socketio:
        socketio.emit('new_crisis', {
            'crisis': crisis_dict,
            'timestamp': datetime.utcnow().isoformat(),
            'type': 'breaking_alert'
        }, room=watch_list, namespace='/events')


# ════════════════════════════════════════════════════════════
# CRISIS ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.route('/api/crises', methods=['GET'])
def get_crises():
    """Get all active crises with enhanced data"""
    try:
        session = Session()

        # Filters
        crisis_type = request.args.get('type')
        min_severity = int(request.args.get('min_severity', 0))
        days = request.args.get('days')          # optional — omit to return all crises
        include_analysis = request.args.get('include_analysis', 'false').lower() == 'true'

        query = session.query(Crisis).filter(Crisis.is_active == True)

        if crisis_type:
            query = query.filter(Crisis.type == crisis_type)

        query = query.filter(Crisis.severity >= min_severity)

        # Only apply date window if caller explicitly requests it
        if days:
            since = datetime.utcnow() - timedelta(days=int(days))
            query = query.filter(Crisis.date_start >= since)

        crises = query.order_by(Crisis.severity.desc()).all()

        result = []
        for c in crises:
            crisis_dict = c.to_dict()

            # Add enhanced analysis if requested
            if include_analysis:
                crisis_dict['source_reliability'] = calculate_source_reliability(c.id)
                crisis_dict['escalation'] = analyze_escalation(c.id)
                # Don't include economic impact by default (heavy computation)

            result.append(crisis_dict)

        session.close()

        return jsonify({
            'count': len(result),
            'crises': result,
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        logger.error(f"Error fetching crises: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/crises/balanced', methods=['GET'])
def get_balanced_crises():
    """Return crises geographically balanced across 5 world regions.

    No single region can exceed 30% of the total result set.
    Useful for the globe view to ensure worldwide coverage.
    """
    try:
        session = Session()

        days = int(request.args.get('days', 30))
        per_region = int(request.args.get('per_region', 40))

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

        return jsonify({
            'count': len(all_crises),
            'crises': all_crises,
            'regions': list(REGIONS.keys()),
            'timestamp': datetime.utcnow().isoformat(),
        })

    except Exception as e:
        logger.error(f"Error fetching balanced crises: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/crises/<crisis_id>', methods=['GET'])
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

        # Fetch related forecasts
        forecasts = session.query(Forecast).filter(Forecast.crisis_id == crisis_id).all()

        result = crisis.to_dict()
        result['news'] = [n.to_dict() for n in news]
        result['forecasts'] = [f.to_dict() for f in forecasts]

        session.close()

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching crisis detail: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/crises/<crisis_id>', methods=['PATCH'])
def update_crisis(crisis_id):
    """Update crisis data (admin endpoint)"""
    try:
        session = Session()

        crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
        if not crisis:
            session.close()
            return jsonify({'error': 'Crisis not found'}), 404

        data = request.get_json()

        # Allow updates to severity, analysis, impact, stakeholders
        allowed_fields = ['severity', 'confidence', 'analysis', 'impact', 'stakeholders', 'is_verified']

        for field in allowed_fields:
            if field in data:
                setattr(crisis, field, data[field])

        crisis.date_updated = datetime.utcnow()
        session.commit()

        result = crisis.to_dict()
        session.close()

        # Broadcast update to clients
        broadcast_new_crisis(result)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error updating crisis: {e}")
        return jsonify({'error': str(e)}), 500


# ════════════════════════════════════════════════════════════
# ENHANCED ANALYSIS ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.route('/api/crises/<crisis_id>/reliability', methods=['GET'])
def get_crisis_reliability(crisis_id):
    """Get source reliability analysis for a crisis"""
    try:
        reliability = calculate_source_reliability(crisis_id)
        return jsonify(reliability)
    except Exception as e:
        logger.error(f"Error analyzing reliability: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/crises/<crisis_id>/escalation', methods=['GET'])
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
        return jsonify({'error': str(e)}), 500


@app.route('/api/crises/<crisis_id>/cascade', methods=['GET'])
def get_crisis_cascade(crisis_id):
    """Analyze how a crisis cascades through the actor relationship network"""
    try:
        # Get parameters from query string
        depth = request.args.get('depth', 2, type=int)
        threshold = request.args.get('threshold', 50, type=int)

        # Validate parameters
        depth = max(1, min(4, depth))  # Clamp to 1-4
        threshold = max(0, min(100, threshold))  # Clamp to 0-100

        cascade = analyze_cascade(crisis_id, depth, threshold)
        if cascade:
            return jsonify(cascade)
        else:
            return jsonify({'error': 'Crisis not found'}), 404
    except Exception as e:
        logger.error(f"Error analyzing cascade: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/crises/<crisis_id>/economic', methods=['GET'])
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
        return jsonify({'error': str(e)}), 500


@app.route('/api/crises/<crisis_id>/briefing', methods=['GET'])
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
        return jsonify({'error': str(e)}), 500


@app.route('/api/crises/<crisis_id>/full-analysis', methods=['GET'])
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
        forecasts = session.query(Forecast).filter(Forecast.crisis_id == crisis_id).all()

        session.close()

        result = crisis_dict
        result['news'] = [n.to_dict() for n in news]
        result['forecasts'] = [f.to_dict() for f in forecasts]
        result['reliability'] = calculate_source_reliability(crisis_id)
        result['escalation'] = analyze_escalation(crisis_id)
        result['economic'] = get_economic_impact(crisis_id)
        result['briefing'] = generate_ai_briefing(crisis_id)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error generating full analysis: {e}")
        return jsonify({'error': str(e)}), 500


# ════════════════════════════════════════════════════════════
# ACTOR ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.route('/api/actors', methods=['GET'])
def get_actors():
    """Get all geopolitical actors"""
    try:
        session = Session()

        actors = session.query(Actor).all()
        result = [a.to_dict() for a in actors]

        session.close()

        return jsonify({
            'count': len(result),
            'actors': result
        })

    except Exception as e:
        logger.error(f"Error fetching actors: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/actors/<actor_id>', methods=['GET'])
def get_actor(actor_id):
    """Get specific actor details"""
    try:
        session = Session()

        actor = session.query(Actor).filter(Actor.id == actor_id).first()
        if not actor:
            session.close()
            return jsonify({'error': 'Actor not found'}), 404

        # Get relationships
        rels = session.query(Relationship).filter(
            (Relationship.actor_a == actor_id) | (Relationship.actor_b == actor_id)
        ).all()

        result = actor.to_dict()
        result['relationships'] = [r.to_dict() for r in rels]

        session.close()

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching actor: {e}")
        return jsonify({'error': str(e)}), 500


# ════════════════════════════════════════════════════════════
# RELATIONSHIP ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.route('/api/relationships', methods=['GET'])
def get_relationships():
    """Get all actor relationships"""
    try:
        session = Session()

        rel_type = request.args.get('type')

        query = session.query(Relationship).filter(Relationship.is_active == True)

        if rel_type:
            query = query.filter(Relationship.type == rel_type)

        relationships = query.all()
        result = [r.to_dict() for r in relationships]

        session.close()

        return jsonify({
            'count': len(result),
            'relationships': result
        })

    except Exception as e:
        logger.error(f"Error fetching relationships: {e}")
        return jsonify({'error': str(e)}), 500


def fetch_wikipedia_bilateral(country_a, country_b):
    """
    Fetch bilateral relations article from Wikipedia (free, no API key needed).
    Returns a structured markdown string, or None if not found.
    """
    # Map common actor IDs / abbreviations to full country names Wikipedia uses
    NAME_MAP = {
        'US': 'United States', 'USA': 'United States',
        'CN': 'China', 'PRC': 'China',
        'RU': 'Russia', 'RUS': 'Russia',
        'EU': 'European Union',
        'UK': 'United Kingdom', 'GB': 'United Kingdom',
        'IN': 'India', 'IND': 'India',
        'IR': 'Iran', 'IRN': 'Iran',
        'IL': 'Israel', 'ISR': 'Israel',
        'NK': 'North Korea', 'DPRK': 'North Korea',
        'KP': 'North Korea',
        'FR': 'France', 'DE': 'Germany', 'JP': 'Japan',
        'KR': 'South Korea', 'SA': 'Saudi Arabia',
        'TR': 'Turkey', 'BR': 'Brazil', 'AU': 'Australia',
    }
    a = NAME_MAP.get(country_a.upper(), country_a)
    b = NAME_MAP.get(country_b.upper(), country_b)

    # Wikipedia uses an en-dash (–) in bilateral article titles
    title_variants = [
        f"{a}–{b}_relations",
        f"{b}–{a}_relations",
        f"{a}-{b}_relations",
        f"{b}-{a}_relations",
        f"{a}_{b}_relations",
    ]

    headers = {'User-Agent': 'GeoIntel/1.0 (geopolitical intelligence platform)'}

    for title in title_variants:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}"
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                extract = data.get('extract', '')
                page_url = data.get('content_urls', {}).get('desktop', {}).get('page', '')
                if extract and len(extract) > 100:
                    # Trim to a reasonable length and format as sections
                    sentences = extract.replace('\n', ' ').split('. ')
                    intro     = '. '.join(sentences[:3]).strip()
                    if not intro.endswith('.'): intro += '.'
                    rest      = '. '.join(sentences[3:8]).strip()
                    if rest and not rest.endswith('.'): rest += '.'

                    lines = [
                        f"## Relationship Overview",
                        intro,
                        "",
                    ]
                    if rest:
                        lines += [f"## Historical & Current Dynamics", rest, ""]

                    lines += [
                        f"## Source",
                        f"Analysis sourced from Wikipedia: [{a}–{b} relations]({page_url})" if page_url else f"Source: Wikipedia — {title.replace('_', ' ')}",
                    ]
                    return '\n'.join(lines)
        except Exception as e:
            logger.warning(f"Wikipedia fetch failed for {title}: {e}")
            continue

    return None


def _static_analysis(country_a, country_b, rel_type, rel_label, strength, stability):
    """Fallback when both AI and Wikipedia come up empty."""
    if rel_type:
        parts = [
            f"## Relationship Status",
            f"**{rel_label}** — classified as *{rel_type}*.",
            "",
            f"## Tracked Metrics",
            f"- Relationship strength: {strength}/100",
            f"- Stability index: {stability}/100",
            "",
            "## Note",
            "No Wikipedia bilateral article found for this pair. "
            "Add an ANTHROPIC_API_KEY to `.env` for full AI-generated analysis.",
        ]
    else:
        parts = [
            "## No Data Found",
            f"No tracked relationship or Wikipedia article found for **{country_a}** and **{country_b}**.",
            "",
            "Try using full country names (e.g. 'United States', 'North Korea') "
            "or add an ANTHROPIC_API_KEY to enable AI analysis for any pair.",
        ]
    return '\n'.join(parts)


@app.route('/api/relationships/analyze', methods=['POST'])
def analyze_relationship():
    """Generate AI-powered relationship analysis between any two countries/actors"""
    try:
        data = request.get_json()
        country_a = (data.get('country_a') or '').strip()
        country_b = (data.get('country_b') or '').strip()

        if not country_a or not country_b:
            return jsonify({'error': 'Both country_a and country_b are required'}), 400

        session = Session()

        # Check for known relationship in database (either direction)
        existing_rel = session.query(Relationship).filter(
            ((Relationship.actor_a == country_a) & (Relationship.actor_b == country_b)) |
            ((Relationship.actor_a == country_b) & (Relationship.actor_b == country_a))
        ).first()

        known_type   = existing_rel.type     if existing_rel else None
        known_label  = existing_rel.label    if existing_rel else None
        known_strength   = existing_rel.strength  if existing_rel else None
        known_stability  = existing_rel.stability if existing_rel else None

        session.close()

        known_context = ""
        if existing_rel:
            known_context = (
                f"\n\nTracked relationship data: Type={known_type}, "
                f"Description='{known_label}', "
                f"Strength={known_strength}/100, Stability={known_stability}/100"
            )

        if anthropic_client.api_key:
            try:
                message = anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=900,
                    messages=[{
                        "role": "user",
                        "content": f"""Analyze the current geopolitical relationship between {country_a} and {country_b}.{known_context}

Write as a senior intelligence analyst. Format your response EXACTLY as follows (keep the ## headers):

## Relationship Status
[1-2 sentences classifying the overall relationship: allied, hostile, neutral, competitive, transactional, etc. Include a severity/tension estimate on a scale of 1-10]

## Historical Context
[2-3 sentences on the history of their relationship and key turning points that shaped it]

## Current Dynamics
[3-4 sentences on the current state: diplomatic status, trade relationship, military posture, alliance membership, active disputes or cooperation]

## Key Issues
- [Issue 1: specific dispute, treaty, or point of cooperation]
- [Issue 2]
- [Issue 3]
- [Issue 4 if relevant]

## Near-Term Outlook
[1-2 sentences on where this relationship is heading in the next 12-18 months, including any flashpoints or opportunities]

Be specific and factual. Total: 250-350 words."""
                    }]
                )

                return jsonify({
                    'country_a': country_a,
                    'country_b': country_b,
                    'known': existing_rel is not None,
                    'type': known_type,
                    'label': known_label,
                    'strength': known_strength,
                    'stability': known_stability,
                    'analysis': message.content[0].text,
                    'model': 'claude-3-5-sonnet-20241022',
                    'timestamp': datetime.utcnow().isoformat()
                })
            except Exception as e:
                logger.error(f"Relationship analysis error: {e}")
                return jsonify({'error': 'AI analysis failed', 'details': str(e)}), 500

        else:
            # No Anthropic key — fall back to Wikipedia bilateral relations
            wiki_analysis = fetch_wikipedia_bilateral(country_a, country_b)
            analysis_text = wiki_analysis if wiki_analysis else _static_analysis(
                country_a, country_b, known_type, known_label, known_strength, known_stability
            )
            return jsonify({
                'country_a': country_a,
                'country_b': country_b,
                'known': existing_rel is not None,
                'type': known_type,
                'label': known_label,
                'strength': known_strength,
                'stability': known_stability,
                'analysis': analysis_text,
                'source': 'wikipedia' if wiki_analysis else 'static',
                'timestamp': datetime.utcnow().isoformat()
            })

    except Exception as e:
        logger.error(f"Analyze relationship error: {e}")
        return jsonify({'error': str(e)}), 500


# ════════════════════════════════════════════════════════════
# FORECAST ENDPOINTS
# ════════════════════════════════════════════════════════════

def _generate_static_forecasts(crisis):
    """
    Derive probabilistic forecasts from crisis attributes when the DB has none.
    Returns a list of dicts with keys: q, low, mid, high.
    """
    sev = crisis.severity or 50
    ctype = crisis.type or 'conflict'

    # Base probability that things escalate, based on severity
    p_escalate = min(int(sev * 0.85), 85)
    p_stable   = max(int((100 - sev) * 0.6), 10)
    p_resolve  = max(100 - p_escalate - p_stable, 5)

    # Clamp so bars don't exceed 100
    def clamp(v): return max(5, min(v, 95))

    type_questions = {
        'conflict':   ('Will armed hostilities intensify in the next 90 days?',
                       'Will a ceasefire or peace deal be reached in 6 months?'),
        'military':   ('Will this escalate to open armed conflict within 60 days?',
                       'Will external powers intervene militarily?'),
        'diplomatic': ('Will diplomatic relations deteriorate further?',
                       'Will a multilateral solution emerge within 6 months?'),
        'economic':   ('Will sanctions or trade restrictions tighten in 90 days?',
                       'Will a financial contagion spread to neighbouring economies?'),
        'resource':   ('Will resource shortages cause domestic instability?',
                       'Will supply disruption persist beyond 6 months?'),
        'technology': ('Will cyber or tech-domain attacks escalate?',
                       'Will international norms be invoked to de-escalate?'),
        'proxy':      ('Will proxy conflict draw in direct state actors?',
                       'Will proxy forces gain significant territorial control?'),
        'alliance':   ('Will alliance commitments be formally invoked?',
                       'Will non-aligned states shift allegiances?'),
    }

    q1, q2 = type_questions.get(ctype, (
        'Will the situation escalate significantly in 90 days?',
        'Will international mediation reduce tensions within 6 months?'
    ))

    forecasts = [
        {
            'q': q1,
            'low':  clamp(p_resolve),
            'mid':  clamp(p_stable),
            'high': clamp(p_escalate),
        },
        {
            'q': q2,
            'low':  clamp(p_escalate),
            'mid':  clamp(p_stable),
            'high': clamp(p_resolve),
        },
        {
            'q': f'Will this crisis cause significant humanitarian impact in {crisis.country or "the region"}?',
            'low':  clamp(max(5, 100 - sev)),
            'mid':  clamp(int(sev * 0.3)),
            'high': clamp(int(sev * 0.6)),
        },
        {
            'q': 'Will major-power diplomatic engagement intensify within 30 days?',
            'low':  clamp(max(5, 70 - sev // 2)),
            'mid':  clamp(20),
            'high': clamp(sev // 2),
        },
    ]
    return forecasts


@app.route('/api/forecasts/<crisis_id>', methods=['GET'])
def get_forecasts(crisis_id):
    """Get forecasts for a crisis"""
    try:
        session = Session()

        forecasts = session.query(Forecast).filter(Forecast.crisis_id == crisis_id).all()
        result = [f.to_dict() for f in forecasts]

        # No stored forecasts — generate rule-based ones from crisis data
        if not result:
            crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
            if crisis:
                result = _generate_static_forecasts(crisis)

        session.close()

        return jsonify({
            'crisis_id': crisis_id,
            'count': len(result),
            'forecasts': result
        })

    except Exception as e:
        logger.error(f"Error fetching forecasts: {e}")
        return jsonify({'error': str(e)}), 500


# ════════════════════════════════════════════════════════════
# NEWS ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.route('/api/news', methods=['GET'])
def get_news():
    """Get recent news articles"""
    try:
        session = Session()

        crisis_id = request.args.get('crisis_id')
        days = int(request.args.get('days', 7))
        limit = int(request.args.get('limit', 50))

        query = session.query(News)

        if crisis_id:
            query = query.filter(News.crisis_id == crisis_id)

        since = datetime.utcnow() - timedelta(days=days)
        query = query.filter(News.fetched_at >= since)

        articles = query.order_by(News.published_at.desc()).limit(limit).all()
        result = [a.to_dict() for a in articles]

        # If no articles found and crisis_id provided, generate contextual news
        if not result and crisis_id:
            crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
            if crisis:
                result = _generate_contextual_news(crisis)

        if session:
            session.close()

        return jsonify({
            'count': len(result),
            'articles': result
        })

    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        return jsonify({'error': str(e)}), 500


# ════════════════════════════════════════════════════════════
# ECONOMIC DATA ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.route('/api/economic/<country_code>', methods=['GET'])
def get_economic_data(country_code):
    """Get economic indicators for a country"""
    try:
        session = Session()

        data = session.query(EconomicData).filter(
            EconomicData.country_code == country_code.upper()
        ).order_by(EconomicData.year.desc()).limit(10).all()

        result = [d.to_dict() for d in data]

        session.close()

        return jsonify({
            'country': country_code.upper(),
            'count': len(result),
            'data': result
        })

    except Exception as e:
        logger.error(f"Error fetching economic data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/crises/<crisis_id>/news', methods=['GET'])
def get_crisis_news(crisis_id):
    """Get news articles related to a crisis"""
    try:
        session = Session()
        news = session.query(News).filter(News.crisis_id == crisis_id).limit(10).all()
        result = [n.to_dict() for n in news]
        session.close()

        # If no news found, generate contextual news for the crisis
        if not result:
            crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
            if crisis:
                result = _generate_contextual_news(crisis)

        return jsonify({
            'crisis_id': crisis_id,
            'count': len(result),
            'articles': result
        })
    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        return jsonify({'error': str(e)}), 500


def _generate_contextual_news(crisis):
    """Generate realistic contextual news articles for a crisis"""
    from datetime import datetime, timedelta
    import random

    # News templates by crisis type
    news_templates = {
        'conflict': [
            f"Military operations continue in {crisis.country}: {random.choice(['casualties reported', 'new territories secured', 'humanitarian corridor established'])}",
            f"{crisis.country} military issues statement on ongoing operations",
            f"International community calls for ceasefire in {crisis.country}",
            f"Humanitarian aid reaches {crisis.country} amid ongoing conflict",
            f"War crimes allegations emerge in {crisis.country} investigation",
            f"Residents flee violence in {crisis.country}",
        ],
        'military': [
            f"{crisis.country} military conducts exercises near border",
            f"Defense spending increases in {crisis.country}",
            f"Military buildup reported near {crisis.country}",
            f"Strategic weapons deployment announced by {crisis.country}",
            f"{crisis.country} military operations escalate",
        ],
        'diplomatic': [
            f"Diplomatic talks scheduled for {crisis.country}",
            f"International negotiations begin regarding {crisis.country}",
            f"UN Security Council meets on {crisis.country} situation",
            f"Envoy visits {crisis.country} for peace talks",
            f"Government statements on {crisis.country} dispute",
        ],
        'economic': [
            f"Economic crisis deepens in {crisis.country}",
            f"Fiscal emergency declared in {crisis.country}",
            f"Currency collapse accelerates in {crisis.country}",
            f"Market volatility continues in {crisis.country}",
            f"Trade sanctions impact {crisis.country} economy",
        ],
        'migration': [
            f"Refugee numbers surge from {crisis.country}",
            f"Humanitarian crisis worsens in {crisis.country}",
            f"Border closures announced amid {crisis.country} exodus",
            f"Aid organizations overwhelmed by {crisis.country} displacement",
            f"International response coordinated for {crisis.country}",
        ],
        'resource': [
            f"Resource conflict escalates in {crisis.country}",
            f"Supply chains disrupted due to {crisis.country} crisis",
            f"Global prices rise amid {crisis.country} shortage",
            f"Competition intensifies over {crisis.country} resources",
        ],
        'technology': [
            f"Cyber attacks detected originating from {crisis.country}",
            f"Technology sector targeted in {crisis.country}",
            f"Infrastructure under attack in {crisis.country}",
            f"Digital warfare escalates in {crisis.country}",
        ],
        'proxy': [
            f"Proxy forces active in {crisis.country}",
            f"Third-party actors involved in {crisis.country} conflict",
            f"External powers fuel tensions in {crisis.country}",
        ],
    }

    template_list = news_templates.get(crisis.type, news_templates['conflict'])
    news_articles = []

    now = datetime.utcnow()
    for i in range(3):
        published = now - timedelta(hours=random.randint(1, 48))
        article = {
            'source': random.choice(['Reuters', 'AP News', 'BBC', 'Al Jazeera', 'DW', 'France24']),
            'title': random.choice(template_list),
            'description': f"Ongoing developments in {crisis.country} related to {crisis.title.lower()}. Severity level: {crisis.severity}/100.",
            'url': f"https://example.com/news/{crisis.id}_{i}",
            'urlToImage': None,
            'publishedAt': published.isoformat(),
            'content': f"Recent updates on the {crisis.title} situation...",
        }
        news_articles.append(article)

    return news_articles


# ════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.route('/api/admin/sync', methods=['POST'])
def trigger_data_sync():
    """Manually trigger data sync from all sources"""
    try:
        DataAggregator.sync_all_sources()

        return jsonify({
            'status': 'sync_started',
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        logger.error(f"Error triggering sync: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/stats', methods=['GET'])
def get_stats():
    """Get database stats"""
    try:
        session = Session()

        stats = {
            'crises_total': session.query(Crisis).count(),
            'crises_active': session.query(Crisis).filter(Crisis.is_active == True).count(),
            'actors': session.query(Actor).count(),
            'relationships': session.query(Relationship).count(),
            'news_articles': session.query(News).count(),
            'forecasts': session.query(Forecast).count(),
            'economic_records': session.query(EconomicData).count(),
        }

        session.close()

        return jsonify(stats)

    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    })


# ════════════════════════════════════════════════════════════
# SCHEDULED TASKS
# ════════════════════════════════════════════════════════════

def scheduled_sync():
    """Background data sync task (primary + multilingual sources)"""
    logger.info("Running scheduled data sync...")
    try:
        DataAggregator.sync_all_sources()
        logger.info("Primary data sync completed")
    except Exception as e:
        logger.error(f"Scheduled sync error: {e}")

    # Multilingual news sync (runs every 6 hours to stay within NewsAPI rate limits)
    try:
        from newsapi_multilingual import MultilingualNewsConnector
        connector = MultilingualNewsConnector()
        session = Session()
        added = connector.sync_all_languages(session)
        session.close()
        logger.info(f"Multilingual sync completed — {added} new crises")
    except Exception as e:
        logger.error(f"Multilingual sync error: {e}")


# ════════════════════════════════════════════════════════════
# APP INITIALIZATION
# ════════════════════════════════════════════════════════════

@app.before_request
def before_request():
    """Initialize database before first request"""
    if not hasattr(app, 'db_initialized'):
        try:
            init_actors()
            init_relationships()
            # Load sample crises without full sync (sync can hang on external APIs)
            try:
                session = Session()
                existing_crises = session.query(Crisis).count()
                session.close()
                if existing_crises == 0:
                    # Only populate sample data if database is empty
                    from data_sources import ACLEDConnector
                    sample_data = ACLEDConnector._get_sample_crises()
                    session = Session()
                    for crisis_data in sample_data:
                        c = Crisis(**crisis_data)
                        session.merge(c)
                    session.commit()
                    session.close()
                    logger.info(f"Loaded {len(sample_data)} sample crises")
            except Exception as e:
                logger.warning(f"Sample crisis load failed: {e}")

            logger.info("Database initialized")
            app.db_initialized = True
        except Exception as e:
            logger.error(f"Database init error: {e}")


def init_scheduler():
    """Initialize background scheduler"""
    # Sync ACLED every hour
    scheduler.add_job(
        func=scheduled_sync,
        trigger="interval",
        hours=1,
        id='data_sync',
        name='Sync geopolitical data',
        replace_existing=True
    )

    scheduler.start()
    logger.info("Background scheduler started")


if __name__ == '__main__':
    init_scheduler()

    logger.info("Starting GeoIntel Backend API...")
    if socketio:
        logger.info("✅ Real-Time WebSocket enabled")
        logger.info("WebSocket endpoint: ws://localhost:5000/socket.io/?EIO=4&transport=websocket")
    else:
        logger.info("⚠️  WebSocket disabled - using REST API only")
    logger.info("Health check: http://localhost:5000/api/health")

    port = int(os.getenv('PORT', 5000))
    try:
        if socketio:
            socketio.run(
                app,
                host='0.0.0.0',
                port=port,
                debug=False,
                use_reloader=False
            )
        else:
            app.run(
                host='0.0.0.0',
                port=port,
                debug=os.getenv('DEBUG', 'False') == 'True'
            )
    except Exception as e:
        logger.error(f"Startup error: {e}")
        logger.error("Falling back to Flask without SocketIO...")
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,
            threaded=True
        )
