"""
Shared Flask extension instances (Limiter, SocketIO, the background
scheduler). Created here — with no `app` bound yet — so blueprint and
service modules can import them (e.g. `@limiter.limit(...)`) without
triggering a circular import with app.py, which is the module that
actually calls `.init_app(app)` on each of these during app creation.
"""
import logging
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

# Bound to an app later via limiter.init_app(app) in app.py's create_app().
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per minute"],
)

# Try to load SocketIO, but don't fail if it's not available. `socketio`
# stays None (never a real SocketIO instance) when the import fails, and
# every caller (services/realtime.py, app.py) already checks truthiness
# before using it.
socketio = None
try:
    from flask_socketio import SocketIO
    socketio = SocketIO()
except Exception as e:
    logger.warning(f"SocketIO not available: {e}. Running in REST-only mode.")

# Background scheduler for data sync (started from app.py's create_app()).
scheduler = BackgroundScheduler()
