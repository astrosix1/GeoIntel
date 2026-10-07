"""Premium saved drawings: list, create, read, update and delete. All require a premium user (401 sign-in / 403 upgrade from
@require_premium) and are scoped to the verified user id, so a user can never read or write another user's drawings."""
import logging

from flask import Blueprint, g, jsonify, request

from extensions import limiter
from services.drawings import (
    DrawingLimitReached, InvalidDrawing, MAX_BYTES, MAX_DRAWINGS, UserDataUnavailable,
    create_drawing, delete_drawing, get_drawing, list_drawings, update_drawing,
)
from services.gating import require_premium

logger = logging.getLogger(__name__)

drawings_bp = Blueprint('drawings', __name__, url_prefix='/api/me/drawings')


def _unavailable(e):
    return jsonify({'error': 'user_data_unavailable', 'reason': e.reason}), 503


def _invalid(e):
    return jsonify({'error': 'invalid_drawing', 'reason': e.reason}), 400


def _too_large():
    return jsonify({'error': 'drawing_too_large', 'limit_bytes': MAX_BYTES}), 413


def _body():
    """The JSON body as a dict, or None. A body bigger than the drawing limit (plus room for the name) is refused before it
    is read into memory."""
    return request.get_json(silent=True)


@drawings_bp.before_request
def _size_guard():
    if request.method in ('POST', 'PUT') and (request.content_length or 0) > MAX_BYTES + 4096:
        return _too_large()
    return None


@drawings_bp.route('', methods=['GET'])
@limiter.limit("60 per minute")
@require_premium
def get_drawings():
    try:
        return jsonify({'drawings': list_drawings(g.user['id']), 'limit': MAX_DRAWINGS})
    except UserDataUnavailable as e:
        return _unavailable(e)


@drawings_bp.route('', methods=['POST'])
@limiter.limit("30 per minute")
@require_premium
def post_drawing():
    body = _body()
    if not isinstance(body, dict) or 'name' not in body or 'data' not in body:
        return jsonify({'error': 'invalid_drawing', 'reason': 'body'}), 400
    try:
        drawing = create_drawing(g.user['id'], body['name'], body['data'])
    except InvalidDrawing as e:
        return (_too_large() if e.reason == 'too_large' else _invalid(e))
    except DrawingLimitReached:
        return jsonify({'error': 'drawing_limit_reached', 'limit': MAX_DRAWINGS}), 409
    except UserDataUnavailable as e:
        return _unavailable(e)
    return jsonify({'drawing': drawing}), 201


@drawings_bp.route('/<drawing_id>', methods=['GET'])
@limiter.limit("60 per minute")
@require_premium
def get_one_drawing(drawing_id):
    try:
        drawing = get_drawing(g.user['id'], drawing_id)
    except UserDataUnavailable as e:
        return _unavailable(e)
    if drawing is None:
        return jsonify({'error': 'Drawing not found'}), 404
    return jsonify({'drawing': drawing})


@drawings_bp.route('/<drawing_id>', methods=['PUT'])
@limiter.limit("60 per minute")
@require_premium
def put_drawing(drawing_id):
    body = _body()
    if not isinstance(body, dict) or ('name' not in body and 'data' not in body):
        return jsonify({'error': 'invalid_drawing', 'reason': 'body'}), 400
    try:
        drawing = update_drawing(g.user['id'], drawing_id, body.get('name'), body.get('data'))
    except InvalidDrawing as e:
        return (_too_large() if e.reason == 'too_large' else _invalid(e))
    except UserDataUnavailable as e:
        return _unavailable(e)
    if drawing is None:
        return jsonify({'error': 'Drawing not found'}), 404
    return jsonify({'drawing': drawing})


@drawings_bp.route('/<drawing_id>', methods=['DELETE'])
@limiter.limit("60 per minute")
@require_premium
def remove_drawing(drawing_id):
    try:
        delete_drawing(g.user['id'], drawing_id)
    except UserDataUnavailable as e:
        return _unavailable(e)
    return '', 204
