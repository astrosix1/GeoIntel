"""Authentication — admin gate (crises PATCH, health/admin-sync) plus
Supabase user identity for the freemium/premium features."""
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

_jwks_client = None
_jwks_client_url = None


def _get_jwks_client():
    """PyJWKClient for the Supabase project's public signing keys, or None
    when SUPABASE_URL isn't configured. Cached per URL; PyJWKClient keeps its
    own key cache, so this doesn't refetch on every request."""
    global _jwks_client, _jwks_client_url
    base = os.getenv('SUPABASE_URL', '').rstrip('/')
    if not base:
        return None
    url = f'{base}/auth/v1/.well-known/jwks.json'
    if _jwks_client is None or _jwks_client_url != url:
        _jwks_client = jwt.PyJWKClient(url)
        _jwks_client_url = url
    return _jwks_client


def decode_supabase_token(token):
    """Verified claims dict for a Supabase-issued JWT, or None.

    Legacy Supabase projects sign with a shared HS256 secret
    (SUPABASE_JWT_SECRET); newer ones sign with asymmetric keys (ES256/RS256)
    published via JWKS. The signature and expiry are always verified. The
    audience is not checked: real Supabase tokens carry aud='authenticated',
    and PyJWT rejects any token with an aud claim when no audience is passed,
    so omitting it here would lock out every real user token. Callers that
    need an identity must also require a `sub` claim (see get_current_user),
    which the project's anon/service-role keys don't have."""
    if not jwt_available:
        return None
    try:
        alg = jwt.get_unverified_header(token).get('alg')
    except jwt.InvalidTokenError as e:
        logger.warning(f"JWT rejected: {e}")
        return None
    options = {"verify_exp": True, "verify_aud": False}
    try:
        if alg == 'HS256':
            jwt_secret = os.getenv('SUPABASE_JWT_SECRET', '')
            if not jwt_secret:
                logger.warning("SUPABASE_JWT_SECRET not set — HS256 JWT auth disabled")
                return None
            return jwt.decode(token, jwt_secret, algorithms=["HS256"], options=options)
        if alg in ('ES256', 'RS256'):
            client = _get_jwks_client()
            if client is None:
                logger.warning("SUPABASE_URL not set — asymmetric JWT auth disabled")
                return None
            key = client.get_signing_key_from_jwt(token).key
            return jwt.decode(token, key, algorithms=[alg], options=options)
        logger.warning(f"JWT rejected: unsupported alg {alg!r}")
    except jwt.ExpiredSignatureError:
        logger.warning("JWT rejected: token expired")
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as e:
        logger.warning(f"JWT rejected: {e}")
    return None


def get_current_user():
    """{'id', 'email'} for the verified Bearer token on this request, or None
    for anonymous/invalid. Requires a `sub` claim, so the project's
    anon/service-role keys (valid JWTs, but no user) never count as a user."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    claims = decode_supabase_token(auth_header[7:])
    if not claims or not claims.get('sub'):
        return None
    email = claims.get('email') or (claims.get('user_metadata') or {}).get('email')
    return {'id': claims['sub'], 'email': email}


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
            decoded = decode_supabase_token(auth_header[7:])
            if decoded:
                admin_emails = [e.strip() for e in os.getenv('ADMIN_EMAILS', 'collins.nick999@gmail.com').split(',')]
                user_email = decoded.get('email') or (decoded.get('user_metadata') or {}).get('email')
                if user_email and user_email in admin_emails:
                    logger.info(f"Admin access granted via JWT for {user_email}")
                    return True
                logger.warning(f"JWT valid but email not in admin list: {user_email}")
            return False

    return False
