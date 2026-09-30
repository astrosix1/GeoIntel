"""
Weather-mode endpoint — real active storm (tropical cyclone) pins for the
globe's Weather mode (step 5 of the rewrite plan). Real data from GDACS
(see data_sources/gdacs.py); no fabricated storms when the feed is
empty or unreachable.
"""
import logging

from flask import Blueprint, jsonify

from services.weather import get_active_storms

logger = logging.getLogger(__name__)

weather_bp = Blueprint('weather', __name__, url_prefix='/api/weather')


@weather_bp.route('/storms', methods=['GET'])
def get_storms():
    """Get real, currently active tropical-cyclone/storm data from GDACS."""
    try:
        result = get_active_storms()
        if result is None:
            return jsonify({'error': 'Live storm data is currently unavailable. Please try again shortly.'}), 503

        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching active storms: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500
