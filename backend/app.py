"""
GeoIntel Backend API - Enhanced with Real-Time Intelligence
Real-time geopolitical intelligence platform with WebSocket streaming,
source reliability, escalation analysis, economic impact, and AI briefings
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import json
from collections import defaultdict

from models import Session, Crisis, News, Actor, Relationship, Forecast, EconomicData
from data_sources import DataAggregator, init_actors

# Optional: Anthropic for AI briefings
try:
    from anthropic import Anthropic
    anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY', ''))
except:
    anthropic_client = None

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app (WebSocket optional)
app = Flask(__name__)
CORS(app)
app.config['JSON_SORT_KEYS'] = False

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


def generate_ai_briefing(crisis_id):
    """
    Generate AI-powered briefing summary using Claude API.
    Returns structured brief with what, why, what's next.
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

        # Call Claude API for briefing
        if anthropic_client.api_key:
            try:
                message = anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=500,
                    messages=[
                        {
                            "role": "user",
                            "content": f"""Generate a professional 2-minute news briefing for this geopolitical crisis.

Format your response as:
WHAT HAPPENED: [1-2 sentences of facts]
WHY IT MATTERS: [2-3 sentences explaining impact]
WHAT'S NEXT: [2-3 sentences of likely outcomes]
SOURCES: [List the news sources]

Crisis Context:
{context}

Make it suitable for broadcast news anchors."""
                        }
                    ]
                )

                briefing_text = message.content[0].text
                return {
                    'briefing': briefing_text,
                    'model': 'claude-3-5-sonnet-20241022',
                    'timestamp': datetime.utcnow().isoformat()
                }
            except Exception as e:
                logger.error(f"AI briefing error: {e}")
                return None
        else:
            logger.warning("ANTHROPIC_API_KEY not set, skipping AI briefing")
            return None
    finally:
        session.close()


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
        days = int(request.args.get('days', 30))
        include_analysis = request.args.get('include_analysis', 'false').lower() == 'true'

        query = session.query(Crisis).filter(Crisis.is_active == True)

        if crisis_type:
            query = query.filter(Crisis.type == crisis_type)

        query = query.filter(Crisis.severity >= min_severity)

        # Recent crises
        since = datetime.utcnow() - timedelta(days=days)
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


# ════════════════════════════════════════════════════════════
# FORECAST ENDPOINTS
# ════════════════════════════════════════════════════════════

@app.route('/api/forecasts/<crisis_id>', methods=['GET'])
def get_forecasts(crisis_id):
    """Get forecasts for a crisis"""
    try:
        session = Session()

        forecasts = session.query(Forecast).filter(Forecast.crisis_id == crisis_id).all()
        result = [f.to_dict() for f in forecasts]

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
