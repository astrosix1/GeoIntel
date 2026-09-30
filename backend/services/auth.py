"""Admin authentication — shared by the crises PATCH endpoint and the
health/admin-sync endpoint."""
import logging
import os
import secrets

from flask import request

logger = logging.getLogger(__name__)

try:
    import jwt
    jwt_available = True
except Exception:
    jwt_available = False


def check_admin_key():
    """Return True if the request carries valid credentials.
    Supports two methods:
    1. X-Admin-Key header (legacy, simple API key)
    2. Authorization: Bearer <JWT> (Supabase/JWT tokens — signature verified)
    """
    # Method 1: Check legacy admin key header
    # SECURITY FIX: constant-time comparison — plain == leaks a timing signal
    # proportional to how many leading bytes of ADMIN_KEY the caller guessed.
    admin_key = os.getenv('ADMIN_KEY', '')
    supplied_key = request.headers.get('X-Admin-Key', '')
    if admin_key and secrets.compare_digest(supplied_key, admin_key):
        logger.info("Admin access granted via API key")
        return True

    # Method 2: Check JWT Bearer token with proper signature verification
    if jwt_available:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            jwt_secret = os.getenv('SUPABASE_JWT_SECRET', '')
            if not jwt_secret:
                logger.warning("SUPABASE_JWT_SECRET not set — JWT auth disabled")
                return False
            try:
                # SECURITY FIX: Verify signature using Supabase JWT secret
                decoded = jwt.decode(
                    token,
                    jwt_secret,
                    algorithms=["HS256"],
                    options={"verify_exp": True}
                )
                admin_emails = [e.strip() for e in os.getenv('ADMIN_EMAILS', 'collins.nick999@gmail.com').split(',')]
                user_email = decoded.get('email') or decoded.get('user_metadata', {}).get('email')
                if user_email and user_email in admin_emails:
                    logger.info(f"Admin access granted via JWT for {user_email}")
                    return True
                logger.warning(f"JWT valid but email not in admin list: {user_email}")
            except jwt.ExpiredSignatureError:
                logger.warning("JWT rejected: token expired")
            except jwt.InvalidTokenError as e:
                logger.warning(f"JWT rejected: {e}")
            return False

    return False
