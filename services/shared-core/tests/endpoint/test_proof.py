"""Characterization: DPoP proof checks in validate_dpop (rs_dpop.py).

The proof is verified with PyJWT against the `jwk` in its own header (ES256 only),
then `cnf.jkt`, `ath`, `htu` (request URL without query) and `htm` are compared.
Nothing else is.
"""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from helpers import (
    BASE_URL,
    dpop_headers,
    make_access_token,
    make_proof,
    new_dpop_key,
    public_jwk,
)

URL = f"{BASE_URL}/echo"
PREFIX = "DPoP Validation Failed: "


@pytest.fixture
def token(realm, dpop_key):
    return make_access_token(realm, dpop_key)


async def send(client, token, proof, path="/echo", method="GET"):
    return await client.request(method, path, headers=dpop_headers(token, proof))


# --- signature and format ----------------------------------------------------


@pytest.mark.asyncio
async def test_proof_signed_by_other_key_than_its_jwk_is_401(client, dpop_key, token):
    proof = make_proof(dpop_key, "GET", URL, token, signing_key=new_dpop_key())

    resp = await send(client, token, proof)

    assert resp.status_code == 401


@pytest.mark.parametrize(
    ("algorithm", "signing_key"),
    [
        ("RS256", rsa.generate_private_key(public_exponent=65537, key_size=2048)),
        ("HS256", "a-shared-secret-that-is-long-enough-for-hs256"),
    ],
)
@pytest.mark.asyncio
async def test_non_es256_proof_is_401(client, dpop_key, token, algorithm, signing_key):
    proof = make_proof(
        dpop_key, "GET", URL, token, signing_key=signing_key, algorithm=algorithm
    )

    resp = await send(client, token, proof)

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_malformed_proof_is_401(client, token):
    resp = await send(client, token, "garbage")

    assert resp.status_code == 401
    assert resp.json()["detail"].startswith(PREFIX)


@pytest.mark.asyncio
async def test_proof_with_past_exp_is_401(client, dpop_key, token):
    proof = make_proof(dpop_key, "GET", URL, token, exp=int(time.time()) - 10)

    resp = await send(client, token, proof)

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_proof_with_future_iat_is_401(client, dpop_key, token):
    # PyJWT itself rejects an `iat` in the future (no leeway); validate_dpop adds no
    # window.
    proof = make_proof(dpop_key, "GET", URL, token, iat=int(time.time()) + 3600)

    resp = await send(client, token, proof)

    assert resp.status_code == 401
    assert resp.json() == {"detail": f"{PREFIX}The token is not yet valid (iat)"}


# --- ath / htm / htu ---------------------------------------------------------


@pytest.mark.asyncio
async def test_ath_for_another_token_is_401(client, dpop_key, token):
    proof = make_proof(dpop_key, "GET", URL, "some-other-token")

    resp = await send(client, token, proof)

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_ath_is_401(client, dpop_key, token):
    proof = make_proof(dpop_key, "GET", URL, None)

    resp = await send(client, token, proof)

    assert resp.status_code == 401


@pytest.mark.parametrize("htm", ["POST", "get"])
@pytest.mark.asyncio
async def test_wrong_htm_is_401(client, dpop_key, token, htm):
    proof = make_proof(dpop_key, htm, URL, token)

    resp = await send(client, token, proof)

    assert resp.status_code == 401


@pytest.mark.parametrize(
    "htu",
    [
        f"{BASE_URL}/other",
        "http://localhost/echo",
        "https://asset-service:8000/echo",
        f"{BASE_URL}/echo/",
    ],
)
@pytest.mark.asyncio
async def test_wrong_htu_is_401(client, dpop_key, token, htu):
    proof = make_proof(dpop_key, "GET", htu, token)

    resp = await send(client, token, proof)

    assert resp.status_code == 401


@pytest.mark.known_bug
@pytest.mark.parametrize(
    ("proof_kwargs", "detail"),
    [
        ({"htm": "POST"}, "DPoP 'htm' mismatch"),
        ({"htu": f"{BASE_URL}/other"}, "DPoP target URL mismatch"),
        ({"ath_token": "some-other-token"}, "DPoP 'ath' mismatch"),
    ],
)
@pytest.mark.asyncio
async def test_claim_mismatch_detail_is_rewrapped(
    client, dpop_key, token, proof_kwargs, detail
):
    # CHARACTERIZATION: changes in R5. The inner HTTPException is re-wrapped by
    # `except Exception`.
    htm = proof_kwargs.get("htm", "GET")
    htu = proof_kwargs.get("htu", URL)
    proof = make_proof(dpop_key, htm, htu, proof_kwargs.get("ath_token", token))

    resp = await send(client, token, proof)

    assert resp.json() == {"detail": f"{PREFIX}401: {detail}"}


@pytest.mark.known_bug
@pytest.mark.parametrize(
    ("make", "detail"),
    [
        (lambda key, token: "garbage", "Not enough segments"),
        (
            lambda key, token: make_proof(
                key, "GET", URL, token, header={"typ": "dpop+jwt"}
            ),
            "'jwk'",
        ),
        (
            lambda key, token: make_proof(
                key, "GET", URL, token, signing_key=new_dpop_key()
            ),
            "Signature verification failed",
        ),
    ],
    ids=["malformed", "no-jwk", "wrong-signer"],
)
@pytest.mark.asyncio
async def test_proof_library_text_reaches_client(client, dpop_key, token, make, detail):
    # CHARACTERIZATION: changes in R5. PyJWT messages (and a bare KeyError) are echoed.
    resp = await send(client, token, make(dpop_key, token))

    assert resp.status_code == 401
    assert resp.json() == {"detail": f"{PREFIX}{detail}"}


# --- claims that are not checked ---------------------------------------------


@pytest.mark.known_bug
@pytest.mark.parametrize(
    "proof_kwargs",
    [
        {"drop": ("iat",)},
        {"iat": int(time.time()) - 3600},
        {"drop": ("jti",)},
    ],
    ids=["no-iat", "iat-hour-old", "no-jti"],
)
@pytest.mark.asyncio
async def test_unchecked_iat_and_jti_are_accepted(
    client, dpop_key, token, proof_kwargs
):
    # CHARACTERIZATION: changes in R5. No `iat` window and no `jti` requirement.
    proof = make_proof(dpop_key, "GET", URL, token, **proof_kwargs)

    resp = await send(client, token, proof)

    assert resp.status_code == 200


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_replayed_proof_is_accepted(client, dpop_key, token):
    # CHARACTERIZATION: changes in R5. There is no `jti` replay cache.
    proof = make_proof(dpop_key, "GET", URL, token)

    first = await send(client, token, proof)
    second = await send(client, token, proof)

    assert (first.status_code, second.status_code) == (200, 200)


@pytest.mark.known_bug
@pytest.mark.parametrize("typ", ["JWT", None], ids=["typ-JWT", "no-typ"])
@pytest.mark.asyncio
async def test_proof_typ_is_not_checked(client, dpop_key, token, typ):
    # CHARACTERIZATION: changes in R5. `typ: dpop+jwt` is not required.
    proof = make_proof(
        dpop_key, "GET", URL, token, header={"typ": typ, "jwk": public_jwk(dpop_key)}
    )
    assert jwt.get_unverified_header(proof).get("typ") == typ

    resp = await send(client, token, proof)

    assert resp.status_code == 200


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_htu_with_query_is_rejected(client, dpop_key, token):
    # CHARACTERIZATION: changes in R5. The BFF puts the full upstream URL, query
    # included, in `htu`, but validate_dpop compares against the request URL with the
    # query stripped.
    proof = make_proof(dpop_key, "GET", f"{URL}?page=2", token)

    resp = await send(client, token, proof, path="/echo?page=2")

    assert resp.status_code == 401
    assert resp.json() == {"detail": f"{PREFIX}401: DPoP target URL mismatch"}
