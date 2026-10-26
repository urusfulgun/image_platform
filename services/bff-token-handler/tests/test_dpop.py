"""Tests for DPoP proof generation."""
import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

from bff_token_handler.auth.dpop import (
    COORD_LEN,
    create_dpop_proof,
    generate_ec_key_pair,
    get_public_jwk,
)


def _decode_b64url(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


@pytest.fixture
def key_pair():
    return generate_ec_key_pair()


def test_dpop_proof_has_three_parts(key_pair):
    proof = create_dpop_proof("POST", "https://example.com/token", key_pair)
    parts = proof.split(".")
    assert len(parts) == 3, "JWT must have header.payload.signature"


def test_dpop_proof_header_typ(key_pair):
    proof = create_dpop_proof("GET", "https://example.com/resource", key_pair)
    header_raw = _decode_b64url(proof.split(".")[0])
    header = json.loads(header_raw)
    assert header["typ"] == "dpop+jwt"
    assert header["alg"] == "ES256"
    assert "jwk" in header


def test_dpop_proof_payload_fields(key_pair):
    proof = create_dpop_proof("POST", "https://auth.example.com/token", key_pair)
    payload_raw = _decode_b64url(proof.split(".")[1])
    payload = json.loads(payload_raw)
    assert payload["htm"] == "POST"
    assert payload["htu"] == "https://auth.example.com/token"
    assert "jti" in payload
    assert "iat" in payload
    assert "jkt" in payload
    assert "ath" not in payload


def test_dpop_proof_includes_ath_when_given(key_pair):
    proof = create_dpop_proof("GET", "https://example.com", key_pair, ath="token-hash")
    payload = json.loads(_decode_b64url(proof.split(".")[1]))
    assert payload["ath"] == "token-hash"


def test_dpop_proofs_have_unique_jti(key_pair):
    proof1 = create_dpop_proof("GET", "https://example.com", key_pair)
    proof2 = create_dpop_proof("GET", "https://example.com", key_pair)
    p1 = json.loads(_decode_b64url(proof1.split(".")[1]))
    p2 = json.loads(_decode_b64url(proof2.split(".")[1]))
    assert p1["jti"] != p2["jti"]


def test_dpop_proof_signature_verifies_with_embedded_jwk(key_pair):
    proof = create_dpop_proof("POST", "https://example.com/token", key_pair)
    h_b64, p_b64, s_b64 = proof.split(".")
    jwk = json.loads(_decode_b64url(h_b64))["jwk"]

    public_key = ec.EllipticCurvePublicNumbers(
        x=int.from_bytes(_decode_b64url(jwk["x"]), "big"),
        y=int.from_bytes(_decode_b64url(jwk["y"]), "big"),
        curve=ec.SECP256R1(),
    ).public_key()
    raw_signature = _decode_b64url(s_b64)
    r = int.from_bytes(raw_signature[:COORD_LEN], "big")
    s = int.from_bytes(raw_signature[COORD_LEN:], "big")

    # Raises InvalidSignature if the proof was not signed by this key
    public_key.verify(
        utils.encode_dss_signature(r, s),
        f"{h_b64}.{p_b64}".encode("ascii"),
        ec.ECDSA(hashes.SHA256()),
    )


def test_public_jwk_has_required_fields(key_pair):
    jwk = get_public_jwk(key_pair.public_key.public_numbers())
    assert jwk["kty"] == "EC"
    assert jwk["crv"] == "P-256"
    assert jwk["alg"] == "ES256"
    assert len(_decode_b64url(jwk["x"])) == COORD_LEN
    assert len(_decode_b64url(jwk["y"])) == COORD_LEN
