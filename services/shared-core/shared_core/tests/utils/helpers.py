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
from shared_core.schemas.dpop import (
    DPoPProofHeader,
    DPoPProofPayload,
    DPoPAccessTokenPayload,
)
from shared_core.shared_types.http_request import MethodType


def get_ath(token: str) -> str:
    digest = hashlib.sha256(token.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def get_ec_keys() -> tuple[jwk.ECKey, jwk.ECKey]:
    ec_key = jwk.generate_key("EC", "P-256")
    private_key: jwk.ECKey = jwk.ECKey.import_key(ec_key.private_key)
    public_key: jwk.ECKey = jwk.ECKey.import_key(ec_key.public_key)
    return private_key, public_key


def create_dpop_proof(
    proof_private_key: jwk.ECKey,
    proof_public_key: jwk.ECKey,
    method,
    url: HttpUrl,
    ath=None,
    nonce=None,
    jti="unique-jti-123",
) -> str:
    """Helper to generate a signed DPoP Proof JWT."""
    if proof_public_key.is_private:
        raise ValueError("Expected public key. Got private.")
    if not proof_private_key.is_private:
        raise ValueError("Expected private key. Got public.")
    header = DPoPProofHeader.model_validate(
        {
            "typ": "dpop+jwt",
            "alg": "ES256",
            "jwk": proof_public_key.as_dict(),
        }
    )
    payload = DPoPProofPayload.model_validate(
        {
            "jti": jti,
            "htm": method,
            "htu": str(url).split("?")[0],
            "iat": int(time.time()),
            "ath": ath,
            "nonce": nonce,
        }
    )

    return jwt.encode(
        header.model_dump(exclude_none=True, mode="json"),
        payload.model_dump(exclude_none=True, mode="json"),
        proof_private_key,
    )


class MadeUpRequest:
    jti: str = ("unique-jti-123",)
    nonce: str = ("valid-nonce",)
    htu: HttpUrl = ("https://api.example.com/data",)
    request_url: HttpUrl = ("https://api.example.com/data",)
    request_method: MethodType = ("GET",)
    method_in_proof: MethodType = ("GET",)

    def __init__(
        self,
        jti: str = "unique-jti-123",
        nonce: str = "valid-nonce",
        htu: HttpUrl = "https://api.example.com/data",
        request_url: HttpUrl = "https://api.example.com/data",
        request_method: MethodType = "GET",
        method_in_proof: MethodType = "GET",
    ):
        self.jti = jti
        self.nonce = nonce
        self.htu = (htu,)
        request_url = request_url
        request_method = request_method
        method_in_proof = method_in_proof

    def make_proof_key(self) -> None:
        self.proof_key = jwk.generate_key("EC", "P-256")

    def buid(self):
        raise NotImplementedError


async def get_mock_request_valid_nonce(
    middleware_instance: DPoPMiddleware,
    test_keys: tuple[jwk.ECKey, jwk.ECKey],
    mock_redis: MagicMock,
    jti: str = "unique-jti-123",
    nonce: str = "valid-nonce",
    htu: HttpUrl = "https://api.example.com/data",
    request_url: HttpUrl = "https://api.example.com/data",
    request_method: MethodType = "GET",
    method_in_proof: MethodType = "GET",
    aud: str | list[str] | None = "api-gateway",
) -> tuple[
    MagicMock,
    Callable[[MagicMock], Literal["Success"]],
    dict[Literal["header", "payload"], dict],
]:
    # Access Token's key pair (made by Authorization Server)
    at_private_key, at_public_key = test_keys
    # 1. Setup Keys and Bindings
    proof_private_key, proof_public_key = get_ec_keys()
    jkt = jwk.thumbprint(at_public_key, "sha256")

    # 2. Create Access Token signed by Auth Server (test_keys)
    at_header = {"alg": "ES256"}
    at_payload = DPoPAccessTokenPayload.model_validate(
        {
            "iss": "https://auth.example.com",
            "sub": "user@example.com",
            "cid": "550e8400-e29b-41d4-a716-446655440000",
            "uid": "550e8400-e29b-41d4-a716-446655440000",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "cnf": {"jkt": jkt},
            "auth_time": int(time.time()) - 100,
            "aud": aud,
        }
    )
    access_token = jwt.encode(
        at_header, at_payload.model_dump(exclude_none=True, mode="json"), at_private_key
    )

    # 3. Create DPoP Proof
    ath = (
        base64.urlsafe_b64encode(hashlib.sha256(access_token.encode()).digest())
        .decode()
        .rstrip("=")
    )

    # Prime the mock just like a real Redis
    await mock_redis.set(f"dpop_nonce:{nonce}", "1")
    proof = create_dpop_proof(
        proof_private_key,
        proof_public_key,
        "GET",
        htu,
        ath=ath,
        nonce=nonce,
        jti=jti,
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

    return request, call_next, {"header": at_header, "payload": at_payload}
