import base64
import hashlib


def compute_ath(access_token: str) -> str:
    """Computes the SHA-256 hash of the ASCII access token."""
    hash_digest = hashlib.sha256(access_token.encode("ascii")).digest()
    return base64.urlsafe_b64encode(hash_digest).decode("utf-8").rstrip("=")
