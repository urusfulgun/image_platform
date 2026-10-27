"""Constants and helpers shared by the BFF API characterization tests."""

import base64
import json

from shared_core.schemas.security.token_set import TokenSet

AUTH_ENDPOINT = (
    "http://keycloak.test/realms/image-platform/protocol/openid-connect/auth"
)
SUB = "0b5d2c1e-8f4a-4c3b-9d6e-7a1f2b3c4d5e"
ACCESS_TOKEN = "access-token-value"
REFRESH_TOKEN = "refresh-token-value"

PROFILE_CLAIMS = {
    "name": "Jane Doe",
    "given_name": "Jane",
    "family_name": "Doe",
    "preferred_username": "jane",
    "email": "jane@example.com",
    "email_verified": True,
}
# What Keycloak returns: the profile plus internal claims the BFF must not echo
USERINFO_CLAIMS = {
    "sub": SUB,
    "iss": "http://keycloak.test/realms/image-platform",
    **PROFILE_CLAIMS,
}


class FakeRedis:
    """The subset of redis.asyncio the stores use, over a dict.

    Behaves like decode_responses=True.
    """

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.data[key] = value
        self.ttls[key] = ttl

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.data.pop(key, None)
            self.ttls.pop(key, None)

    def keys(self, prefix: str) -> list[str]:
        return [k for k in self.data if k.startswith(prefix)]


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def make_id_token(claims: dict) -> str:
    """An unsigned compact JWS. The BFF decodes id tokens without verifying them."""
    header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = b64url(json.dumps(claims).encode())
    return f"{header}.{payload}.{b64url(b'not-a-signature')}"


def make_token_set(**overrides) -> TokenSet:
    fields = {
        "access_token": ACCESS_TOKEN,
        "refresh_token": REFRESH_TOKEN,
        "id_token": make_id_token(USERINFO_CLAIMS),
        "expires_in": 300,
        "token_type": "DPoP",
    } | overrides
    return TokenSet(**fields)


def decode_proof(proof: str) -> tuple[dict, dict]:
    """Header and payload of a DPoP proof JWT."""
    h_b64, p_b64, _ = proof.split(".")
    return json.loads(b64url_decode(h_b64)), json.loads(b64url_decode(p_b64))
