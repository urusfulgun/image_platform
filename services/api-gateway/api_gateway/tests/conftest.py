from collections.abc import Callable
from api_gateway.middlewares.dpop import DPoPMiddleware
import fakeredis
import pytest
import time
import base64
import hashlib
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from joserfc import jwt, jwk
from joserfc.jwk import thumbprint

from pydantic import HttpUrl

from utils import compute_ath

# Import your middleware here
# from your_module import DPoPMiddleware

PayloadFactory = Callable[[str, HttpUrl, HttpUrl], tuple[str, str]]


@pytest.fixture
def app():
    app = FastAPI()
    app.add_middleware(DPoPMiddleware)

    @app.get("/protected")
    async def protected_route(request: Request):
        return {"sub": getattr(request.state, "user_sub", None)}

    return app


@pytest.fixture
def keys():
    # 1. Keycloak Key (Server)
    keycloak_key = jwk.generate_key("RSA", 2048, {"alg": "RS256", "use": "sig"})
    # 2. Ephemeral DPoP Key (Client)
    client_key = jwk.generate_key("EC", "P-256", {"alg": "ES256", "use": "sig"})
    return {"keycloak": keycloak_key, "client": client_key}


@pytest.fixture(scope="session")
def server_keys():
    """
    Generates the RSA key representing Keycloak.
    Session scoped because generating RSA keys is expensive.
    """
    return jwk.generate_key("RSA", 2048, {"alg": "RS256", "use": "sig"})


@pytest.fixture
def client_key():
    """Generates a fresh EC key for each test (the client's DPoP key)."""
    return jwk.generate_key("EC", "P-256", {"alg": "ES256", "use": "sig"})


@pytest.fixture
async def mock_redis():
    """Provides a fresh, fake Redis instance for each test."""
    # Create an async fake redis client
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def create_dpop_payloads(
    server_keys: jwk.RSAKey, client_key: jwk.ECKey
) -> PayloadFactory:
    """
    A factory fixture that generates a valid Access Token and
    a corresponding DPoP proof.
    """

    def _generate(
        method="GET",
        url="http://testserver/protected",
        issuer="https://auth.example.com",
    ):
        jkt = thumbprint(client_key, "sha256")

        # 1. Access Token
        at_payload = {
            "iss": issuer,
            "sub": "user_123",
            "exp": int(time.time()) + 300,
            "cnf": {"jkt": jkt},
        }
        access_token = jwt.encode({"alg": "RS256"}, at_payload, server_keys)

        # 2. DPoP Proof
        header = {
            "typ": "dpop+jwt",
            "alg": "ES256",
            "jwk": client_key.as_dict(public_only=True),
        }
        proof_payload = {
            "jti": hashlib.md5(str(time.time()).encode()).hexdigest(),
            "htm": method,
            "htu": url,
            "iat": int(time.time()),
            "ath": compute_ath(access_token),
        }
        dpop_proof = jwt.encode(header, proof_payload, client_key)

        return access_token, dpop_proof

    return _generate


@pytest.fixture
def malicious_key():
    """A secondary key used to simulate an attacker's signature."""
    return jwk.generate_key("EC", "P-256", {"alg": "ES256", "use": "sig"})


@pytest.fixture
def create_invalid_proof(client_key, malicious_key) -> PayloadFactory:
    """
    Generates a DPoP proof that is signed by a key OTHER than the
    one declared in the JWK header.
    """

    def _generate(method="GET", url="http://testserver/protected"):
        header = {
            "typ": "dpop+jwt",
            "alg": "ES256",
            "jwk": client_key.as_dict(public_only=True),  # Declares legitimate key
        }
        payload = {
            "jti": "malicious-jti",
            "htm": method,
            "htu": url,
            "iat": int(time.time()),
        }
        # Signed with the WRONG key
        return jwt.encode(header, payload, malicious_key)

    return _generate


@pytest.fixture
async def client(app, mock_redis, server_keys, monkeypatch):
    """
    The main client fixture. It patches settings, injects
    fakeredis, and provides the AsyncClient.
    """
    # Mock settings before the app starts
    monkeypatch.setattr(
        "api_gateway.config.settings.KEYCLOAK_PUBLIC_KEY",
        server_keys.as_dict(public_only=True),
    )
    monkeypatch.setattr(
        "api_gateway.config.settings.ALLOWED_ISSUER", "https://auth.example.com"
    )

    # Inject fake redis into app state
    app.state.redis = mock_redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac
