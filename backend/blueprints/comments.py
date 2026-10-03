"""Comments on events, display names, and moderation. Reading comments is
public; posting and reporting need premium; deleting your own comment needs
only a signed-in user; the admin endpoints need the admin key / admin email.
All of it is enforced here on the server."""
import logging

from flask import Blueprint, g, jsonify, request

from extensions import limiter
from services import comments as svc
from services.auth import check_admin_key, get_current_user
from services.gating import require_premium, require_user
from services.supabase_rest import SupabaseUnavailable

logger = logging.getLogger(__name__)

comments_bp = Blueprint('comments', __name__, url_prefix='/api')


def _failed(e):
    """A malformed id in the URL is a plain 404; anything else is Supabase
    being unavailable."""
    if e.reason == 'bad_id':
        return jsonify({'error': 'Comment not found'}), 404
    return jsonify({'error': 'user_data_unavailable', 'reason': e.reason}), 503


@comments_bp.route('/crises/<crisis_id>/comments', methods=['GET'])
@limiter.limit("60 per minute")
def get_comments(crisis_id):
    user = get_current_user()  # optional: lets an author see their own hidden comments
    try:
        return jsonify(svc.list_comments(crisis_id, user['id'] if user else None,
                                         before=request.args.get('before')))
    except SupabaseUnavailable as e:
        return _failed(e)


@comments_bp.route('/crises/<crisis_id>/comments', methods=['POST'])
@limiter.limit("10 per minute")
@require_premium
def post_comment(crisis_id):
    body = request.get_json(silent=True)
    text = body.get('body') if isinstance(body, dict) else None
    try:
        comment = svc.post_comment(g.user['id'], crisis_id, text)
    except svc.InvalidComment as e:
        return jsonify({'error': 'invalid_comment', 'reason': str(e)}), 400
    except svc.ProfileRequired:
        return jsonify({'error': 'profile_required'}), 409
    except svc.TooFast:
        return jsonify({'error': 'slow_down'}), 429
    except SupabaseUnavailable as e:
        return _failed(e)
    if comment is None:
        return jsonify({'error': 'Crisis not found'}), 404
    return jsonify({'comment': comment}), 201


@comments_bp.route('/comments/<comment_id>', methods=['DELETE'])
@limiter.limit("20 per minute")
@require_user
def delete_comment(comment_id):
    try:
        deleted = svc.delete_own_comment(g.user['id'], comment_id)
    except SupabaseUnavailable as e:
        return _failed(e)
    if not deleted:
        return jsonify({'error': 'Comment not found'}), 404
    return '', 204


@comments_bp.route('/comments/<comment_id>/report', methods=['POST'])
@limiter.limit("20 per minute")
@require_premium
def report_comment(comment_id):
    body = request.get_json(silent=True)
    reason = body.get('reason') if isinstance(body, dict) else None
    try:
        result = svc.report_comment(g.user['id'], comment_id, reason)
    except svc.InvalidReport:
        return jsonify({'error': 'invalid_report', 'reasons': list(svc.REPORT_REASONS)}), 400
    except svc.CannotReportOwn:
        return jsonify({'error': 'cannot_report_own'}), 400
    except SupabaseUnavailable as e:
        return _failed(e)
    if result is None:
        return jsonify({'error': 'Comment not found'}), 404
    return jsonify(result)


@comments_bp.route('/me/profile', methods=['GET'])
@limiter.limit("60 per minute")
@require_premium
def get_my_profile():
    try:
        return jsonify({'profile': svc.get_profile(g.user['id'])})
    except SupabaseUnavailable as e:
        return _failed(e)


@comments_bp.route('/me/profile', methods=['PUT'])
@limiter.limit("20 per minute")
@require_premium
def put_my_profile():
    body = request.get_json(silent=True)
    name = body.get('display_name') if isinstance(body, dict) else None
    try:
        return jsonify({'profile': svc.set_profile(g.user['id'], name)})
    except svc.InvalidDisplayName as e:
        return jsonify({'error': 'invalid_display_name', 'message': str(e)}), 400
    except svc.DisplayNameTaken:
        return jsonify({'error': 'display_name_taken'}), 409
    except SupabaseUnavailable as e:
        return _failed(e)


# ---- Admin moderation: protected by the existing admin key / admin email ----

def _admin_denied():
    return None if check_admin_key() else (jsonify({'error': 'Unauthorized'}), 401)


@comments_bp.route('/admin/comments/reported', methods=['GET'])
@limiter.limit("60 per minute")
def admin_reported():
    if (denied := _admin_denied()):
        return denied
    try:
        return jsonify({'comments': svc.list_reported()})
    except SupabaseUnavailable as e:
        return _failed(e)


@comments_bp.route('/admin/comments/<comment_id>/reports', methods=['GET'])
@limiter.limit("60 per minute")
def admin_reports(comment_id):
    if (denied := _admin_denied()):
        return denied
    try:
        return jsonify({'reports': svc.list_reports(comment_id)})
    except SupabaseUnavailable as e:
        return _failed(e)


@comments_bp.route('/admin/comments/<comment_id>/restore', methods=['POST'])
@limiter.limit("60 per minute")
def admin_restore(comment_id):
    if (denied := _admin_denied()):
        return denied
    try:
        found = svc.restore_comment(comment_id)
    except SupabaseUnavailable as e:
        return _failed(e)
    return jsonify({'restored': True}) if found else (jsonify({'error': 'Comment not found'}), 404)


@comments_bp.route('/admin/comments/<comment_id>/remove', methods=['POST'])
@limiter.limit("60 per minute")
def admin_remove(comment_id):
    if (denied := _admin_denied()):
        return denied
    try:
        found = svc.remove_comment(comment_id)
    except SupabaseUnavailable as e:
        return _failed(e)
    return jsonify({'removed': True}) if found else (jsonify({'error': 'Comment not found'}), 404)
