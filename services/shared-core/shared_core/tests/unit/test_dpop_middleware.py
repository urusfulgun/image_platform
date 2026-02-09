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
from utils.helpers import create_dpop_proof, get_mock_request_valid_nonce


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
    middleware_instance: DPoPMiddleware, test_keys: jwk.ECKey, mock_redis
):
    """Test the 'Happy Path' where all bindings are valid."""

    request, call_next, token = await get_mock_request_valid_nonce(
        middleware_instance, test_keys, mock_redis
    )
    nonce = 'valid-nonce'
    assert await mock_redis.delete(f"dpop_nonce:{nonce}") == 1

    response = await middleware_instance.dispatch(request, call_next)

    assert response.status_code == 401
    # Check that a NEW nonce was generated and saved to Redis
    new_nonce = response.headers["DPoP-Nonce"]
    assert await mock_redis.exists(f"dpop_nonce:{new_nonce}") is True


# @pytest.mark.asyncio
# async def test_jti_replay_fails(middleware_instance, mock_redis):
#     async def call_next(req):
#         return "Success"
#     # 1. Setup a valid request
#     jti = "unique-jti-456"
#     nonce = "valid-nonce"
#     await mock_redis.set(f"dpop_nonce:{nonce}", "1")

#     proof = create_dpop_proof(..., jti=jti, nonce=nonce)
#     request = MagicMock(spec=Request)
#     request.headers = {"Authorization": f"DPoP {valid_token}", "DPoP": proof}
#     request.app.state.redis = mock_redis

#     # 2. First request should succeed
#     response1 = await middleware_instance.dispatch(request, call_next)

#     # 3. Second request with the SAME JTI should fail
#     # We mock a new nonce because the previous one was deleted
#     new_nonce = "second-nonce"
#     await mock_redis.set(f"dpop_nonce:{new_nonce}", "1")

#     # Re-sign the proof with the same JTI but the new nonce
#     replay_proof = create_dpop_proof(..., jti=jti, nonce=new_nonce)
#     request.headers["DPoP"] = replay_proof

#     # This should now trigger a DPoPReplayError (401)
#     response2 = await middleware_instance.dispatch(request, call_next)

#     assert response2.status_code == 401
#     assert "replay" in response2.body.decode().lower()
