class DPoPError(Exception):
    """Base exception for all DPoP-related errors."""

    message = "An error occurred during DPoP validation"

    def __init__(
        self,
        detail: str = "DPoP validation failed",
        error_code: str = "invalid_dpop_proof",
    ):
        self.detail = detail
        self.error_code = error_code
        super().__init__(self.detail)


class DPoPInvalidTokenError(DPoPError):
    """The JWT structure itself is malformed or invalidly signed."""

    message = "DPoP proof JWT is malformed or signature is invalid"


class DPoPClockSkewError(DPoPError):
    """The 'iat' claim is outside the acceptable window."""

    message = "DPoP proof iat is outside the allowed time window"

    def __init__(self, detail: str = "Token timing is outside the permitted window"):
        super().__init__(detail=detail, error_code="use_dpop_nonce")


class DPoPBindingError(DPoPError):
    """Mismatch between proof and the HTTP request (htm, htu, or ath)."""

    message = "DPoP proof binding validation failed"

    def __init__(self, detail: str):
        super().__init__(detail=detail, error_code="invalid_dpop_proof")


class DPoPNonceError(DPoPError):
    """The server-provided nonce is missing, invalid, or expired."""

    message = "DPoP nonce is invalid or expired"

    def __init__(self, detail: str = "DPoP nonce is invalid or expired"):
        super().__init__(detail=detail, error_code="use_dpop_nonce")


class DPoPReplayError(DPoPError):
    """The 'jti' has already been used."""

    message = "DPoP proof has already been used (replay detected)"

    def __init__(self, detail: str = "DPoP proof replay detected"):
        super().__init__(detail=detail, error_code="invalid_dpop_proof")


class DPoPNotBoundError(DPoPError):
    """Raised when the Access Token is missing the 'cnf' claim."""

    def __init__(
        self,
        detail: str = "The provided Access Token is not sender-constrained (missing cnf claim).",
    ):
        super().__init__(detail=detail, error_code="invalid_token")


class DPoPKeyMismatchError(DPoPError):
    """Raised when the proof key does not match the token's jkt."""

    detail = "The DPoP proof key does not match the thumbprint bound to the token."
    error_code = "invalid_grant"

    def __init__(
        self,
        detail: str = "The DPoP proof key does not match the thumbprint bound to the token.",
    ):
        super().__init__(detail=detail, error_code="invalid_grant")
