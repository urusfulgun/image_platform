from unittest.mock import MagicMock
from pydantic import HttpUrl
import pytest
import time
import hashlib
import base64
from joserfc import jwt, jwk
from fastapi import Request
from shared_core.schemas.exceptions import DPoPError
from shared_core.middlewares.dpop import DPoPMiddleware


def create_dpop_proof(proof_key: jwk.ECKey, method, url: HttpUrl, ath=None, nonce=None):
    """Helper to generate a signed DPoP Proof JWT."""
    header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": proof_key.as_dict()}
    payload = {
        "jti": "unique-jti-123",
        "htm": method,
        "htu": str(url).split("?")[0],
        "iat": int(time.time()),
    }
    if ath:
        payload["ath"] = ath
    if nonce:
        payload["nonce"] = nonce

    return jwt.encode(header, payload, proof_key)


@pytest.mark.asyncio
async def test_middleware_nonce_challenge(
    middleware_instance: DPoPMiddleware, mock_redis
):
    """Test that missing DPoP header triggers a 401 Nonce Challenge."""
    request: Request = MagicMock(spec=Request)
    dummy_jwt = "header.payload.signature"
    request.headers = {"Authorization": f"DPoP {dummy_jwt}"}
    request.app.state.redis = mock_redis

    # We call dispatch directly or simulate call_next
    async def call_next(req):
        return None

    response = await middleware_instance.dispatch(request, call_next)

    assert response.status_code == 401
    assert "DPoP-Nonce" in response.headers
    assert b"use_dpop_nonce" in response.body


@pytest.mark.asyncio
async def test_full_dpop_success(
    middleware_instance: DPoPMiddleware, test_keys: jwk.ECKey, mock_redis
):
    """Test the 'Happy Path' where all bindings are valid."""

    # 1. Setup Keys and Bindings
    proof_key: jwk.ECKey = jwk.generate_key("EC", "P-256")
    jkt = jwk.thumbprint(proof_key, "sha256")

    # 2. Create Access Token signed by Auth Server (test_keys)
    at_header = {"alg": "ES256"}
    at_payload = {
        "iss": "https://auth.example.com",
        "sub": "550e8400-e29b-41d4-a716-446655440000",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "cnf": {"jkt": jkt},
    }
    access_token = jwt.encode(at_header, at_payload, test_keys)

    # 3. Create DPoP Proof
    ath = (
        base64.urlsafe_b64encode(hashlib.sha256(access_token.encode()).digest())
        .decode()
        .rstrip("=")
    )
    nonce = "valid-nonce"
    # Prime the mock just like a real Redis
    await mock_redis.set(f"dpop_nonce:{nonce}", "1")
    proof = create_dpop_proof(
        proof_key, "GET", "https://api.example.com/data", ath=ath, nonce=nonce
    )

    # # 4. Mock Redis behavior
    # mock_redis.delete.side_effect = lambda k: 1 if k == f"dpop_nonce:{nonce}" else 0
    # mock_redis.exists.side_effect = lambda k: (
    #     k == f"dpop_nonce:{nonce}"
    # )  # Only nonce exists

    # 5. Simulate Request
    request = MagicMock(spec=Request)
    request.headers = {"Authorization": f"DPoP {access_token}", "DPoP": proof}
    request.method = "GET"
    request.url = "https://api.example.com/data"
    request.app.state.redis = mock_redis
    request.state = MagicMock()  # To allow request.state.user_sub assignment

    async def call_next(req):
        return "Success"

    result = await middleware_instance.dispatch(request, call_next)

    assert result == "Success"
    # Ensure user_sub was correctly extracted
    assert str(request.state.user_sub) == at_payload["sub"]

@pytest.mark.asyncio
async def test_expired_or_missing_nonce(middleware_instance: DPoPMiddleware, test_keys: jwk.ECKey, mock_redis):
    """Test the 'Happy Path' where all bindings are valid."""

    # 1. Setup Keys and Bindings
    proof_key: jwk.ECKey = jwk.generate_key("EC", "P-256")
    jkt = jwk.thumbprint(proof_key, "sha256")

    # 2. Create Access Token signed by Auth Server (test_keys)
    at_header = {"alg": "ES256"}
    at_payload = {
        "iss": "https://auth.example.com",
        "sub": "550e8400-e29b-41d4-a716-446655440000",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "cnf": {"jkt": jkt},
    }
    access_token = jwt.encode(at_header, at_payload, test_keys)

    # 3. Create DPoP Proof
    ath = (
        base64.urlsafe_b64encode(hashlib.sha256(access_token.encode()).digest())
        .decode()
        .rstrip("=")
    )
    nonce = "expired-nonce"
    # Prime the mock just like a real Redis
    # Do NOT set anything in mock_redis
    proof = create_dpop_proof(
        proof_key, "GET", "https://api.example.com/data", ath=ath, nonce=nonce
    )

    # # 4. Mock Redis behavior
    # mock_redis.delete.side_effect = lambda k: 1 if k == f"dpop_nonce:{nonce}" else 0
    # mock_redis.exists.side_effect = lambda k: (
    #     k == f"dpop_nonce:{nonce}"
    # )  # Only nonce exists

    # 5. Simulate Request
    request = MagicMock(spec=Request)
    request.headers = {"Authorization": f"DPoP {access_token}", "DPoP": proof}
    request.method = "GET"
    request.url = "https://api.example.com/data"
    request.app.state.redis = mock_redis
    request.state = MagicMock()  # To allow request.state.user_sub assignment

    async def call_next(req):
        return "Success"
    
    response = await middleware_instance.dispatch(request, call_next)
    
    assert response.status_code == 401
    # Check that a NEW nonce was generated and saved to Redis
    new_nonce = response.headers["DPoP-Nonce"]
    assert await mock_redis.exists(f"dpop_nonce:{new_nonce}") is True
