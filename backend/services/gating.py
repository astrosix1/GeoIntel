"""Route decorators for the freemium model. Premium is enforced here, on the
server — hiding a button in the frontend is not a paywall."""
from functools import wraps

from flask import g, jsonify

from services.auth import get_current_user
from services.entitlements import get_plan


def optional_user(f):
    """Anonymous callers allowed. Sets g.user (or None) and g.plan."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        g.user = get_current_user()
        g.plan = get_plan(g.user['id']) if g.user else 'free'
        return f(*args, **kwargs)
    return wrapper


def require_premium(f):
    """401 sign_in_required for anonymous, 403 premium_required for a
    signed-in free user — distinct codes so the UI can show the right prompt."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'sign_in_required'}), 401
        plan = get_plan(user['id'])
        if plan != 'premium':
            return jsonify({'error': 'premium_required'}), 403
        g.user = user
        g.plan = plan
        return f(*args, **kwargs)
    return wrapper
