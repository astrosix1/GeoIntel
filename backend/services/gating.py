"""Route decorators for the freemium model. Premium is enforced here, on the
server — hiding a button in the frontend is not a paywall."""
import os
from functools import wraps

from flask import g, jsonify

from services.auth import get_current_user, is_admin_email
from services.entitlements import get_plan


def premium_for_all():
    """Testing switch: PREMIUM_FOR_ALL=true gives every signed-in user premium.
    Off unless the env var is set; anonymous callers are still asked to sign in
    (saved events, comments and the like are tied to an account). Unset it to
    restore the paywall."""
    return os.getenv('PREMIUM_FOR_ALL', '').strip().lower() in ('1', 'true', 'yes', 'on')


def plan_for(user):
    """Admins (ADMIN_EMAILS) always get premium; with PREMIUM_FOR_ALL on, so does
    everyone signed in; otherwise the subscription is looked up."""
    if is_admin_email(user.get('email')) or premium_for_all():
        return 'premium'
    return get_plan(user['id'])


def optional_user(f):
    """Anonymous callers allowed. Sets g.user (or None) and g.plan."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        g.user = get_current_user()
        g.plan = plan_for(g.user) if g.user else 'free'
        return f(*args, **kwargs)
    return wrapper


def require_user(f):
    """401 sign_in_required for anonymous callers; any signed-in user passes
    (no premium check). For actions a lapsed-premium user must keep, such as
    deleting their own comment."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'sign_in_required'}), 401
        g.user = user
        return f(*args, **kwargs)
    return wrapper


def require_premium_feature(f):
    """Like require_premium, for features that need no account of their own
    (scenarios, pin refinement). With PREMIUM_FOR_ALL on, anonymous callers pass
    too (g.user is None); otherwise it behaves exactly like require_premium."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if premium_for_all():
            user = get_current_user()
            g.user = user
            g.plan = 'premium'
            return f(*args, **kwargs)
        return require_premium(f)(*args, **kwargs)
    return wrapper


def require_premium(f):
    """401 sign_in_required for anonymous, 403 premium_required for a
    signed-in free user — distinct codes so the UI can show the right prompt."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'sign_in_required'}), 401
        plan = plan_for(user)
        if plan != 'premium':
            return jsonify({'error': 'premium_required'}), 403
        g.user = user
        g.plan = plan
        return f(*args, **kwargs)
    return wrapper
