"""Characterization: Authorization/DPoP header checks in validate_dpop.

These run before its try block.
"""

import logging

import pytest
from helpers import BASE_URL, make_access_token, make_proof


@pytest.fixture
def token(realm, dpop_key):
    return make_access_token(realm, dpop_key)


@pytest.fixture
def proof(dpop_key, token):
    return make_proof(dpop_key, "GET", f"{BASE_URL}/echo", token)


@pytest.mark.asyncio
async def test_missing_authorization_is_401(client, keycloak, proof):
    resp = await client.get("/echo", headers={"DPoP": proof})

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Missing Security Headers"}
    assert keycloak.calls == {"public_key": 0, "certs": 0}


@pytest.mark.asyncio
async def test_missing_dpop_proof_is_401(client, keycloak, token):
    resp = await client.get("/echo", headers={"Authorization": f"DPoP {token}"})

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Missing Security Headers"}
    assert keycloak.calls == {"public_key": 0, "certs": 0}


@pytest.mark.asyncio
async def test_no_headers_is_401(client):
    resp = await client.get("/echo")

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Missing Security Headers"}


@pytest.mark.asyncio
async def test_bearer_scheme_is_401(client, keycloak, token, proof):
    resp = await client.get(
        "/echo", headers={"Authorization": f"Bearer {token}", "DPoP": proof}
    )

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Expected DPoP Authorization"}
    assert keycloak.calls == {"public_key": 0, "certs": 0}


@pytest.mark.asyncio
async def test_scheme_check_is_case_sensitive(client, token, proof):
    resp = await client.get(
        "/echo", headers={"Authorization": f"dpop {token}", "DPoP": proof}
    )

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Expected DPoP Authorization"}


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_empty_dpop_header_never_reaches_missing_proof_branch(client, token):
    # CHARACTERIZATION: changes in R12. The later `if not dpop_jwt` branch is
    # unreachable, so the "Missing DPoP Proof" detail is never produced.
    resp = await client.get(
        "/echo", headers={"Authorization": f"DPoP {token}", "DPoP": ""}
    )

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Missing Security Headers"}


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_missing_proof_logs_access_token(client, caplog, token):
    # CHARACTERIZATION: changes in R3. The full Authorization value is logged at
    # WARNING.
    caplog.set_level(logging.WARNING, logger="shared_core.utils.endpoint.rs_dpop")

    await client.get("/echo", headers={"Authorization": f"DPoP {token}"})

    assert token in caplog.text


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_wrong_scheme_logs_access_token(client, caplog, token, proof):
    # CHARACTERIZATION: changes in R3. The full Authorization value is logged at
    # WARNING.
    caplog.set_level(logging.WARNING, logger="shared_core.utils.endpoint.rs_dpop")

    await client.get(
        "/echo", headers={"Authorization": f"Bearer {token}", "DPoP": proof}
    )

    assert token in caplog.text
