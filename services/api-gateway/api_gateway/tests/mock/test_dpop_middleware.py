from collections.abc import Callable
from pydantic import HttpUrl
import pytest
import time
import base64
import hashlib
from fastapi import FastAPI, Request, Response
from httpx import ASGITransport, AsyncClient
from joserfc import jwt, jwk
from joserfc.jwk import thumbprint
from utils import compute_ath, create_dpop_proof


@pytest.mark.asyncio
async def test_successful_dpop_request(
    client: AsyncClient,
    create_dpop_payloads: Callable[[str, HttpUrl, HttpUrl], tuple[str, str]],
):
    # Arrange
    access_token, dpop_proof = create_dpop_payloads(
        method="GET", url="http://testserver/protected"
    )

    # Act
    response = await client.get(
        "/protected",
        headers={"Authorization": f"DPoP {access_token}", "DPoP": dpop_proof},
    )

    # Assert
    assert response.status_code == 200
    assert response.json()["sub"] == "user_123"


@pytest.mark.asyncio
async def test_replay_attack_fails(
    client: AsyncClient,
    create_dpop_payloads: Callable[[str, HttpUrl, HttpUrl], tuple[str, str]],
):
    # Arrange
    access_token, dpop_proof = create_dpop_payloads()
    headers = {"Authorization": f"DPoP {access_token}", "DPoP": dpop_proof}

    # Act
    first_resp = await client.get("/protected", headers=headers)
    second_resp = await client.get("/protected", headers=headers)

    # Assert
    assert first_resp.status_code == 200
    assert second_resp.status_code == 401
    assert "replayed" in second_resp.json()["detail"]


@pytest.mark.asyncio
async def test_dpop_success(app, keys, monkeypatch):
    # Mock settings to use our test Keycloak public key
    monkeypatch.setattr(
        "api_gateway.config.settings.KEYCLOAK_PUBLIC_KEY",
        keys["keycloak"].as_dict(public_only=True),
    )
    monkeypatch.setattr(
        "api_gateway.config.settings.ALLOWED_ISSUER", "https://auth.example.com"
    )

    # 1. Generate Access Token bound to Client Key
    jkt = thumbprint(keys["client"], "sha256")
    at_payload = {
        "iss": "https://auth.example.com",
        "sub": "user_123",
        "exp": int(time.time()) + 300,
        "cnf": {"jkt": jkt},
    }
    access_token = jwt.encode({"alg": "RS256"}, at_payload, keys["keycloak"])

    # 2. Generate DPoP Proof
    target_url = "http://testserver/protected"
    proof = create_dpop_proof(keys["client"], "GET", target_url)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        response = await ac.get(
            "/protected",
            headers={"Authorization": f"DPoP {access_token}", "DPoP": proof},
        )

    assert response.status_code == 200
    assert response.json() == {"sub": "user_123"}


@pytest.mark.asyncio
async def test_dpop_invalid_htu(app, keys, monkeypatch):
    monkeypatch.setattr(
        "api_gateway.config.settings.KEYCLOAK_PUBLIC_KEY",
        keys["keycloak"].as_dict(public_only=True),
    )

    jkt = thumbprint(keys["client"], "sha256")
    at_payload = {
        "iss": "https://auth.example.com",
        "exp": int(time.time()) + 300,
        "cnf": {"jkt": jkt},
    }
    access_token = jwt.encode({"alg": "RS256"}, at_payload, keys["keycloak"])

    # Proof has WRONG URL
    proof = create_dpop_proof(keys["client"], "GET", "https://wrong-url.com/api")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        response = await ac.get(
            "/protected",
            headers={"Authorization": f"DPoP {access_token}", "DPoP": proof},
        )

    assert response.status_code == 401
    assert "DPoP proof target mismatch" in response.json()["detail"]


@pytest.mark.asyncio
async def test_dpop_key_mismatch(app, keys, monkeypatch):
    monkeypatch.setattr(
        "api_gateway.config.settings.KEYCLOAK_PUBLIC_KEY",
        keys["keycloak"].as_dict(public_only=True),
    )

    # Token is bound to client_key...
    jkt = thumbprint(keys["client"], "sha256")
    at_payload = {
        "iss": "https://auth.example.com",
        "exp": int(time.time()) + 300,
        "cnf": {"jkt": jkt},
    }
    access_token = jwt.encode({"alg": "RS256"}, at_payload, keys["keycloak"])

    # ...but proof is signed by a DIFFERENT malicious key
    malicious_key = jwk.generate_key("EC", "P-256")
    proof = create_dpop_proof(malicious_key, "GET", "http://testserver/protected")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        response = await ac.get(
            "/protected",
            headers={"Authorization": f"DPoP {access_token}", "DPoP": proof},
        )

    assert response.status_code == 401
    assert "DPoP key mismatch" in response.json()["detail"]


# -- test cases for checking the ath (Access Token Hash) claim or handling token expiration specifically


@pytest.mark.asyncio
async def test_dpop_token_expired(app, keys, monkeypatch):
    monkeypatch.setattr(
        "api_gateway.config.settings.KEYCLOAK_PUBLIC_KEY",
        keys["keycloak"].as_dict(public_only=True),
    )

    jkt = thumbprint(keys["client"], "sha256")
    at_payload = {
        "iss": "https://auth.example.com",
        "exp": int(time.time()) - 100,  # Expired 100 seconds ago
        "cnf": {"jkt": jkt},
    }
    access_token = jwt.encode({"alg": "RS256"}, at_payload, keys["keycloak"])
    proof = create_dpop_proof(keys["client"], "GET", "http://testserver/protected")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        response = await ac.get(
            "/protected",
            headers={"Authorization": f"DPoP {access_token}", "DPoP": proof},
        )

    assert response.status_code == 401
    assert "Token expired" in response.json()["detail"]


@pytest.mark.asyncio
async def test_dpop_invalid_ath(app, keys, monkeypatch):
    """
    Note: This test assumes you add 'ath' verification to your middleware.
    It verifies that a proof meant for Token A cannot be used with Token B.
    """
    monkeypatch.setattr(
        "api_gateway.config.settings.KEYCLOAK_PUBLIC_KEY",
        keys["keycloak"].as_dict(public_only=True),
    )

    jkt = thumbprint(keys["client"], "sha256")
    at_payload = {
        "iss": "https://auth.example.com",
        "exp": int(time.time()) + 300,
        "cnf": {"jkt": jkt},
    }

    # Generate two different tokens
    access_token_a = jwt.encode(
        {"alg": "RS256", "kid": "1"}, at_payload, keys["keycloak"]
    )
    access_token_b = jwt.encode(
        {"alg": "RS256", "kid": "2"}, at_payload, keys["keycloak"]
    )

    # Create proof bound to Token A
    ath_a = compute_ath(access_token_a)
    proof_for_a = create_dpop_proof(
        keys["client"], "GET", "http://testserver/protected", ath=ath_a
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        # Attempt to use Token B with Proof meant for Token A
        response = await ac.get(
            "/protected",
            headers={"Authorization": f"DPoP {access_token_b}", "DPoP": proof_for_a},
        )

    # This should fail if your middleware checks verified_proof.claims.get("ath")
    assert response.status_code == 401


# -- jti


@pytest.mark.asyncio
async def test_dpop_jti_replay_with_fake_redis(test_client, keys, monkeypatch):
    # Setup keys and token
    monkeypatch.setattr(
        "api_gateway.config.settings.KEYCLOAK_PUBLIC_KEY",
        keys["keycloak"].as_dict(public_only=True),
    )

    jkt = thumbprint(keys["client"], "sha256")
    at_payload = {
        "iss": "https://auth.example.com",
        "exp": int(time.time()) + 300,
        "cnf": {"jkt": jkt},
    }
    access_token = jwt.encode({"alg": "RS256"}, at_payload, keys["keycloak"])

    # Generate proof
    proof = create_dpop_proof(keys["client"], "GET", "http://testserver/protected")
    headers = {"Authorization": f"DPoP {access_token}", "DPoP": proof}

    # First request: Should pass and store JTI in Fakeredis
    resp1 = await test_client.get("/protected", headers=headers)
    assert resp1.status_code == 200

    # Second request: Middleware checks Fakeredis, finds JTI, and fails
    resp2 = await test_client.get("/protected", headers=headers)
    assert resp2.status_code == 401
    assert "replayed" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_dpop_invalid_signature_fails(client, create_dpop_payloads, create_invalid_proof):
    # Arrange: Get a valid Access Token but a cryptographically invalid Proof
    access_token, _ = create_dpop_payloads()
    invalid_proof = create_invalid_proof()
    
    # Act
    response = await client.get(
        "/protected",
        headers={
            "Authorization": f"DPoP {access_token}",
            "DPoP": invalid_proof
        }
    )
    
    # Assert
    assert response.status_code == 401
    # The error message comes from the catch-all Exception in your middleware
    assert "Auth error" in response.json()["detail"]
