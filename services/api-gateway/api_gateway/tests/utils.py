import base64
import hashlib
import time
from joserfc import jwt, jwk
from joserfc.jwk import thumbprint


def compute_ath(access_token: str) -> str:
    """Computes the SHA-256 hash of the ASCII access token."""
    hash_digest = hashlib.sha256(access_token.encode("ascii")).digest()
    return base64.urlsafe_b64encode(hash_digest).decode("utf-8").rstrip("=")


def create_dpop_proof(client_key, method, url, ath=None):
    header = {
        "typ": "dpop+jwt",
        "alg": "ES256",
        "jwk": client_key.as_dict(public_only=True)
    }
    payload = {
        "jti": "unique-id-123",
        "htm": method,
        "htu": url,
        "iat": int(time.time())
    }
    if ath:
        payload["ath"] = ath
    return jwt.encode(header, payload, client_key)

