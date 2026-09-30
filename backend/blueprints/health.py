"""Health check and admin data-sync endpoints. Admin sync is relocated
here (rather than a separate admin blueprint) since the new app has no
ops/admin UI in scope."""
import logging
from datetime import datetime

from flask import Blueprint, jsonify

from data_sources import DataAggregator
from cache import cache_clear_prefix, cache_stats
from extensions import limiter
from services.auth import check_admin_key

logger = logging.getLogger(__name__)

health_bp = Blueprint('health', __name__, url_prefix='/api')


@health_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0',
        'cache': cache_stats()
    })


@health_bp.route('/admin/sync', methods=['POST'])
@limiter.limit("10 per minute")
def trigger_data_sync():
    """Manually trigger data sync from all sources"""
    if not check_admin_key():
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        DataAggregator.sync_all_sources()

        # Invalidate all crisis and actor caches so fresh data is served immediately
        cache_clear_prefix('crises:')
        cache_clear_prefix('actors:')
        logger.info("Cache invalidated after admin sync")

        return jsonify({
            'status': 'sync_started',
            'cache_cleared': True,
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        logger.error(f"Error triggering sync: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500
