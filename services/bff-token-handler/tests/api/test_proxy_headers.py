"""Characterization: exactly which headers /proxy sends to AssetService and back."""

import gzip

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

from bff_token_handler.auth.dpop import COORD_LEN, generate_dpop_ath, get_public_jwk
from bff_token_handler.settings import settings
from tests.api.helpers import SUB, b64url_decode, decode_proof

UPSTREAM_URL = "http://asset-service:8000/projects/p1/images/?limit=5"


def _proxy_get(client, headers=None):
    return client.get(
        "/proxy/projects/p1/images/", params={"limit": "5"}, headers=headers
    )


def test_authorization_is_replaced_with_dpop_access_token(
    client, seed_session, upstream
):
    session = seed_session()

    _proxy_get(client, headers={"Authorization": "Bearer client-supplied"})

    assert upstream.last.headers.get_list("authorization") == [
        f"DPoP {session.token_set.access_token}"
    ]


def test_dpop_proof_claims(client, seed_session, upstream):
    session = seed_session()

    _proxy_get(client)

    [proof] = upstream.last.headers.get_list("dpop")
    header, payload = decode_proof(proof)
    assert header["typ"] == "dpop+jwt"
    assert header["alg"] == "ES256"
    assert header["jwk"] == get_public_jwk(session.key_pair.public_key.public_numbers())
    assert payload["htm"] == "GET"
    # The query string is part of htu (see R5 for the RS-side mismatch)
    assert payload["htu"] == UPSTREAM_URL
    assert payload["ath"] == generate_dpop_ath(session.token_set.access_token)


def test_dpop_proof_is_signed_by_session_key(client, seed_session, upstream):
    session = seed_session()

    client.post("/proxy/projects/", json={"name": "x"})

    [proof] = upstream.last.headers.get_list("dpop")
    h_b64, p_b64, s_b64 = proof.split(".")
    raw = b64url_decode(s_b64)
    signature = utils.encode_dss_signature(
        int.from_bytes(raw[:COORD_LEN], "big"), int.from_bytes(raw[COORD_LEN:], "big")
    )
    # Raises InvalidSignature if another key signed it
    session.key_pair.public_key.verify(
        signature, f"{h_b64}.{p_b64}".encode("ascii"), ec.ECDSA(hashes.SHA256())
    )
    assert decode_proof(proof)[1]["htm"] == "POST"


def test_user_sub_comes_from_session_id_token(client, seed_session, upstream):
    seed_session()

    _proxy_get(client)

    assert upstream.last.headers.get_list("x-user-sub") == [SUB]


def test_hop_by_hop_headers_are_dropped(client, seed_session, upstream):
    seed_session()

    _proxy_get(
        client,
        headers={
            "Host": "evil.example",
            "Connection": "close",
            "Keep-Alive": "timeout=5",
            "Upgrade": "websocket",
            "Proxy-Connection": "keep-alive",
            "Transfer-Encoding": "chunked",
        },
    )

    headers = upstream.last.headers
    assert headers.get_list("host") == ["asset-service:8000"]
    # The client's value is dropped; httpx adds its own
    assert headers.get_list("connection") == ["keep-alive"]
    for name in ("keep-alive", "upgrade", "proxy-connection", "transfer-encoding"):
        assert name not in headers, name


def test_other_client_headers_are_forwarded(client, seed_session, upstream):
    seed_session()

    client.post(
        "/proxy/projects/",
        content=b"{}",
        headers={"X-Custom": "kept", "Content-Type": "application/json"},
    )

    headers = upstream.last.headers
    assert headers["x-custom"] == "kept"
    assert headers["content-type"] == "application/json"


@pytest.mark.known_bug
def test_client_user_sub_is_forwarded_before_bffs(client, seed_session, upstream):
    # CHARACTERIZATION: changes in R1 (proxy strips client identity headers)
    seed_session()

    _proxy_get(client, headers={"X-User-Sub": "attacker-chosen-sub"})

    assert upstream.last.headers.get_list("x-user-sub") == ["attacker-chosen-sub", SUB]


@pytest.mark.known_bug
def test_client_dpop_is_forwarded_next_to_bffs(client, seed_session, upstream):
    # CHARACTERIZATION: changes in R1 (proxy strips client DPoP headers)
    seed_session()

    _proxy_get(client, headers={"DPoP": "client-proof"})

    proofs = upstream.last.headers.get_list("dpop")
    assert len(proofs) == 2
    assert proofs[0] == "client-proof"
    assert decode_proof(proofs[1])[1]["htu"] == UPSTREAM_URL


@pytest.mark.known_bug
def test_session_cookie_is_forwarded_upstream(client, seed_session, upstream):
    # CHARACTERIZATION: changes in R1 (proxy strips the Cookie header)
    session = seed_session()

    _proxy_get(client)

    assert (
        f"{settings.session_cookie_name}={session.sid}"
        in upstream.last.headers["cookie"]
    )


@pytest.mark.known_bug
def test_upstream_response_headers_are_copied_verbatim(client, seed_session, upstream):
    # CHARACTERIZATION: changes in R17 (filter upstream response headers)
    seed_session()
    compressed = gzip.compress(b'{"ok": true}')
    upstream.reply = lambda request: httpx.Response(
        200,
        content=compressed,
        headers={"content-encoding": "gzip", "x-upstream": "yes"},
    )

    with client.stream("GET", "/proxy/projects/") as resp:
        raw = b"".join(resp.iter_raw())

    assert resp.headers["x-upstream"] == "yes"
    # httpx already decoded the body, yet the gzip header and its length are kept
    assert resp.headers["content-encoding"] == "gzip"
    assert resp.headers["content-length"] == str(len(compressed))
    assert raw == b'{"ok": true}'
