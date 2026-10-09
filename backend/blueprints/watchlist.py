"""Watchlist places, hazard alerts, place search and alert settings.

Listing/adding/searching/alerts need a premium user (401 sign-in / 403
upgrade); deleting a place and marking alerts read need only a signed-in user,
so a lapsed member can still tidy up. Everything is scoped to the verified
user id, and every limit is enforced here on the server.
"""
import logging

from flask import Blueprint, g, jsonify, request

from extensions import limiter
from services import watchlist as svc
from services.forecast import ForecastUnavailable
from services.gating import require_premium, require_user
from services.geocode import InvalidQuery, search_places
from services.place_alert_prefs import InvalidPlaceAlertPrefs
from services.supabase_rest import SupabaseUnavailable
from services.weather import get_active_storms

logger = logging.getLogger(__name__)

watchlist_bp = Blueprint('watchlist', __name__, url_prefix='/api/me')


def _failed(e):
    """A malformed id in the URL is a plain 404; anything else is Supabase
    being unavailable."""
    if e.reason == 'bad_id':
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'error': 'user_data_unavailable', 'reason': e.reason}), 503


@watchlist_bp.route('/watch', methods=['GET'])
@limiter.limit("60 per minute")
@require_premium
def get_watch():
    try:
        places = svc.list_places(g.user['id'])
    except SupabaseUnavailable as e:
        return _failed(e)
    storms = get_active_storms()  # cached; None when the hazard feed is down
    hazards = storms['storms'] if storms else []
    return jsonify({
        'places': [{**p, 'nearby': svc.nearby_hazards(p, hazards)} for p in places],
        'limit': svc.MAX_PLACES,
        'hazards_available': storms is not None,
    })


@watchlist_bp.route('/watch', methods=['POST'])
@limiter.limit("30 per minute")
@require_premium
def post_watch():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'error': 'invalid_place', 'message': 'expected a JSON object'}), 400
    try:
        place = svc.add_place(g.user['id'], body.get('name'), body.get('lat'), body.get('lon'),
                              body.get('radius_km'), body.get('alert_prefs'))
    except (svc.InvalidPlace, InvalidPlaceAlertPrefs) as e:
        return jsonify({'error': 'invalid_place', 'message': str(e)}), 400
    except svc.PlaceExists:
        return jsonify({'error': 'place_exists'}), 409
    except svc.PlaceLimitReached:
        return jsonify({'error': 'place_limit_reached', 'limit': svc.MAX_PLACES}), 409
    except SupabaseUnavailable as e:
        return _failed(e)
    return jsonify({'place': place}), 201


@watchlist_bp.route('/watch/<place_id>/alert-prefs', methods=['PUT'])
@limiter.limit("60 per minute")
@require_premium
def put_place_alert_prefs(place_id):
    """Which alerts a place raises. `apply_to_all: true` saves the same choices for every place the user has."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or 'alert_prefs' not in body:
        return jsonify({'error': 'invalid_place', 'message': 'expected {"alert_prefs": {...}}'}), 400
    try:
        places = svc.update_place_prefs(g.user['id'], place_id, body['alert_prefs'], body.get('apply_to_all') is True)
    except InvalidPlaceAlertPrefs as e:
        return jsonify({'error': 'invalid_place', 'message': str(e)}), 400
    except SupabaseUnavailable as e:
        return _failed(e)
    if not places:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'places': places})


@watchlist_bp.route('/watch/<place_id>', methods=['DELETE'])
@limiter.limit("60 per minute")
@require_user
def delete_watch(place_id):
    try:
        svc.delete_place(g.user['id'], place_id)
    except SupabaseUnavailable as e:
        return _failed(e)
    return '', 204


@watchlist_bp.route('/alerts', methods=['GET'])
@limiter.limit("60 per minute")
@require_premium
def get_alerts():
    try:
        return jsonify({'alerts': svc.list_alerts(g.user['id']), 'unread': svc.unread_count(g.user['id'])})
    except SupabaseUnavailable as e:
        return _failed(e)


@watchlist_bp.route('/alerts/read', methods=['POST'])
@limiter.limit("60 per minute")
@require_user
def post_alerts_read():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'error': 'invalid_request', 'message': 'expected {"ids": [...]} or {"all": true}'}), 400
    try:
        if body.get('all') is True:
            svc.mark_alerts_read(g.user['id'])
        elif isinstance(body.get('ids'), list) and all(isinstance(i, str) for i in body['ids']):
            svc.mark_alerts_read(g.user['id'], body['ids'])
        else:
            return jsonify({'error': 'invalid_request',
                            'message': 'expected {"ids": [...]} or {"all": true}'}), 400
    except SupabaseUnavailable as e:
        return _failed(e)
    return '', 204


@watchlist_bp.route('/alert-settings', methods=['GET'])
@limiter.limit("60 per minute")
@require_premium
def get_alert_settings():
    try:
        return jsonify(svc.get_alert_settings(g.user['id']))
    except SupabaseUnavailable as e:
        return _failed(e)


@watchlist_bp.route('/alert-settings', methods=['PUT'])
@limiter.limit("30 per minute")
@require_premium
def put_alert_settings():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'error': 'invalid_settings', 'message': 'expected a JSON object'}), 400
    try:
        return jsonify(svc.set_alert_settings(
            g.user['id'], body.get('alert_email'), body.get('alert_min_level'), body.get('alert_conditions')))
    except svc.InvalidAlertSettings as e:
        return jsonify({'error': 'invalid_settings', 'message': str(e)}), 400
    except SupabaseUnavailable as e:
        return _failed(e)


@watchlist_bp.route('/geo/search', methods=['GET'])
@limiter.limit("20 per minute")
@require_premium
def get_geo_search():
    try:
        return jsonify({'results': search_places(request.args.get('q', ''))})
    except InvalidQuery as e:
        return jsonify({'error': 'invalid_query', 'message': str(e)}), 400
    except ForecastUnavailable:
        return jsonify({'error': 'search_unavailable'}), 503
