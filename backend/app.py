"""
GeoIntel Backend API - Enhanced with Real-Time Intelligence
Real-time geopolitical intelligence platform with WebSocket streaming,
source reliability, escalation analysis, economic impact, and AI briefings.

This module is just the Flask app factory: app creation, config,
extensions (rate limiter, CORS, SocketIO, scheduler), blueprint
registration, and the two static-serving routes, which now serve the
built Vite frontend (frontend/dist, produced by `npm run build` in
frontend/) instead of the old hand-rolled index.html/app.js/app.css.

Route logic itself lives in blueprints/ (crises, economic, health) and
services/ (reliability, escalation, economic, briefing, history, auth,
realtime) — see that plan's Step 1 for the reasoning behind the split.
"""
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import logging
import os
from dotenv import load_dotenv

from models import Session, Crisis
from data_sources import DataAggregator, init_actors, init_relationships, init_scheduled_events
from extensions import limiter, socketio, scheduler
from cache import cache_clear_prefix
from services.auth import check_admin_key
from services.retention import archive_old_crises
from services.realtime import register_socketio_handlers, broadcast_new_crisis
from blueprints.crises import crises_bp
from blueprints.economic import economic_bp
from blueprints.health import health_bp
from blueprints.countries import countries_bp
from blueprints.weather import weather_bp
from blueprints.me import me_bp

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Backward-compatible alias — a couple of older test modules reference
# `app._check_admin_key` directly.
_check_admin_key = check_admin_key

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'dist'))

# Restrict CORS to known origins. Set CORS_ORIGINS env var in production
# (comma-separated list of allowed frontend URLs).
_cors_origins_raw = os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://localhost:5000,http://localhost:5173')
_cors_origins = [o.strip() for o in _cors_origins_raw.split(',') if o.strip()]

# Updated for the step-9 cutover to the built Vite frontend. The old
# comment about inline <script>/<style> blocks no longer applies (the new
# frontend ships as hashed, non-inline bundles), but 'unsafe-inline' is
# left in place defensively since nothing currently depends on removing
# it. New additions for the MapLibre globe: `connect-src` needs
# tiles.openfreemap.org (the vector-tile/style/glyph/sprite host the globe
# fetches from client-side), cdn.jsdelivr.net (Globe.tsx's invisible
# country-hit-test layer fetches real Natural Earth country-boundary
# GeoJSON directly from the browser for click detection — confirmed live
# this was missing and silently broke every country click in production,
# since the fetch failed CSP with no console-visible functional symptom
# beyond a blocked-request error), and `worker-src` needs 'self' blob:
# (MapLibre GL JS runs its tile-parsing worker from a blob: URL, which
# otherwise falls back to script-src and gets blocked with no blob:
# source).
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.socket.io; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https://en.wikipedia.org https://*.supabase.co https://tiles.openfreemap.org https://cdn.jsdelivr.net; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'"
)


def _init_rate_limiter_storage():
    """Uses Redis if REDIS_URL is set AND reachable, otherwise falls back
    to in-memory storage."""
    redis_url = os.getenv('REDIS_URL', '')
    if not redis_url:
        logger.info("No REDIS_URL set — rate limiter using in-memory storage.")
        return "memory://"
    try:
        import redis as _redis_test
        _r = _redis_test.from_url(redis_url)
        _r.ping()
        logger.info(f"Rate limiter using Redis: {redis_url}")
        return redis_url
    except Exception as e:
        logger.warning(f"Redis unreachable for rate limiter ({e}). Using in-memory storage.")
        return "memory://"


def create_app():
    app = Flask(__name__)
    CORS(app, origins=_cors_origins)
    app.config['JSON_SORT_KEYS'] = False

    app.config['RATELIMIT_STORAGE_URI'] = _init_rate_limiter_storage()
    limiter.init_app(app)

    if socketio:
        # SECURITY FIX: Match WebSocket CORS to REST CORS (not wildcard)
        socketio.init_app(app, cors_allowed_origins=_cors_origins)
        register_socketio_handlers()
        logger.info("SocketIO loaded successfully")
    else:
        logger.info("SocketIO not available. Running in REST-only mode.")

    # ════════════════════════════════════════════════════════════
    # GLOBAL ERROR HANDLING
    # ════════════════════════════════════════════════════════════

    @app.errorhandler(400)
    def bad_request(error):
        logger.warning(f"Bad request: {error}")
        return jsonify({'error': 'Invalid request parameters', 'details': str(error)}), 400

    @app.errorhandler(401)
    def unauthorized(error):
        logger.warning("Unauthorized access attempt")
        return jsonify({'error': 'Unauthorized — API key required'}), 401

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Resource not found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {error}")
        return jsonify({'error': 'Internal server error — please try again later'}), 500

    @app.route('/')
    def serve_frontend():
        return send_from_directory(FRONTEND_DIR, 'index.html')

    @app.route('/<path:filename>')
    def serve_static(filename):
        # Serve a built asset if it exists (JS/CSS bundles, favicon, the
        # bundled timezone GeoJSON, etc.); otherwise fall back to
        # index.html so client-side routes (if any are added later) don't
        # 404 on a hard refresh.
        full_path = os.path.join(FRONTEND_DIR, filename)
        if os.path.isfile(full_path):
            return send_from_directory(FRONTEND_DIR, filename)
        return send_from_directory(FRONTEND_DIR, 'index.html')

    # ════════════════════════════════════════════════════════════
    # SECURITY HEADERS
    # ════════════════════════════════════════════════════════════

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = _CSP
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains'
        # Frontend files (served straight off disk by serve_static/index
        # above) otherwise rely on Flask's default conditional
        # ETag/Last-Modified caching, which lets a plain browser reload
        # silently serve a stale app.js/app.css/index.html after an edit.
        # API responses are unaffected (their own in-memory cache_get/
        # cache_set layer already handles that separately).
        if not request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-cache, must-revalidate'
        return response

    # ════════════════════════════════════════════════════════════
    # BLUEPRINTS
    # ════════════════════════════════════════════════════════════
    app.register_blueprint(crises_bp)
    app.register_blueprint(economic_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(countries_bp)
    app.register_blueprint(weather_bp)
    app.register_blueprint(me_bp)

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
                init_scheduled_events()
                # Load sample crises without full sync (sync can hang on external APIs)
                try:
                    session = Session()
                    # Excludes curated scheduled events (elections/summits,
                    # added by init_scheduled_events() just above) from
                    # this count — otherwise, on a brand-new database,
                    # those rows alone would make this non-zero and
                    # permanently skip seeding the sample reactive crises,
                    # leaving the Crises tab empty forever.
                    existing_crises = session.query(Crisis).filter(Crisis.source != 'CURATED').count()
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

    return app


app = create_app()


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
    try:
        if archive_old_crises():
            cache_clear_prefix('crises:')
    except Exception as e:
        logger.error(f"Crisis archive error: {e}")

    # Snapshot current severity for every active crisis, once per sync run —
    # this is the real history analyze_escalation() needs. Its own
    # try/except so a snapshot failure never blocks the primary sync above.
    try:
        session = Session()
        DataAggregator.snapshot_severity_history(session)
        session.commit()
        session.close()
    except Exception as e:
        logger.error(f"Severity snapshot error: {e}")

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
                use_reloader=False,
                allow_unsafe_werkzeug=True  # Required for production on Railway/Render
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
