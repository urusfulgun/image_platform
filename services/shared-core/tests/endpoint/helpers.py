"""Keys, tokens and DPoP proofs for the rs_dpop characterization tests.

Proofs are built with PyJWT directly; shared-core must not import bff-token-handler.
"""

import base64
import hashlib
import time
import uuid
from dataclasses import dataclass

import jwt
import jwt.algorithms
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

BASE_URL = "http://asset-service:8000"
ISSUER = "http://keycloak:8080/realms/image-platform"
AUDIENCE = "account"
SUB = "11111111-2222-3333-4444-555555555555"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def ath(token: str) -> str:
    return b64url(hashlib.sha256(token.encode()).digest())


@dataclass(frozen=True)
class RealmKey:
    """Stands in for Keycloak's realm signing key."""

    private: rsa.RSAPrivateKey
    kid: str

    @property
    def jwk(self) -> dict:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
            self.private.public_key(), as_dict=True
        )
        return {**jwk, "kid": self.kid, "alg": "RS256", "use": "sig"}

    @property
    def public_key_b64(self) -> str:
        """What `KeycloakOpenID.public_key()` returns.

        Base64 DER SubjectPublicKeyInfo.
        """
        der = self.private.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return base64.b64encode(der).decode()


def new_realm_key() -> RealmKey:
    return RealmKey(
        rsa.generate_private_key(public_exponent=65537, key_size=2048), uuid.uuid4().hex
    )


def new_dpop_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def public_jwk(key: ec.EllipticCurvePrivateKey) -> dict:
    return jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True)


def rfc7638_thumbprint(key: ec.EllipticCurvePrivateKey) -> str:
    """RFC 7638 §3 for EC keys, built by hand from the public numbers."""
    nums = key.public_key().public_numbers()
    x = b64url(nums.x.to_bytes(32, "big"))
    y = b64url(nums.y.to_bytes(32, "big"))
    canonical = f'{{"crv":"P-256","kty":"EC","x":"{x}","y":"{y}"}}'
    return b64url(hashlib.sha256(canonical.encode()).digest())


def make_access_token(
    realm: RealmKey,
    cnf_key: ec.EllipticCurvePrivateKey | None,
    *,
    signing_key: rsa.RSAPrivateKey | None = None,
    drop: tuple[str, ...] = (),
    **claims,
) -> str:
    """An RS256 access token as Keycloak issues it, bound to `cnf_key` via `cnf.jkt`."""
    now = int(time.time())
    payload = {
        "sub": SUB,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 300,
        "typ": "Bearer",
        "azp": "bff-client",
    }
    if cnf_key is not None:
        payload["cnf"] = {"jkt": rfc7638_thumbprint(cnf_key)}
    payload.update(claims)
    for name in drop:
        payload.pop(name, None)
    return jwt.encode(
        payload,
        signing_key or realm.private,
        algorithm="RS256",
        headers={"kid": realm.kid},
    )


def make_proof(
    key: ec.EllipticCurvePrivateKey,
    htm: str,
    htu: str,
    token: str | None,
    *,
    signing_key=None,
    algorithm: str = "ES256",
    header: dict | None = None,
    drop: tuple[str, ...] = (),
    **claims,
) -> str:
    """A DPoP proof (RFC 9449) carrying `key`'s public JWK in its header."""
    payload = {
        "jti": str(uuid.uuid4()),
        "htm": htm,
        "htu": htu,
        "iat": int(time.time()),
    }
    if token is not None:
        payload["ath"] = ath(token)
    payload.update(claims)
    for name in drop:
        payload.pop(name, None)
    headers = {"typ": "dpop+jwt", "jwk": public_jwk(key)}
    if header is not None:
        headers = header
    return jwt.encode(payload, signing_key or key, algorithm=algorithm, headers=headers)


def dpop_headers(token: str, proof: str) -> dict[str, str]:
    return {"Authorization": f"DPoP {token}", "DPoP": proof}
