"""Characterization: access-token checks in validate_dpop (rs_dpop.py).

python-keycloak's `decode_token` verifies the RS256 signature against `certs()` and checks
`exp`/`nbf` with jwcrypto's 60 s leeway. Nothing else about the token is checked.
"""

import time

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from helpers import (
    BASE_URL,
    SUB,
    dpop_headers,
    make_access_token,
    make_proof,
    new_dpop_key,
    new_realm_key,
    rfc7638_thumbprint,
)

URL = f"{BASE_URL}/echo"
PREFIX = "DPoP Validation Failed: "


async def call(client, key, token, *, method="GET", path="/echo", htu=URL):
    proof = make_proof(key, method, htu, token)
    return await client.request(method, path, headers=dpop_headers(token, proof))


@pytest.mark.asyncio
async def test_valid_token_and_proof_returns_claims(client, realm, dpop_key):
    token = make_access_token(realm, dpop_key)

    resp = await call(client, dpop_key, token)

    assert resp.status_code == 200
    claims = resp.json()
    # CHARACTERIZATION: changes in R1. The claims (incl. `sub`) are returned, but asset-service
    # mounts validate_dpop via `dependencies=[...]`, discards them and trusts X-User-Sub instead.
    assert claims["sub"] == SUB
    assert claims["cnf"] == {"jkt": rfc7638_thumbprint(dpop_key)}


@pytest.mark.asyncio
async def test_post_is_accepted(client, realm, dpop_key):
    token = make_access_token(realm, dpop_key)

    resp = await call(client, dpop_key, token, method="POST")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_path_params_are_part_of_htu(client, realm, dpop_key):
    token = make_access_token(realm, dpop_key)

    resp = await call(
        client, dpop_key, token, path="/items/42", htu=f"{BASE_URL}/items/42"
    )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_request_query_is_ignored_when_htu_has_none(client, realm, dpop_key):
    token = make_access_token(realm, dpop_key)

    resp = await call(client, dpop_key, token, path="/echo?page=2&size=10")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_token_signed_by_unknown_key_is_401(client, realm, dpop_key):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = make_access_token(realm, dpop_key, signing_key=other)

    resp = await call(client, dpop_key, token)

    assert resp.status_code == 401
    assert resp.json()["detail"].startswith(PREFIX)


@pytest.mark.asyncio
async def test_token_from_another_realm_is_401(client, dpop_key):
    token = make_access_token(new_realm_key(), dpop_key)

    resp = await call(client, dpop_key, token)

    assert resp.status_code == 401
    assert resp.json()["detail"].startswith(PREFIX)


@pytest.mark.asyncio
async def test_malformed_token_is_401(client, dpop_key):
    resp = await call(client, dpop_key, "not.a.jwt")

    assert resp.status_code == 401
    assert resp.json()["detail"].startswith(PREFIX)


@pytest.mark.asyncio
async def test_empty_token_is_401(client, dpop_key):
    resp = await call(client, dpop_key, "")

    assert resp.status_code == 401
    assert resp.json()["detail"].startswith(PREFIX)


@pytest.mark.asyncio
async def test_token_expired_beyond_leeway_is_401(client, realm, dpop_key):
    token = make_access_token(realm, dpop_key, exp=int(time.time()) - 90)

    resp = await call(client, dpop_key, token)

    assert resp.status_code == 401
    assert resp.json()["detail"].startswith(PREFIX)


@pytest.mark.asyncio
async def test_token_expired_within_leeway_is_accepted(client, realm, dpop_key):
    token = make_access_token(realm, dpop_key, exp=int(time.time()) - 30)

    resp = await call(client, dpop_key, token)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_token_without_cnf_is_401(client, realm, dpop_key):
    token = make_access_token(realm, None)

    resp = await call(client, dpop_key, token)

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_bound_to_another_key_is_401(client, realm, dpop_key):
    token = make_access_token(realm, new_dpop_key())

    resp = await call(client, dpop_key, token)

    assert resp.status_code == 401


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_binding_failure_detail_is_rewrapped(client, realm, dpop_key):
    # CHARACTERIZATION: changes in R5. The inner HTTPException is caught by `except Exception`
    # and its str() ("401: ...") is wrapped into a second detail.
    token = make_access_token(realm, new_dpop_key())

    resp = await call(client, dpop_key, token)

    assert resp.json() == {
        "detail": f"{PREFIX}401: Token is not bound to this DPoP key"
    }


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_expiry_library_text_reaches_client(client, realm, dpop_key):
    # CHARACTERIZATION: changes in R5. jwcrypto's message, with server timestamps, is echoed.
    token = make_access_token(realm, dpop_key, exp=int(time.time()) - 90)

    resp = await call(client, dpop_key, token)

    detail = resp.json()["detail"]
    assert detail.startswith(f"{PREFIX}Expired at ")
    assert "(leeway: 60)" in detail


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_malformed_token_library_text_reaches_client(client, dpop_key):
    # CHARACTERIZATION: changes in R5. jwcrypto's parser message is echoed.
    resp = await call(client, dpop_key, "not.a.jwt")

    assert resp.json() == {"detail": f"{PREFIX}Invalid JWS Object [Invalid format]"}


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_wrong_issuer_is_accepted(client, realm, dpop_key):
    # CHARACTERIZATION: changes in R5. `iss` is not checked.
    token = make_access_token(realm, dpop_key, iss="https://evil.example/realms/x")

    resp = await call(client, dpop_key, token)

    assert resp.status_code == 200


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_wrong_audience_is_accepted(client, realm, dpop_key):
    # CHARACTERIZATION: changes in R5. `aud` is not checked.
    token = make_access_token(realm, dpop_key, aud="some-other-client")

    resp = await call(client, dpop_key, token)

    assert resp.status_code == 200


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_missing_audience_is_accepted(client, realm, dpop_key):
    # CHARACTERIZATION: changes in R5. `aud` is not required.
    token = make_access_token(realm, dpop_key, drop=("aud",))

    resp = await call(client, dpop_key, token)

    assert resp.status_code == 200
