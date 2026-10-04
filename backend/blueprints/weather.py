"""
Weather-mode endpoint — real active storm (tropical cyclone) pins for the
globe's Weather mode (step 5 of the rewrite plan). Real data from GDACS
(see data_sources/gdacs.py); no fabricated storms when the feed is
empty or unreachable.
"""
import logging

from flask import Blueprint, jsonify, request

from extensions import limiter
from services.forecast import ForecastUnavailable, InvalidCoordinates, get_forecast
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


@weather_bp.route('/forecast', methods=['GET'])
@limiter.limit("30 per minute")
def get_point_forecast():
    """Current conditions, next 48 h and 7-day forecast for a point
    (?lat=&lon=). Coordinates are rounded to 0.1 degree and results cached."""
    try:
        result = get_forecast(request.args.get('lat'), request.args.get('lon'))
    except InvalidCoordinates as e:
        return jsonify({'error': str(e)}), 400
    except ForecastUnavailable:
        return jsonify({'error': 'forecast_unavailable'}), 503
    except Exception as e:
        logger.error(f"Error fetching forecast: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500
    return jsonify(result)
