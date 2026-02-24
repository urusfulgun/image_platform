"""DPoP (Demonstrating Proof-of-Possession) key management and proof generation.

Generates an RSA key pair at module load. The private key is kept in memory
only — tokens bound to this key are useless without it.
"""

import json
import secrets
import time
from typing import NamedTuple
import uuid
import base64
import hashlib

from cryptography.hazmat.primitives.asymmetric import rsa, padding, ec, utils
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from shared_core.dto.key_pair import KeyPair

COORD_LEN = 32


def generate_dpop_ath(access_token: str) -> str:
    """
    Generates the 'ath' (Access Token Hash) claim for a DPoP proof.

    Args:
        access_token: The full string value of the JWT access token.

    Returns:
        A base64url-encoded SHA-256 hash of the token.
    """
    # 1. SHA-256 hash of the ASCII encoding of the access token
    hash_digest = hashlib.sha256(access_token.encode("ascii")).digest()

    # 2. Base64url encode the digest
    # urlsafe_b64encode uses '-' and '_' instead of '+' and '/'
    binary_b64 = base64.urlsafe_b64encode(hash_digest)

    # 3. Convert to string and strip the padding (=) as per RFC 7515
    return binary_b64.decode("ascii").rstrip("=")


def _b64url(data: bytes) -> str:
    """Encode bytes to a Base64URL string without padding."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _int_to_b64url(val: int, length: int) -> str:
    """Convert integer to fixed-length base64url string as per RFC 7518."""
    # EC coordinates must be padded to the byte length of the curve (32 bytes for P-256)
    byte_val = val.to_bytes(length, "big")
    return _b64url(byte_val)


# Generate key pair at startup — one per process instance
def generate_ec_key_pair() -> KeyPair:
    private_key: ec.EllipticCurvePrivateKey = ec.generate_private_key(ec.SECP256R1())
    public_key: ec.EllipticCurvePublicKey = private_key.public_key()
    key_pair = KeyPair(private_key, public_key)
    return key_pair


def get_public_jwk(public_numbers: ec.EllipticCurvePublicNumbers) -> dict:
    """Return the EC public key as a JWK dict (ES256)."""
    # Assuming _pub_numbers is available from your context
    # P-256 (SECP256R1) coordinate length is 32 bytes

    return {
        "kty": "EC",
        "crv": "P-256",
        "use": "sig",
        "alg": "ES256",
        "x": _int_to_b64url(public_numbers.x, COORD_LEN),
        "y": _int_to_b64url(public_numbers.y, COORD_LEN),
    }


def _jwk_thumbprint(jwk: dict) -> str:
    """Compute the RFC 7638 JWK thumbprint for an EC key (SHA-256)."""
    # REQUIRED members for EC: crv, kty, x, y (lexicographical order)
    required_data = {"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"], "y": jwk["y"]}

    # Canonical JSON: no whitespace, keys sorted
    canonical = json.dumps(required_data, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )

    digest = hashlib.sha256(canonical).digest()
    return _b64url(digest)


def _encode_header_payload(header: dict, payload: dict) -> bytes:
    """
    Encode header and payload as UTF-8 bytes for signing.
    Follows JWS Compact Serialization (RFC 7515).
    """
    # 1. Serialize to JSON with NO whitespace (separators=(',', ':'))
    # 2. Encode to UTF-8 bytes
    # 3. Base64URL encode without padding
    h_json = json.dumps(header, separators=(",", ":")).encode("utf-8")
    p_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    h_b64 = _b64url(h_json)
    p_b64 = _b64url(p_json)

    # The signing input is 'ASCII(HEADER) + "." + ASCII(PAYLOAD)'
    return f"{h_b64}.{p_b64}".encode("ascii")


def decode_jwt_token(token: str):
    """
    Reverses the encoding of a JWT token.
    Returns: (header_dict, payload_dict, signature_bytes)
    """
    # 1. Split the string into its 3 Base64URL components
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format. Expected 3 parts.")

    h_b64, p_b64, s_b64 = parts

    def _un_b64url(data: str) -> bytes:
        # Add back required padding for the base64 library
        missing_padding = len(data) % 4
        if missing_padding:
            data += "=" * (4 - missing_padding)
        return base64.urlsafe_b64decode(data)

    # 2. Decode Header and Payload back into Dictionaries
    header = json.loads(_un_b64url(h_b64).decode("utf-8"))
    payload = json.loads(_un_b64url(p_b64).decode("utf-8"))

    # 3. Decode Signature back into raw Bytes
    # (The signature remains bytes because it's cryptographic data, not JSON)
    raw_signature = _un_b64url(s_b64)

    return header, payload, raw_signature


def create_dpop_proof(
    htm: str,
    htu: str,
    key_pair: KeyPair,
    ath: str | None = None,
) -> str:
    """Create a signed DPoP proof JWT for a given HTTP method and URI.

    Args:
        htm: HTTP method (e.g. "POST")
        htu: HTTP URI (e.g. "https://keycloak.example.com/token")

    Returns:
        Compact serialized DPoP proof JWT string.
    """
    private_key, public_key = key_pair
    public_numbers: ec.EllipticCurvePublicNumbers = public_key.public_numbers()
    jwk = get_public_jwk(public_numbers=public_numbers)
    thumbprint = _jwk_thumbprint(jwk)

    header = {
        "typ": "dpop+jwt",
        "alg": "ES256",
        "jwk": jwk,
    }
    payload = {
        "jti": secrets.token_hex(16),
        "htm": htm.upper(),
        "htu": htu,
        "iat": int(time.time()),
        "jkt": thumbprint,
    }
    if ath:
        payload["ath"] = ath

    # 1. Prepare signing input
    signing_input: bytes = _encode_header_payload(header, payload)
    # 2. Sign using ECDSA
    # IMPORTANT: We use utils.decode_dss_signature to convert DER to Raw
    # if using older versions, but most modern JWT libs handle this.
    # For 'cryptography' raw signing:
    signature_der: bytes = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(signature_der)

    # Each coordinate must be 32 bytes for P-256
    raw_signature = r.to_bytes(COORD_LEN, "big") + s.to_bytes(COORD_LEN, "big")

    # 4. Assemble the final JWS Compact Serialization
    h_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    s_b64 = _b64url(raw_signature)
    return f"{h_b64}.{p_b64}.{s_b64}"
