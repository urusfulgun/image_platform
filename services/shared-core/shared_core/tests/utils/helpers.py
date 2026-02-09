import base64
from collections.abc import Callable
import time
from typing import Any, Literal
from unittest.mock import MagicMock
from fastapi import Request
from joserfc import jwk, jwt
import hashlib

from pydantic import HttpUrl
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


async def get_mock_request_valid_nonce(
    middleware_instance: DPoPMiddleware,
    test_keys: jwk.ECKey,
    mock_redis: MagicMock,
) -> tuple[MagicMock, Callable[[MagicMock], Literal["Success"]], dict[Literal['header', 'payload'], dict]]:
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

    # # 4. Mock Redis behavior (in conftest)

    # 5. Simulate Request
    request = MagicMock(spec=Request)
    request.headers = {"Authorization": f"DPoP {access_token}", "DPoP": proof}
    request.method = "GET"
    request.url = "https://api.example.com/data"
    request.app.state.redis = mock_redis
    request.state = MagicMock()  # To allow request.state.user_sub assignment

    async def call_next(req):
        return "Success"

    return request, call_next, {'header': at_header, 'payload': at_payload}
