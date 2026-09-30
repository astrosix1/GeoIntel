"""
WebSocket events — real-time streaming of crisis updates.

Registers the socket.io event handlers (connect/subscribe) against the
shared `socketio` instance from extensions.py, and exposes
`broadcast_new_crisis`, which the crises blueprint calls after any
crisis create/update so subscribed clients get pushed the change.
"""
import logging
from datetime import datetime

from extensions import socketio

logger = logging.getLogger(__name__)


def register_socketio_handlers():
    """Attach the connect/subscribe handlers. Called once from app.py's
    create_app(), after extensions.socketio.init_app(app) has run — a no-op
    if SocketIO isn't installed."""
    if not socketio:
        return

    from flask_socketio import emit, join_room

    @socketio.on('connect', namespace='/events')
    def handle_connect():
        """Handle client connection to event stream"""
        logger.info("Client connected to event stream")
        emit('connection_response', {'status': 'connected'})

    @socketio.on('subscribe', namespace='/events')
    def handle_subscribe(data):
        """Subscribe to crisis alerts for specific watch lists"""
        watch_list = data.get('watch_list', 'all')
        join_room(watch_list)
        logger.info(f"Client subscribed to {watch_list}")
        emit('subscribed', {'watch_list': watch_list, 'status': 'ok'})


def broadcast_new_crisis(crisis_dict, watch_list='all'):
    """
    Broadcast a new/updated crisis to subscribed clients.
    Called when a new crisis is detected or updated.
    """
    if socketio:
        socketio.emit('new_crisis', {
            'crisis': crisis_dict,
            'timestamp': datetime.utcnow().isoformat(),
            'type': 'breaking_alert'
        }, room=watch_list, namespace='/events')
