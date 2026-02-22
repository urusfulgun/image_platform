"""DPoP (Demonstrating Proof-of-Possession) key management and proof generation.

Generates an RSA key pair at module load. The private key is kept in memory
only — tokens bound to this key are useless without it.
"""
import json
import time
import uuid
import base64
import hashlib

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend


def _b64url(data: bytes) -> str:
    """URL-safe base64 encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _int_to_b64url(n: int) -> str:
    length = (n.bit_length() + 7) // 8
    return _b64url(n.to_bytes(length, "big"))


# Generate key pair at startup — one per process instance
_private_key: rsa.RSAPrivateKey = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend(),
)
_public_key = _private_key.public_key()
_pub_numbers = _public_key.public_key().public_numbers()


def get_public_jwk() -> dict:
    """Return the RSA public key as a JWK dict."""
    pub = _private_key.public_key()
    numbers = pub.public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": _int_to_b64url(numbers.n),
        "e": _int_to_b64url(numbers.e),
    }


def _jwk_thumbprint(jwk: dict) -> str:
    """Compute the RFC 7638 JWK thumbprint (SHA-256)."""
    # Canonical JSON with only required members, sorted by key
    canonical = json.dumps(
        {"e": jwk["e"], "kty": jwk["kty"], "n": jwk["n"]},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    digest = hashlib.sha256(canonical).digest()
    return _b64url(digest)


def _encode_header_payload(header: dict, payload: dict) -> bytes:
    """Encode header.payload as UTF-8 bytes for signing."""
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    return f"{h}.{p}".encode()


def create_dpop_proof(htm: str, htu: str) -> str:
    """Create a signed DPoP proof JWT for a given HTTP method and URI.

    Args:
        htm: HTTP method (e.g. "POST")
        htu: HTTP URI (e.g. "https://keycloak.example.com/token")

    Returns:
        Compact serialized DPoP proof JWT string.
    """
    jwk = get_public_jwk()
    thumbprint = _jwk_thumbprint(jwk)

    header = {
        "typ": "dpop+jwt",
        "alg": "RS256",
        "jwk": jwk,
    }
    payload = {
        "jti": str(uuid.uuid4()),
        "htm": htm.upper(),
        "htu": htu,
        "iat": int(time.time()),
        "jkt": thumbprint,
    }

    signing_input = _encode_header_payload(header, payload)
    signature = _private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())

    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    s = _b64url(signature)
    return f"{h}.{p}.{s}"
