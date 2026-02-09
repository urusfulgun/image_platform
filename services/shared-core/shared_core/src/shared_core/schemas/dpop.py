import uuid
from pydantic import BaseModel, Field, field_validator, model_validator, HttpUrl
from typing import Dict, Any, Literal, Self
import time

from shared_core.schemas import exceptions


class TemporalClaimsMixin(BaseModel):
    """Shared logic for anything with iat/exp/nbf."""
    iat: int = Field(..., description="Issued at timestamp")
    
    @field_validator("iat")
    @classmethod
    def validate_freshness(cls, v: int) -> int:
        # Ensure the token isn't from the future or too old (e.g., older than 2 mins)
        now = int(time.time())
        if v > now + 60:
            raise exceptions.DPoPClockSkewError("Token issued in the future")
        return v


class DPoPHeader(BaseModel):
    typ: Literal["dpop+jwt"]
    alg: str
    jwk: Dict[str, Any]  # The public key


class DPoPProofPayload(TemporalClaimsMixin):
    iss: str | None = Field(None, description="(RFC 9449) The client id")
    jti: str = Field(..., description="Unique identifier for replay protection")
    htm: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
    htu: HttpUrl = Field(..., description="The HTTP URI without query or fragment")
    nonce: str | None = Field(None, description="Server-provided freshness token")
    ath: str | None = Field(None, description="Required when calling Resource Servers")

    @field_validator("htu")
    @classmethod
    def validate_htu_constraints(cls, v: HttpUrl) -> str:
        # RFC 9449: htu MUST NOT contain query or fragment
        if v.query or v.fragment:
            raise exceptions.DPoPBindingError(
                "htu must not contain query parameters or fragments"
            )

        # We return the string representation for the model
        return str(v)


class DPoPProof(BaseModel):
    header: DPoPHeader
    payload: DPoPProofPayload

    @model_validator(mode="after")
    def check_key_exists(self) -> Self:
        if not self.header.jwk:
            raise ValueError("DPoP header must contain the public key (jwk)")
        return self
    
    @model_validator(mode="after")
    def validate_proof_integrity(self) -> Self:
        if not self.header.jwk:
            raise ValueError("DPoP header must contain jwk")
        # Ensure iat is fresh (Proofs should be very short-lived, e.g., 2 mins)
        now = int(time.time())
        if self.payload.iat < now - 120:
            raise exceptions.DPoPClockSkewError(
                "Token has expired (issued more than 2 minutes ago)"
            )
        return self


class ConfirmationClaim(BaseModel):
    jkt: str = Field(..., description="The SHA-256 JWK Thumbprint")


class DPoPAccessTokenPayload(TemporalClaimsMixin):
    iss: HttpUrl = Field(..., description="The Authorization Server issuer URL")
    sub: uuid.UUID
    iat: int
    exp: int
    nbf: int | None = Field(None, description="Token not valid before this timestamp")
    cnf: ConfirmationClaim  # This makes the token DPoP-bound
    scope: str | None = None

    def verify_iss(self, expected_as_url: HttpUrl) -> None:
        if str(self.iss).rstrip("/") != str(expected_as_url).rstrip("/"):
            raise exceptions.DPoPBindingError(
                f"Token issued by {self.iss}, bbut this RS only trusts {expected_as_url}"
            )
        
    @field_validator("iss", mode="before")
    @classmethod
    def validate_issuer(cls, v: HttpUrl | None) -> str | None:
        if v is None:
            raise exceptions.DPoPBindingError(
                "DPoP 'iss' mismatch: expected URL of issuer. Got None",
            )
        return v

    @field_validator("iat")
    @classmethod
    def validate_freshness(cls, v: int) -> int:
        # Ensure the token isn't from the future or too old (e.g., older than 2 mins)
        now = int(time.time())
        if v > now + 60:
            raise exceptions.DPoPClockSkewError("Token issued in the future")
        if v < now - 120:
            raise exceptions.DPoPClockSkewError(
                "Token has expired (issued more than 2 minutes ago)"
            )
        return v

    def check_expiration(self, leeway_seconds: int = 30):
        """
        Validates the entire temporal validity of the token in one pass.
        This allows us to compare exp and nbf against each other if needed.
        """
        now = int(time.time())

        # 1. Validate Expiration (Current time must be before exp + leeway)
        if now > (self.exp + leeway_seconds):
            raise exceptions.DPoPError(
                detail="Access Token has expired",
                error_code="invalid_token"
            )

        # 2. Validate Not Before (Current time must be after nbf - leeway)
        if self.nbf is not None:
            if now < (self.nbf - leeway_seconds):
                raise exceptions.DPoPError(
                    detail="Access Token is not yet valid (nbf check failed)",
                    error_code="token_not_yet_valid"
                )
        
        # 3. Sanity Check: Ensure nbf isn't after exp
        if self.nbf and self.nbf > self.exp:
            raise exceptions.DPoPError(
                detail="Malformed token: nbf cannot be after exp",
                error_code="invalid_token"
            )

    def verify_binding(self, incoming_jwk_thumbprint: str):
        """Matches the Proof's key to the Token's binding."""
        if self.cnf.jkt != incoming_jwk_thumbprint:
            raise exceptions.DPoPKeyMismatchError("Token is not bound to the provided private key")
        return True
