"""Tests for JWT user identity, the @optional_user / @require_premium
decorators, and GET /api/me."""
import time
import uuid
from unittest.mock import MagicMock, patch

import jwt
import pytest
from flask import Flask, g, jsonify

from cache import cache_delete
from services import auth, entitlements
from services.gating import optional_user, require_premium

SECRET = 'jwt-signing-secret'


def _token(user_id, secret=SECRET, expires_in=3600, with_sub=True, **extra):
    payload = {'email': 'user@example.com', 'aud': 'authenticated', 'exp': int(time.time()) + expires_in, **extra}
    if with_sub:
        payload['sub'] = user_id
    return jwt.encode(payload, secret, algorithm='HS256')


@pytest.fixture()
def user_id(monkeypatch):
    monkeypatch.setenv('SUPABASE_JWT_SECRET', SECRET)
    uid = str(uuid.uuid4())
    cache_delete(f'plan:{uid}')
    yield uid
    cache_delete(f'plan:{uid}')


@pytest.fixture()
def gated_client():
    """A throwaway Flask app — the decorators only need flask's g/request."""
    app = Flask(__name__)

    @app.route('/open')
    @optional_user
    def open_route():
        return jsonify({'user': g.user, 'plan': g.plan})

    @app.route('/premium')
    @require_premium
    def premium_route():
        return jsonify({'ok': True, 'plan': g.plan})

    with app.test_client() as c:
        yield c


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _plan(plan_status):
    return patch.object(entitlements, '_fetch_subscription',
                        return_value={'status': plan_status} if plan_status else None)


class TestGetCurrentUser:
    def test_valid_token_yields_id_and_email(self, gated_client, user_id):
        with _plan(None):
            body = gated_client.get('/open', headers=_auth(_token(user_id))).get_json()
        assert body['user'] == {'id': user_id, 'email': 'user@example.com'}

    def test_real_supabase_token_with_audience_claim_is_accepted(self, gated_client, user_id):
        # Regression guard: PyJWT rejects a token carrying `aud` when no
        # audience is passed to decode().
        with _plan(None):
            assert gated_client.get('/open', headers=_auth(_token(user_id))).get_json()['user'] is not None

    def test_expired_token_is_anonymous(self, gated_client, user_id):
        body = gated_client.get('/open', headers=_auth(_token(user_id, expires_in=-10))).get_json()
        assert body['user'] is None

    def test_wrong_signature_is_anonymous(self, gated_client, user_id):
        body = gated_client.get('/open', headers=_auth(_token(user_id, secret='some-other-secret-key-xxxxxxxx'))).get_json()
        assert body['user'] is None

    def test_garbage_token_is_anonymous(self, gated_client, user_id):
        assert gated_client.get('/open', headers=_auth('not.a.jwt')).get_json()['user'] is None

    def test_token_without_sub_is_not_a_user(self, gated_client, user_id):
        # The project's anon/service-role keys are valid JWTs with no `sub`.
        body = gated_client.get('/open', headers=_auth(_token(user_id, with_sub=False))).get_json()
        assert body['user'] is None

    def test_no_header_is_anonymous(self, gated_client, user_id):
        body = gated_client.get('/open').get_json()
        assert body == {'user': None, 'plan': 'free'}

    def test_hs256_without_secret_configured_is_anonymous(self, gated_client, user_id, monkeypatch):
        monkeypatch.setenv('SUPABASE_JWT_SECRET', '')
        assert gated_client.get('/open', headers=_auth(_token(user_id))).get_json()['user'] is None


class TestAsymmetricJwt:
    def test_es256_token_verified_via_jwks(self, gated_client):
        from cryptography.hazmat.primitives.asymmetric import ec
        private_key = ec.generate_private_key(ec.SECP256R1())
        uid = str(uuid.uuid4())
        cache_delete(f'plan:{uid}')
        token = jwt.encode({'sub': uid, 'email': 'a@b.co', 'aud': 'authenticated',
                            'exp': int(time.time()) + 600}, private_key, algorithm='ES256')
        client = MagicMock()
        client.get_signing_key_from_jwt.return_value = MagicMock(key=private_key.public_key())
        with patch.object(auth, '_get_jwks_client', return_value=client), _plan('active'):
            body = gated_client.get('/open', headers=_auth(token)).get_json()
        assert body['user']['id'] == uid
        assert body['plan'] == 'premium'
        cache_delete(f'plan:{uid}')

    def test_es256_token_signed_by_a_different_key_is_rejected(self, gated_client):
        from cryptography.hazmat.primitives.asymmetric import ec
        attacker, real = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
        token = jwt.encode({'sub': str(uuid.uuid4()), 'exp': int(time.time()) + 600}, attacker, algorithm='ES256')
        client = MagicMock()
        client.get_signing_key_from_jwt.return_value = MagicMock(key=real.public_key())
        with patch.object(auth, '_get_jwks_client', return_value=client):
            assert gated_client.get('/open', headers=_auth(token)).get_json()['user'] is None

    def test_es256_without_supabase_url_is_anonymous(self, gated_client):
        from cryptography.hazmat.primitives.asymmetric import ec
        key = ec.generate_private_key(ec.SECP256R1())
        token = jwt.encode({'sub': str(uuid.uuid4()), 'exp': int(time.time()) + 600}, key, algorithm='ES256')
        with patch.object(auth, '_get_jwks_client', return_value=None):
            assert gated_client.get('/open', headers=_auth(token)).get_json()['user'] is None

    def test_alg_none_token_is_rejected(self, gated_client, user_id):
        token = jwt.encode({'sub': user_id, 'exp': int(time.time()) + 600}, None, algorithm='none')
        assert gated_client.get('/open', headers=_auth(token)).get_json()['user'] is None


class TestRequirePremium:
    def test_anonymous_gets_401_sign_in_required(self, gated_client, user_id):
        res = gated_client.get('/premium')
        assert res.status_code == 401
        assert res.get_json() == {'error': 'sign_in_required'}

    def test_free_user_gets_403_premium_required(self, gated_client, user_id):
        with _plan(None):
            res = gated_client.get('/premium', headers=_auth(_token(user_id)))
        assert res.status_code == 403
        assert res.get_json() == {'error': 'premium_required'}

    def test_premium_user_gets_200(self, gated_client, user_id):
        with _plan('active'):
            res = gated_client.get('/premium', headers=_auth(_token(user_id)))
        assert res.status_code == 200
        assert res.get_json() == {'ok': True, 'plan': 'premium'}

    def test_lookup_failure_denies_premium(self, gated_client, user_id):
        with patch.object(entitlements, '_fetch_subscription', side_effect=RuntimeError('down')):
            res = gated_client.get('/premium', headers=_auth(_token(user_id)))
        assert res.status_code == 403


class TestMeEndpoint:
    def test_anonymous(self, client, user_id):
        res = client.get('/api/me')
        assert res.status_code == 200
        assert res.get_json() == {'signedIn': False, 'userId': None, 'plan': 'free', 'premium': False}
        assert res.headers['Cache-Control'] == 'no-store'

    def test_signed_in_free(self, client, user_id):
        with _plan(None):
            body = client.get('/api/me', headers=_auth(_token(user_id))).get_json()
        assert body == {'signedIn': True, 'userId': user_id, 'plan': 'free', 'premium': False}

    def test_signed_in_premium(self, client, user_id):
        with _plan('active'):
            body = client.get('/api/me', headers=_auth(_token(user_id))).get_json()
        assert body == {'signedIn': True, 'userId': user_id, 'plan': 'premium', 'premium': True}


class TestAdminIsPremium:
    def test_admin_email_is_premium_without_a_subscription(self, gated_client, user_id, monkeypatch):
        monkeypatch.setenv('ADMIN_EMAILS', 'boss@example.com, other@example.com')
        token = _token(user_id, email='Boss@Example.com')
        with _plan(None) as fetch:
            assert gated_client.get('/premium', headers=_auth(token)).status_code == 200
            assert gated_client.get('/open', headers=_auth(token)).get_json()['plan'] == 'premium'
        fetch.assert_not_called()

    def test_non_admin_without_subscription_stays_free(self, gated_client, user_id, monkeypatch):
        monkeypatch.setenv('ADMIN_EMAILS', 'boss@example.com')
        with _plan(None):
            assert gated_client.get('/premium', headers=_auth(_token(user_id))).status_code == 403

    def test_forged_token_claiming_admin_email_is_not_admin(self, gated_client, user_id, monkeypatch):
        monkeypatch.setenv('ADMIN_EMAILS', 'boss@example.com')
        forged = _token(user_id, secret='wrong-secret-wrong-secret-wrong!!', email='boss@example.com')
        assert gated_client.get('/premium', headers=_auth(forged)).status_code == 401
