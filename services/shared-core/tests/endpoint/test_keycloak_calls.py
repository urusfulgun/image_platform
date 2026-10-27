"""Characterization: Keycloak calls and logging in validate_dpop (rs_dpop.py)."""

import logging

import jwt
import pytest

from tests.endpoint.helpers import BASE_URL, dpop_headers, make_access_token, make_proof

URL = f"{BASE_URL}/echo"
LOGGER = "shared_core.utils.endpoint.rs_dpop"


@pytest.fixture
def token(realm, dpop_key):
    return make_access_token(realm, dpop_key)


async def send_valid(client, dpop_key, token):
    proof = make_proof(dpop_key, "GET", URL, token)
    return await client.get("/echo", headers=dpop_headers(token, proof)), proof


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_each_request_calls_keycloak_twice_without_cache(
    client, keycloak, dpop_key, token
):
    # CHARACTERIZATION: changes in R7. Two blocking HTTP calls per request, no JWKS
    # cache.
    # The `public_key()` result is only loaded and logged, never used for validation.
    for n in (1, 2):
        resp, _ = await send_valid(client, dpop_key, token)
        assert resp.status_code == 200
        assert keycloak.calls == {"public_key": n, "certs": n}


@pytest.mark.parametrize("failing", ["public_key", "certs"])
@pytest.mark.asyncio
async def test_keycloak_unreachable_is_401(client, keycloak, dpop_key, token, failing):
    keycloak.raise_on.add(failing)

    resp, _ = await send_valid(client, dpop_key, token)

    assert resp.status_code == 401
    assert resp.json() == {
        "detail": f"DPoP Validation Failed: keycloak {failing} unreachable"
    }


@pytest.mark.asyncio
async def test_public_key_failure_stops_before_certs(client, keycloak, dpop_key, token):
    keycloak.raise_on.add("public_key")

    await send_valid(client, dpop_key, token)

    assert keycloak.calls == {"public_key": 1, "certs": 0}


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_success_logs_realm_key_jwk_and_proof_payload(
    client, caplog, realm, dpop_key, token
):
    # CHARACTERIZATION: changes in R3. Key material and the full proof payload are
    # logged at INFO.
    caplog.set_level(logging.INFO, logger=LOGGER)

    resp, proof = await send_valid(client, dpop_key, token)

    assert resp.status_code == 200
    messages = [r.getMessage() for r in caplog.records if r.name == LOGGER]
    assert any(realm.public_key_b64 in m for m in messages)
    assert any(m.startswith("Ephemeral jwk of DPoP JWT") for m in messages)
    payload = jwt.decode(proof, options={"verify_signature": False})
    assert any(payload["ath"] in m and payload["jti"] in m for m in messages)
