"""Who the caller is and what plan they're on — the frontend's single source
for locking/unlocking premium UI."""
from flask import Blueprint, g, jsonify

from extensions import limiter
from services.gating import optional_user, premium_for_all

me_bp = Blueprint('me', __name__, url_prefix='/api')


@me_bp.route('/me', methods=['GET'])
@limiter.limit("60 per minute")
@optional_user
def get_me():
    response = jsonify({
        'signedIn': g.user is not None,
        'userId': g.user['id'] if g.user else None,
        'plan': g.plan,
        'premium': g.plan == 'premium',
        # Testing switch: features that need no account are open to everyone (see services/gating.py).
        'openAccess': premium_for_all(),
    })
    response.headers['Cache-Control'] = 'no-store'
    return response
