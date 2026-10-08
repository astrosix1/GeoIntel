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
from services.hazard_detail import get_hazard_detail
from services.hazard_links import events_for_hazard
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


@weather_bp.route('/storms/<event_type>/<event_id>', methods=['GET'])
@limiter.limit("30 per minute")
def get_storm_detail(event_type, event_id):
    """Track, footprint and people exposed for one active hazard (GDACS data).
    Parts GDACS does not publish for this event come back as null."""
    if event_type not in ('TC', 'FL', 'WF', 'DR') or not event_id.isdigit():
        return jsonify({'error': 'Unknown hazard'}), 400
    try:
        result = get_hazard_detail(event_type, event_id)
    except Exception as e:
        logger.error(f"Error fetching hazard detail: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500
    if result == 'not_found':
        return jsonify({'error': 'Hazard not found or no longer active'}), 404
    if result == 'unavailable':
        return jsonify({'error': 'hazard_detail_unavailable'}), 503
    return jsonify(result)


@weather_bp.route('/storms/<event_type>/<event_id>/events', methods=['GET'])
@limiter.limit("30 per minute")
def get_hazard_events(event_type, event_id):
    """Physical events whose pin is inside or near this hazard while it was active.
    "Near" and "during" only: no claim that either caused the other."""
    if event_type not in ('TC', 'FL', 'WF', 'DR') or not event_id.isdigit():
        return jsonify({'error': 'Unknown hazard'}), 400
    try:
        result = events_for_hazard(event_type, event_id)
    except Exception as e:
        logger.error(f"Error linking events to hazard: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500
    if result == 'not_found':
        return jsonify({'error': 'Hazard not found or no longer active'}), 404
    if result == 'unavailable':
        return jsonify({'error': 'hazards_unavailable'}), 503
    return jsonify(result)


@weather_bp.route('/layers', methods=['GET'])
@limiter.limit("60 per minute")
def get_layer_times():
    """The forecast map layers (DWD ICON) and the times each can draw, read from the service's capabilities and remembered for
    30 minutes. 503 when DWD cannot be reached, so the app offers no layer it cannot draw."""
    from data_sources import dwd
    try:
        result = dwd.layers()
        if result is None:
            return jsonify({'error': 'layers_unavailable'}), 503
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error reading forecast layers: {e}")
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500
