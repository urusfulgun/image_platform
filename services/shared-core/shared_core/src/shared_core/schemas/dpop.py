import uuid
from pydantic import BaseModel, Field, field_validator, model_validator, HttpUrl
from typing import Dict, Any, Literal, Self
import time

from shared_core.schemas import exceptions
from shared_core.shared_types.http_request import MethodType
from shared_core.schemas import jwk as jwk_schema


class TemporalClaimsMixin(BaseModel):
    """Shared logic for anything with iat/exp/nbf/jti."""

    iat: int = Field(
        default_factory=lambda: int(time.time()),
        description="Time at which the JWT was created.",
    )

    jti: str = Field(
        default_factory=lambda: str(uuid.uuid7()),
        description="Unique identifier for the proof to prevent replay.",
    )

    @field_validator("iat")
    @classmethod
    def validate_freshness(cls, v: int) -> int:
        # Ensure the token isn't from the future or too old (e.g., older than 2 mins)
        now = int(time.time())
        if v > now + 60:
            raise exceptions.DPoPClockSkewError("Token issued in the future")
        return v


class DPoPProofHeader(BaseModel):
    """
    Represents the header of a DPoP Proof JWT.
    As per RFC 9449, this must contain the 'typ' and 'jwk' claims.
    """

    typ: Literal["dpop+jwt"] = Field(
        ..., description="Must be exactly 'dpop+jwt' as per RFC 9449"
    )

    alg: Literal["ES256"] = Field(
        default="ES256", description="Asymmetric algorithm used to sign the proof"
    )

    jwk: jwk_schema.DPoPClientPublicKey = Field(
        ..., description="The public key used to sign this JWT, in JWK format"
    )

    class Config:
        # Prevents extra fields from being injected into the header model
        extra = "forbid"
        # Ensures the model is read-only during the validation lifecycle
        allow_mutation = False


class AccessTokenJwtHeader(BaseModel):
    # 'at+jwt' is the RFC 9068 standard
    typ: Literal["at+jwt"] = Field(..., description="JWT type")

    # Allow common secure algorithms; ES256 is preferred for DPoP
    alg: Literal["ES256"] = Field(..., description="Signing algorithm")

    # Key ID is essential for the Resource Server to find the AS public key
    kid: str = Field(..., min_length=1, description="Key ID")

    # Optional: X.509 Certificate thumbprint (common in enterprise OIDC)
    x5t: str | None = None

    class Config:
        frozen = True  # Makes the model immutable and hashable


class DPoPProofPayload(TemporalClaimsMixin):
    iat: int = Field(
        default_factory=lambda: int(time.time()),
        description="Time at which the JWT was created.",
    )

    htm: MethodType = Field(..., description="The HTTP Method of the request.")
    htu: HttpUrl = Field(..., description="The HTTP URI without query or fragment")

    sub: str | None = Field(None, description="(RFC 9449) The client id")
    nonce: str | None = Field(None, description="Server-provided freshness token")
    ath: str | None = Field(None, description="Required when calling Resource Servers")

    @field_validator("htu", mode="before")
    @classmethod
    def validate_htu_constraints(cls, v: Any) -> str:
        # RFC 9449: htu MUST NOT contain query or fragment
        s = str(v)
        if "?" in s or "#" in s:
            raise ValueError("htu must not contain query or fragment")
        return s.rstrip("/")

    @field_validator("iat")
    @classmethod
    def validate_iat(cls, v: int) -> int:
        now = int(time.time())
        # Proofs should be extremely short-lived (usually +/- 60-120 seconds)
        if v > now + 60:
            raise ValueError("Proof iat is in the future (clock skew)")
        if v < now - 120:
            raise ValueError("Proof has expired (issued too long ago)")
        return v


class DPoPProof(BaseModel):
    header: DPoPProofHeader
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
    """Represents the 'cnf' (Confirmation) claim, often used for Proof-of-Possession.

    Mandatory for DPoP: Contains the JWK Thumbprint (jkt)
    of the public key used to sign the DPoP proof.
    """

    jkt: str = Field(
        ...,
        description="The SHA-256 JWK Thumbprint."
        "JWK Thumbprint used to bind the token to a specific key."
        "Validates that the client presenting the token "
        "possesses the private key used during token issuance.",
    )


class DPoPAccessTokenPayload(TemporalClaimsMixin):
    ver: int = Field(1, description="The version of the access token schema.")
    iss: HttpUrl = Field(
        ...,
        description="Issuer: The URL of the authorization server that issued the token.",
    )
    aud: str | list[str] = Field(
        ...,
        description="Audience: The intended recipient of the token (typically your API).",
    )
    exp: int = Field(
        ..., description="Expiration: Unix timestamp of when the token expires."
    )
    cid: str = Field(
        ...,
        description="Client ID: The ID of the application that requested the token.",
    )
    uid: str = Field(
        ..., description="User ID: The unique identifier for the user in STS or IdP."
    )
    sub: str = Field(..., description="Subject: Usually the user's email or username.")
    nbf: int | None = Field(None, description="Token not valid before this timestamp")
    cnf: ConfirmationClaim  # This makes the token DPoP-bound
    auth_time: int = Field(
        ...,
        description="Authentication Time: Unix timestamp of when the user originally authenticated."
        "Time of original authentication. Vital for step-up security.",
    )
    scp: list[str] = Field(
        default_factory=list,
        description="Scopes: A list of permissions granted by this token. (e.g., 'openid profile')",
    )

    model_config = {
        "extra": "ignore",
        "json_schema_extra": {
            "example": {
                "sub": "user@example.com",
                "cnf": {"jkt": "2HR2BW5-tan1aI6yIPHVOHwirAy4kQGWULoQHKUO0s4"},
                "scp": "openid profile email",
            }
        },
    }

    def is_expired(self, leeway: int = 30) -> bool:
        return int(time.time()) > (self.exp + leeway)

    def verify_binding(self, thumbprint: str):
        if self.cnf.jkt != thumbprint:
            raise exceptions.DPoPKeyMismatchError("Key binding mismatch")

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
                detail="Access Token has expired", error_code="invalid_token"
            )

        # 2. Validate Not Before (Current time must be after nbf - leeway)
        if self.nbf is not None:
            if now < (self.nbf - leeway_seconds):
                raise exceptions.DPoPError(
                    detail="Access Token is not yet valid (nbf check failed)",
                    error_code="token_not_yet_valid",
                )

        # 3. Sanity Check: Ensure nbf isn't after exp
        if self.nbf and self.nbf > self.exp:
            raise exceptions.DPoPError(
                detail="Malformed token: nbf cannot be after exp",
                error_code="invalid_token",
            )


class IDTokenHeader(BaseModel):
    typ: Literal["JWT"] = Field("JWT", description="Standard JWT type for ID Tokens")
    alg: Literal["RS256", "ES256"] = Field(..., description="Signature algorithm")
    kid: str = Field(..., description="Key ID for the identity provider's public key")

    model_config = {"frozen": True}


class IDTokenPayload(BaseModel):
    # Standard OIDC Claims
    iss: str = Field(..., description="Issuer: The Keycloak Realm URL")
    sub: str = Field(..., description="Subject: The unique User ID")
    aud: str = Field(..., description="Audience: The Client ID of your app")
    exp: int = Field(..., description="Expiration time")
    iat: int = Field(..., description="Issued at time")
    auth_time: int | None = Field(None, description="Time of original authentication")

    # User Profile Claims (Common in Keycloak)
    name: str | None = Field(None, description="Full name of the user")
    given_name: str | None = Field(None, alias="given_name")
    family_name: str | None = Field(None, alias="family_name")
    preferred_username: str | None = Field(None, description="Keycloak username")
    email: str | None = Field(None, description="User's email address")
    email_verified: bool = Field(False, description="Whether the email is verified")

    # Session Management
    sid: str | None = Field(None, description="Session ID for logout purposes")
    azp: str = Field(..., description="Authorized party (the Client ID)")
    nonce: str | None = Field(None, description="Nonce to prevent replay attacks")

    # Keycloak Roles (Often mapped into ID Token)
    realm_access: dict[str, list[str]] | None = None
    resource_access: dict[str, Any] | None = None

    @field_validator("iss", mode="before")
    @classmethod
    def normalize_iss(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.rstrip("/")
        return str(v)

    def is_valid(self, leeway: int = 30) -> bool:
        """Checks if the ID token is still chronologically valid."""
        now = int(time.time())
        return self.exp + leeway > now

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",  # Keycloak adds many custom claims
    }


class AuthorizeRequest(BaseModel):
    # The client ID is usually an alphanumeric string from Auth provider
    client_id: str = Field(..., description="The unique ID of the Auth application")

    # In this flow, response_type must be 'code'
    response_type: Literal["code"] = Field(
        ..., description="The type of authorization grant"
    )

    # Scope can be a single string or space-separated values
    scope: str = Field(
        ..., description="Requested permissions (e.g., 'openid profile')"
    )

    # Must be a valid HTTPS URL
    redirect_uri: HttpUrl = Field(
        ..., description="The callback URL registered in Okta"
    )

    # State is used for security (CSRF protection)
    state: str = Field(
        ...,
        description="An opaque value used to maintain state between request and callback",
    )
    code_challenge: str
    code_challenge_method: Literal["S256"]
    response_type: Literal["code"]
    response_mode: Literal["query"]

    @field_validator("scope")
    @classmethod
    def validate_openid_scope(cls, v: str):
        if "openid" not in v.split():
            raise ValueError("The 'openid' scope is required for OIDC requests.")
        return v

    @model_validator(mode="after")
    def validate_offline_access(self) -> Self:
        scopes = self.scope.split()

        # 2. logical check: offline_access requires 'code' in response_type
        if "offline_access" in scopes:
            if "code" not in self.response_type:
                # Per specification, it can be ignored, but in a strict validator
                # we often raise an error to alert the developer.
                raise ValueError(
                    "scope 'offline_access' can only be requested if "
                    "response_type contains 'code'."
                )
        return self


class AccessTokenRequest(BaseModel):
    grant_type: Literal["authorization_code"]
    code: str
    redirect_uri: str
    code_verifier: str


class RefreshAccessTokenRequestData(BaseModel):
    grant_type: Literal["refresh_token"]
    refresh_token: str


def validate_granted_permissions(
    granted_scope_str: str, required_scopes: set[str]
) -> bool:
    granted_scopes: set[str] = set(granted_scope_str.split())
    missing = required_scopes - granted_scopes

    if missing:
        # Logic: If the user didn't give us profile access, we can't show their name.
        raise PermissionError(f"User did not grant required scopes: {missing}")

    return True
