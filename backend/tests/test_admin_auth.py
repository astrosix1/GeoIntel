"""
Tests for `_check_admin_key()` in app.py — the gate in front of every
/api/admin/* route, the CSV export, and PATCH /api/crises/<id>.

Covers both supported credential methods (legacy X-Admin-Key header,
Supabase-issued JWT bearer token) and the failure modes that matter for
an auth check: wrong key, expired token, bad signature, unlisted email.
"""
import time

import jwt


def _make_token(secret, email, expires_in=3600, algorithm='HS256'):
    payload = {'email': email, 'exp': int(time.time()) + expires_in}
    return jwt.encode(payload, secret, algorithm=algorithm)


class TestLegacyAdminKey:
    def test_missing_key_is_rejected(self, app_module, monkeypatch):
        monkeypatch.setenv('ADMIN_KEY', 'super-secret-key')
        with app_module.app.test_request_context('/api/admin/stats'):
            assert app_module._check_admin_key() is False

    def test_correct_key_is_accepted(self, app_module, monkeypatch):
        monkeypatch.setenv('ADMIN_KEY', 'super-secret-key')
        with app_module.app.test_request_context(
            '/api/admin/stats', headers={'X-Admin-Key': 'super-secret-key'}
        ):
            assert app_module._check_admin_key() is True

    def test_wrong_key_is_rejected(self, app_module, monkeypatch):
        monkeypatch.setenv('ADMIN_KEY', 'super-secret-key')
        with app_module.app.test_request_context(
            '/api/admin/stats', headers={'X-Admin-Key': 'guessed-wrong'}
        ):
            assert app_module._check_admin_key() is False

    def test_no_admin_key_configured_rejects_everything(self, app_module, monkeypatch):
        # If ADMIN_KEY isn't set in the environment, the legacy path must
        # never accept an empty-string "match".
        monkeypatch.setenv('ADMIN_KEY', '')
        with app_module.app.test_request_context(
            '/api/admin/stats', headers={'X-Admin-Key': ''}
        ):
            assert app_module._check_admin_key() is False


class TestJwtAdminAuth:
    def test_valid_token_for_admin_email_is_accepted(self, app_module, monkeypatch):
        monkeypatch.setenv('ADMIN_KEY', '')
        monkeypatch.setenv('SUPABASE_JWT_SECRET', 'jwt-signing-secret')
        monkeypatch.setenv('ADMIN_EMAILS', 'admin@example.com')
        token = _make_token('jwt-signing-secret', 'admin@example.com')
        with app_module.app.test_request_context(
            '/api/admin/stats', headers={'Authorization': f'Bearer {token}'}
        ):
            assert app_module._check_admin_key() is True

    def test_valid_token_for_non_admin_email_is_rejected(self, app_module, monkeypatch):
        monkeypatch.setenv('ADMIN_KEY', '')
        monkeypatch.setenv('SUPABASE_JWT_SECRET', 'jwt-signing-secret')
        monkeypatch.setenv('ADMIN_EMAILS', 'admin@example.com')
        token = _make_token('jwt-signing-secret', 'someone-else@example.com')
        with app_module.app.test_request_context(
            '/api/admin/stats', headers={'Authorization': f'Bearer {token}'}
        ):
            assert app_module._check_admin_key() is False

    def test_expired_token_is_rejected(self, app_module, monkeypatch):
        monkeypatch.setenv('ADMIN_KEY', '')
        monkeypatch.setenv('SUPABASE_JWT_SECRET', 'jwt-signing-secret')
        monkeypatch.setenv('ADMIN_EMAILS', 'admin@example.com')
        token = _make_token('jwt-signing-secret', 'admin@example.com', expires_in=-10)
        with app_module.app.test_request_context(
            '/api/admin/stats', headers={'Authorization': f'Bearer {token}'}
        ):
            assert app_module._check_admin_key() is False

    def test_wrong_signature_is_rejected(self, app_module, monkeypatch):
        monkeypatch.setenv('ADMIN_KEY', '')
        monkeypatch.setenv('SUPABASE_JWT_SECRET', 'jwt-signing-secret')
        monkeypatch.setenv('ADMIN_EMAILS', 'admin@example.com')
        # Signed with a different secret than the server expects.
        token = _make_token('attacker-controlled-secret', 'admin@example.com')
        with app_module.app.test_request_context(
            '/api/admin/stats', headers={'Authorization': f'Bearer {token}'}
        ):
            assert app_module._check_admin_key() is False

    def test_no_jwt_secret_configured_disables_jwt_auth(self, app_module, monkeypatch):
        monkeypatch.setenv('ADMIN_KEY', '')
        monkeypatch.setenv('SUPABASE_JWT_SECRET', '')
        token = _make_token('whatever-secret', 'admin@example.com')
        with app_module.app.test_request_context(
            '/api/admin/stats', headers={'Authorization': f'Bearer {token}'}
        ):
            assert app_module._check_admin_key() is False
