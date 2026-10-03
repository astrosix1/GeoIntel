"""Premium dashboard endpoints: saved events and outlet preferences. All
require a premium user (401 sign-in / 403 upgrade from @require_premium) and
are scoped to the verified user id — a user can never read or write another
user's data."""
import logging

from flask import Blueprint, g, jsonify, request

from extensions import limiter
from services.gating import require_premium
from services.user_data import (
    InvalidPrefs, MAX_SAVED, SaveLimitReached, UserDataUnavailable,
    get_prefs, list_saved, save_event, set_prefs, unsave_event,
)

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api/me')


def _unavailable(e):
    return jsonify({'error': 'user_data_unavailable', 'reason': e.reason}), 503


@dashboard_bp.route('/saved', methods=['GET'])
@limiter.limit("60 per minute")
@require_premium
def get_saved():
    try:
        return jsonify({'saved': list_saved(g.user['id'])})
    except UserDataUnavailable as e:
        return _unavailable(e)


@dashboard_bp.route('/saved/<crisis_id>', methods=['PUT'])
@limiter.limit("60 per minute")
@require_premium
def put_saved(crisis_id):
    try:
        saved = save_event(g.user['id'], crisis_id)
    except SaveLimitReached:
        return jsonify({'error': 'save_limit_reached', 'limit': MAX_SAVED}), 409
    except UserDataUnavailable as e:
        return _unavailable(e)
    if saved is None:
        return jsonify({'error': 'Crisis not found'}), 404
    return jsonify({'saved': saved})


@dashboard_bp.route('/saved/<crisis_id>', methods=['DELETE'])
@limiter.limit("60 per minute")
@require_premium
def delete_saved(crisis_id):
    try:
        unsave_event(g.user['id'], crisis_id)
    except UserDataUnavailable as e:
        return _unavailable(e)
    return '', 204


@dashboard_bp.route('/prefs', methods=['GET'])
@limiter.limit("60 per minute")
@require_premium
def get_user_prefs():
    try:
        return jsonify(get_prefs(g.user['id']))
    except UserDataUnavailable as e:
        return _unavailable(e)


@dashboard_bp.route('/prefs', methods=['PUT'])
@limiter.limit("60 per minute")
@require_premium
def put_user_prefs():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or 'hidden_outlets' not in body:
        return jsonify({'error': 'invalid_prefs', 'message': 'expected {"hidden_outlets": [...]}'}), 400
    try:
        return jsonify(set_prefs(g.user['id'], body['hidden_outlets']))
    except InvalidPrefs as e:
        return jsonify({'error': 'invalid_prefs', 'message': str(e)}), 400
    except UserDataUnavailable as e:
        return _unavailable(e)
