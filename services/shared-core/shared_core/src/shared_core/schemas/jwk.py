from typing import Literal
from pydantic import BaseModel, Field
from shared_core.shared_types import jwk as jwk_types


class ASKeyModel(BaseModel):
    kty: Literal["RSA", "EC"] = Field(..., description="Key Type (e.g., RSA or EC)")
    alg: str = Field(..., description="The algorithm intended for use with the key")
    use: Literal["sig", "enc"] = Field(
        "sig", description="Intended use: signature or encryption"
    )
    kid: str = Field(
        ..., description="Key ID: unique pointer used by Keycloak for rotation"
    )

    # RSA Specific Fields
    n: str | None = Field(None, description="RSA modulus")
    e: str | None = Field(None, description="RSA public exponent")

    # EC (Elliptic Curve) Specific Fields
    crv: str | None = Field(None, description="Curve name (e.g., P-256)")
    x: str | None = Field(None, description="X coordinate")
    y: str | None = Field(None, description="Y coordinate")

    x5c: list[str] | None = Field(None, description="X.509 certificate chain")

    model_config = {"extra": "ignore"}  # AS keys often have custom metadata


class DPoPClientPublicKey(BaseModel):
    """
    Public key structure for DPoP Proof header as per RFC 7638.
    Only includes the essential cryptographic parameters.
    """
    kty: Literal["RSA", "EC"] = Field(...)
    
    # RSA parameters
    n: str | None = Field(None)
    e: str | None = Field(None)
    
    # EC parameters
    crv: Literal["P-256", "P-384", "P-512"] | None = Field(None)
    x: str | None = Field(None)
    y: str | None = Field(None)

    # DPoP proofs should be strict; extra fields can change the JKT thumbprint
    model_config = {"extra": "forbid"}


class JSONWebKey(BaseModel):
    kid: str
    kty: jwk_types.PyblicKeyType
    alg: jwk_types.JSONWebKeySetType
    use: jwk_types.IntendedUseType


class ECJWK(JSONWebKey):
    kty: Literal["EC"]
    x: str
    y: str
    alg: jwk_types.ECJWKSetType
