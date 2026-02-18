from unittest.mock import MagicMock
from pydantic import HttpUrl
import pytest
import time
import hashlib
import base64
from joserfc import jwt, jwk
from fastapi import HTTPException, Request
from shared_core.schemas.exceptions import DPoPError
from shared_core.middlewares.dpop import DPoPMiddleware
from utils.helpers import (
    create_dpop_proof,
    get_ec_keys,
    get_mock_request_valid_nonce,
    get_ath,
)
from shared_core.shared_types.http_request import MethodType


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
    middleware_instance: DPoPMiddleware, test_keys: tuple[jwk.ECKey,  jwk.ECKey], mock_redis
):
    """Test the 'Happy Path' where all bindings are valid."""

    request, call_next, token = await get_mock_request_valid_nonce(
        middleware_instance, test_keys, mock_redis
    )

    result = await middleware_instance.dispatch(request, call_next)

    assert result == "Success"
    # Ensure user_sub was correctly extracted
    at_payload = token["payload"]
    assert str(request.state.user_sub) == at_payload["sub"]


@pytest.mark.asyncio
async def test_expired_or_missing_nonce(
    middleware_instance: DPoPMiddleware, test_keys: tuple[jwk.ECKey,  jwk.ECKey], mock_redis
):
    """Test the 'Happy Path' where all bindings are valid."""
    nonce = "valid-nonce"
    request, call_next, token = await get_mock_request_valid_nonce(
        middleware_instance,
        test_keys,
        mock_redis,
    )
    assert await mock_redis.delete(f"dpop_nonce:{nonce}") == 1

    response = await middleware_instance.dispatch(request, call_next)

    assert response.status_code == 401
    # Check that a NEW nonce was generated and saved to Redis
    new_nonce = response.headers["DPoP-Nonce"]
    assert await mock_redis.exists(f"dpop_nonce:{new_nonce}") is True


@pytest.mark.asyncio
async def test_jti_replay_fails(
    middleware_instance: DPoPMiddleware, test_keys: tuple[jwk.ECKey,  jwk.ECKey], mock_redis
):
    nonce = "valid-nonce"
    jti_1 = "unique-jti-123"
    request, call_next, token = await get_mock_request_valid_nonce(
        middleware_instance,
        test_keys,
        mock_redis,
        jti=jti_1,
        nonce=nonce,
    )

    # 2. First request should succeed
    response1 = await middleware_instance.dispatch(request, call_next)

    assert response1 == "Success"

    # 3. Second request with the SAME JTI should fail
    # We mock a new nonce because the previous one was deleted
    new_nonce = "second-nonce"
    request, call_next, token = await get_mock_request_valid_nonce(
        middleware_instance,
        test_keys,
        mock_redis,
        jti=jti_1,
        nonce=nonce,
    )
    await mock_redis.set(f"dpop_nonce:{new_nonce}", "1")

    # Re-sign the proof with the same JTI but the new nonce
    # replay_proof = create_dpop_proof(..., jti=jti, nonce=new_nonce)
    # request.headers["DPoP"] = replay_proof

    # This should now trigger a DPoPReplayError (401)
    # Assert that the middleware raises the specific HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await middleware_instance.dispatch(request, call_next)

    # Verify the details of the exception
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Proof JTI already used"


@pytest.mark.asyncio
async def test_dpop_invalid_htu(
    middleware_instance: DPoPMiddleware, test_keys: tuple[jwk.ECKey,  jwk.ECKey], mock_redis
):
    """Test that proof with a different HTU than the request fails."""
    # Setup
    proof_private_key, proof_public_key = get_ec_keys()
    nonce = "valid-nonce"
    await mock_redis.set(f"dpop_nonce:{nonce}", "1")

    # Proof says /secure but request is /admin
    proof = create_dpop_proof(
        proof_private_key,
        proof_public_key,
        "GET",
        "https://api.com/secure",
        nonce=nonce,
    )

    request = MagicMock(spec=Request)
    request.headers = {"Authorization": "DPoP valid-at", "DPoP": proof}
    request.method = "GET"
    request.url = "https://api.com/admin"  # Mismatch
    request.app.state.redis = mock_redis

    with pytest.raises(HTTPException) as exc:
        await middleware_instance.dispatch(request, None)
    assert exc.value.status_code == 401
    assert "htu binding mismatch" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_dpop_key_mismatch(
    middleware_instance: DPoPMiddleware, test_keys: tuple[jwk.ECKey,  jwk.ECKey], mock_redis
):
    """Test that using a different key than the one bound to the token fails."""
    # Token is bound to Key A
    private_key_a, public_key_a = get_ec_keys()
    jkt_a = jwk.thumbprint(public_key_a, "sha256")

    # Proof is signed by Key B
    private_key_b, public_key_b = get_ec_keys()
    time_of_creation = int(time.time())
    at_payload = {
        "iss": "https://auth.com",
        "sub": "123",
        "cnf": {"jkt": jkt_a},
        "exp": time_of_creation + 100,
        "iat": time_of_creation,
    }
    access_token = jwt.encode({"alg": "ES256"}, at_payload, test_keys)

    nonce = "valid-nonce"
    await mock_redis.set(f"dpop_nonce:{nonce}", "1")
    proof = create_dpop_proof(
        private_key_b,
        public_key_b,
        "GET",
        "https://api.com/data",
        ath=get_ath(access_token),
        nonce=nonce,
    )

    request = MagicMock(spec=Request)
    request.headers = {"Authorization": f"DPoP {access_token}", "DPoP": proof}
    request.method = "GET"
    request.url = "https://api.com/data"
    request.app.state.redis = mock_redis

    with pytest.raises(HTTPException) as exc:
        await middleware_instance.dispatch(request, None)
    assert "Token is not bound to the provided private key" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_dpop_token_expired(
    middleware_instance: DPoPMiddleware, test_keys: tuple[jwk.ECKey,  jwk.ECKey], mock_redis
):
    """Test that an expired Access Token fails even with a valid Proof."""
    time_of_creation = int(time.time())
    at_payload = {
        "iss": "https://auth.com",
        "exp": time_of_creation - 1000,  # Expired
        "iat": time_of_creation - 2000,
        "cnf": {"jkt": "some-jkt"},
    }
    access_token = jwt.encode({"alg": "ES256"}, at_payload, test_keys)

    request = MagicMock(spec=Request)
    request.headers = {"Authorization": f"DPoP {access_token}", "DPoP": "some-proof"}

    with pytest.raises(HTTPException) as exc:
        await middleware_instance.verify_and_parse_access_token(access_token)
    assert exc.value.detail == "Access Token has expired"


@pytest.mark.asyncio
async def test_dpop_invalid_ath(
    middleware_instance: DPoPMiddleware, test_keys: tuple[jwk.ECKey,  jwk.ECKey], mock_redis
):
    """Test that a proof with a mismatched Access Token Hash (ath) fails."""
    proof_key = jwk.generate_key("EC", "P-256")
    jkt = jwk.thumbprint(proof_key, "sha256")

    time_of_creation = int(time.time())

    at_payload = {
        "iss": "https://auth.com",
        "cnf": {"jkt": jkt},
        "exp": time_of_creation + 100,
        "iat": time_of_creation,
    }
    access_token = jwt.encode({"alg": "ES256"}, at_payload, test_keys)

    nonce = "v"
    await mock_redis.set(f"dpop_nonce:{nonce}", "1")

    # ath is set to 'wrong-hash'
    proof = create_dpop_proof(
        proof_key, "GET", "https://api.com/data", ath="wrong-hash", nonce=nonce
    )

    request = MagicMock(spec=Request)
    request.headers = {"Authorization": f"DPoP {access_token}", "DPoP": proof}
    request.method = "GET"
    request.url = "https://api.com/data"
    request.app.state.redis = mock_redis

    with pytest.raises(HTTPException) as exc:
        await middleware_instance.dispatch(request, None)
    assert "ath claim mismatch" in str(exc.value.detail)
