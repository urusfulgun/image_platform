"""Tests for DPoP proof generation."""
import json
import base64
import pytest

from bff_token_handler.auth.dpop import create_dpop_proof, get_public_jwk


def _decode_b64url(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def test_dpop_proof_has_three_parts():
    proof = create_dpop_proof("POST", "https://example.com/token")
    parts = proof.split(".")
    assert len(parts) == 3, "JWT must have header.payload.signature"


def test_dpop_proof_header_typ():
    proof = create_dpop_proof("GET", "https://example.com/resource")
    header_raw = _decode_b64url(proof.split(".")[0])
    header = json.loads(header_raw)
    assert header["typ"] == "dpop+jwt"
    assert header["alg"] == "RS256"
    assert "jwk" in header


def test_dpop_proof_payload_fields():
    proof = create_dpop_proof("POST", "https://auth.example.com/token")
    payload_raw = _decode_b64url(proof.split(".")[1])
    payload = json.loads(payload_raw)
    assert payload["htm"] == "POST"
    assert payload["htu"] == "https://auth.example.com/token"
    assert "jti" in payload
    assert "iat" in payload
    assert "jkt" in payload


def test_dpop_proofs_have_unique_jti():
    proof1 = create_dpop_proof("GET", "https://example.com")
    proof2 = create_dpop_proof("GET", "https://example.com")
    p1 = json.loads(_decode_b64url(proof1.split(".")[1]))
    p2 = json.loads(_decode_b64url(proof2.split(".")[1]))
    assert p1["jti"] != p2["jti"]


def test_public_jwk_has_required_fields():
    jwk = get_public_jwk()
    assert jwk["kty"] == "RSA"
    assert jwk["alg"] == "RS256"
    assert "n" in jwk
    assert "e" in jwk
