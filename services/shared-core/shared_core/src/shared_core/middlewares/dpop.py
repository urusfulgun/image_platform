import secrets
import base64
import hashlib
from typing import Optional

from fastapi import Request, HTTPException, status
from pydantic import ValidationError
from shared_core.helpers.key_importing import convert_to_joserfc_key
from shared_core.schemas import exceptions
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from joserfc import jwt, jwk, jws, errors as joserfc_errors
from joserfc.jwk import thumbprint
import redis.asyncio as redis

from shared_core.schemas.dpop import (
    DPoPProofHeader,
    DPoPProofPayload,
    DPoPAccessTokenPayload,
    DPoPProof,
)


# Define the Lua script as a constant
# ARGV[1] is the nonce key
NONCE_CHECK_LUA = """
local deleted = redis.call('DEL', ARGV[1])
if deleted == 1 then
    return 1
else
    return 0
end
"""

# ARGV[1] = jti_key, ARGV[2] = ttl_seconds
JTI_REPLAY_LUA = """
local exists = redis.call('EXISTS', ARGV[1])
if exists == 1 then
    return 0
else
    redis.call('SET', ARGV[1], '1', 'EX', ARGV[2])
    return 1
end
"""


class DPoPMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette middleware for validating Demonstrating Proof-of-Possession (DPoP).

    This middleware enforces sender-constraint by verifying that the client holds the
    private key corresponding to the public key bound to the Access Token. It handles
    signature verification, protocol binding (HTM/HTU), token binding (ATH),
    nonce-based freshness, and replay protection.
    """

    # Standardize the prefix as a class constant
    NONCE_PREFIX = "dpop_nonce:"
    NONCE_TTL = 300  # 5 minutes is standard for DPoP nonces

    def __init__(
        self, app, authz_public_key: str, allowed_issuer: str, leeway_seconds: int = 30
    ):
        """
        Initializes the DPoP middleware.

        Args:
            app: The Starlette/FastAPI application instance.
        """
        super().__init__(app)
        self.authz_key = jwk.import_key(authz_public_key, key_type="EC")
        self.allowed_issuer = allowed_issuer
        self.leeway_seconds = leeway_seconds

    def _get_nonce_key(self, nonce: str) -> str:
        """Helper to ensure key consistency."""
        return f"{self.NONCE_PREFIX}{nonce}"

    def register_lua_scripts(self, redis_pool: redis.Redis):
        self.nonce_script = redis_pool.register_script(NONCE_CHECK_LUA)
        self.jti_replay_script = redis_pool.register_script(JTI_REPLAY_LUA)

    async def dispatch(self, request: Request, call_next):
        """
        Intercepts requests to validate DPoP proofs for 'DPoP' authorization schemes.

        Args:
            request: The incoming Starlette Request.
            call_next: The next middleware or route handler in the chain.

        Returns:
            Response: The resulting HTTP response or a 401 JSONResponse challenge.

        Raises:
            HTTPException: 401 error if validation fails and no nonce challenge is issued.
        """

        auth_header = request.headers.get("Authorization")
        dpop_jwt = request.headers.get("DPoP")
        redis_cache: redis.Redis = request.app.state.redis

        if not auth_header or not auth_header.startswith("DPoP "):
            return await call_next(request)

        if not dpop_jwt:
            return await self.handle_nonce_challenge(redis_cache, "DPoP header missing")

        try:
            # 1. DPoP Proof Phase
            proof = self.verify_and_parse_proof(dpop_jwt)

            # 2. Nonce Handshake Phase
            if not await self.check_nonce_atomic(redis_cache, proof.payload.nonce):
                return await self.handle_nonce_challenge(
                    redis_cache, "Nonce already used or invalid"
                )

            # 3. Access Token Phase
            access_token = auth_header.split(" ")[1]
            at_claims = self.verify_and_parse_access_token(access_token)

            # 4. Binding Phase
            self.validate_protocol_bindings(proof, at_claims, access_token, request)

            # 5. Replay Protection
            if not await self.is_not_replay(redis_cache, proof.payload.jti):
                raise exceptions.DPoPReplayError("Proof JTI already used or in-flight")

            request.state.user_sub = at_claims.sub
            return await call_next(request)

        except exceptions.DPoPClockSkewError as e:
            return await self.handle_nonce_challenge(redis_cache, str(e))
        except exceptions.DPoPError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=e.detail
            )
        # 3. Handle Cryptographic/JWT failures from joserfc
        except joserfc_errors.BadSignatureError as e:
            # log.error(f"JWT Verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token signature or format",
            )
        except (
            exceptions.DPoPBindingError,
            exceptions.DPoPReplayError,
            exceptions.DPoPKeyMismatchError,
        ) as e:
            # These are all 401 Unauthorized issues
            # We ensure the 'detail' from the custom exception is passed through
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=getattr(e, "detail", str(e)),
            )
        except exceptions.DPoPError as e:
            # Generic catch-all for other DPoP issues
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=getattr(e, "detail", "DPoP validation failed"),
            )
        except ValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.errors(),
            )
        except (exceptions.DPoPBindingError, exceptions.DPoPReplayError) as e:
            # All binding (htu, htm, iss, ath) and replay issues go here
            raise HTTPException(status_code=401, detail=e.detail)

    # --- Atomic Logic Methods ---

    def verify_and_parse_access_token(self, token: str) -> DPoPAccessTokenPayload:
        """
        Verifies the signature of the Bearer Access Token using the Authorization Server's key.

        Args:
            token: The raw Access Token string from the Authorization header.

        Returns:
            DPoPAccessTokenPayload: Validated Pydantic model containing claims like 'cnf'.

        Raises:
            JoseError: If signature verification or standard claim validation (exp/iss) fails.
        """
        decoded = jwt.decode(token, self.authz_key)
        claims = DPoPAccessTokenPayload(**decoded.claims)
        claims.check_expiration(self.leeway_seconds)  # also checks exp
        claims.verify_iss(self.allowed_issuer)  # checks iss
        return claims

    def verify_and_parse_proof(self, proof_jwt: str) -> DPoPProof:
        """
        Verifies the DPoP proof's signature using the public key embedded in its own header.

        This ensures the sender possesses the private key. Pydantic model validation
        further enforces iat, htu, and htm requirements.

        Args:
            proof_jwt: The raw JWT string from the 'DPoP' header.

        Returns:
            DPoPProof: Validated Pydantic model containing the proof header and payload.

        Raises:
            DPoPBindingError: If the 'jwk' is missing from the header.
            JoseError: If the proof signature is invalid.
        """
        # DPoP JWTs are always ASCII-safe
        token_bytes = proof_jwt.encode("ascii")
        member = jws.extract_compact(token_bytes)
        jwk_data = member.headers().get("jwk")
        if not jwk_data:
            raise exceptions.DPoPBindingError("DPoP header missing 'jwk'")

        # Verify signature using the key inside the header
        proof_key: jwk.ECKey = jwk.import_key(jwk_data, key_type="EC")
        verified = jwt.decode(proof_jwt, proof_key)

        # Pydantic handles iat/htu/iss validation here automatically
        return DPoPProof(
            header=DPoPProofHeader.model_validate(verified.header),
            payload=DPoPProofPayload.model_validate(verified.claims),
        )

    def validate_protocol_bindings(
        self,
        proof: DPoPProof,
        at: DPoPAccessTokenPayload,
        access_token: str,
        request: Request,
    ):
        """
        Validates the cryptographic and protocol-level bindings between the proof and the request.

        Performs three critical checks:
        1. Key Binding: Ensures the JWK in the proof matches the 'jkt' bound to the Access Token.
        2. Token Binding: Ensures the 'ath' claim matches the hash of the provided Access Token.
        3. Protocol Binding: Ensures 'htm' and 'htu' match the current request.

        Args:
            proof: The validated DPoP proof model.
            at: The validated Access Token payload model.
            access_token: The raw Access Token string (used for hash verification).
            request: The current Starlette Request object.

        Raises:
            DPoPBindingError: If any of the bindings (Key, Token, or Protocol) fail.
        """
        # A) Key Binding (cnf.jkt == thumbprint(jwk))
        retrieved_public_key = convert_to_joserfc_key(proof.header.jwk)
        proof_jkt = thumbprint(retrieved_public_key, "sha256")
        at.verify_binding(proof_jkt)

        # B) Token Binding (ath == hash(access_token))
        expected_ath = self._compute_ath(access_token)
        if proof.payload.ath != expected_ath:
            raise exceptions.DPoPBindingError("ath claim mismatch")

        # C) Protocol Binding (htm/htu)
        current_htu = str(request.url).split("?")[0]
        if proof.payload.htm != request.method or str(proof.payload.htu) != current_htu:
            raise exceptions.DPoPBindingError("htm/htu binding mismatch")

    # --- Infrastructure Helpers ---

    def _compute_ath(self, token: str) -> str:
        """
        Computes the Access Token Hash (ath) as required by RFC 9449.

        Args:
            token: The ASCII Access Token string.

        Returns:
            str: Base64URL encoded SHA-256 hash of the token without padding.
        """
        digest = hashlib.sha256(token.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    async def check_nonce_atomic(
        self, redis_cache: redis.Redis, nonce: Optional[str]
    ) -> bool:
        """
        Checks if the provided nonce exists in the server-side cache.

        Args:
            redis_cache: The Redis client instance.
            nonce: The nonce string extracted from the DPoP payload.

        Returns:
            bool: True if the nonce is valid, False otherwise.
        """
        if not nonce:
            return False

        nonce_key = self._get_nonce_key(nonce)

        # eval args: script, num_keys, *keys_and_args
        # We pass 0 for num_keys and use ARGV for the key name
        # (or 1 if you want to follow Redis Cluster key-slot conventions)
        result = await redis_cache.eval(NONCE_CHECK_LUA, 0, nonce_key)

        return result == 1

    async def is_not_replay_atomic(self, redis_cache: redis.Redis, jti: str) -> bool:
        """
        Checks the JTI against the replay cache to prevent replay attacks.
        Implements JTI Replay Protection.
        Returns True if the JTI is new and has been recorded.
        Returns False if the JTI has been seen before.
        Args:
            redis_cache: The Redis client instance.
            jti: The unique identifier for the DPoP proof.

        Returns:
            bool: True if the JTI has not been seen before, False if it's a replay.
        """
        jti_key = f"dpop_jti:{jti}"

        result = await redis_cache.eval(JTI_REPLAY_LUA, 0, jti_key, self.NONCE_TTL)

        return result == 1

    async def handle_nonce_challenge(
        self, redis_cache: redis.Redis, detail: str
    ) -> JSONResponse:
        """
        Generates a new nonce and returns a 401 challenge response.

        Args:
            redis_cache: The Redis client instance.
            detail: Error description to include in the JSON response.

        Returns:
            JSONResponse: A 401 response containing the DPoP-Nonce header.
        """
        new_nonce = secrets.token_urlsafe(32)
        key = self._get_nonce_key(new_nonce)
        await redis_cache.set(key, "1", ex=self.NONCE_TTL)
        # Return RFC 9449 compliant headers
        return JSONResponse(
            status_code=401,
            content={"error": "use_dpop_nonce", "error_description": detail},
            headers={
                "DPoP-Nonce": new_nonce,
                "WWW-Authenticate": f'DPoP error="use_dpop_nonce", error_description="{detail}"',
            },
        )
