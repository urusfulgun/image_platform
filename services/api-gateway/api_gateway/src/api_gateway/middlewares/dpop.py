import time
import base64
import hashlib
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from joserfc import jwt, jwk
from joserfc.errors import JoseError
from api_gateway.config import settings

# Configuration (In production, load these from env)
KEYCLOAK_PUBLIC_KEY = settings.KEYCLOAK_PUBLIC_KEY
ALLOWED_ISSUER = settings.ALLOWED_ISSUER


# Define the expected claims for your environment
REQUIRED_CLAIMS = {
    "iss": ALLOWED_ISSUER,
    "aud": "api-gateway-client" # Or your specific audience
}


class DPoPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Extract Headers
        auth_header = request.headers.get("Authorization")
        dpop_proof = request.headers.get("DPoP")

        if not auth_header or not auth_header.startswith("DPoP "):
            # If your API allows public routes, skip. Otherwise, 401.
            return await call_next(request)

        try:
            # 2. Extract Access Token
            access_token = auth_header.split(" ")[1]

            # 3. Validate Access Token (JWT)
            # We check the signature, issuer, and 'cnf' claim for DPoP binding
            header_key = jwk.import_key(KEYCLOAK_PUBLIC_KEY)
            decoded_token = jwt.decode(access_token, header_key, algorithms=["RS256"])

            # Verify basic claims
            decoded_token.validate_claims(issuer=ALLOWED_ISSUER)

            # 4. DPoP Proof Validation (The 'cnf' check)
            # Access token must contain the thumbprint (jkt) of the DPoP key
            cnf = decoded_token.claims.get("cnf")
            if not cnf or "jkt" not in cnf:
                raise HTTPException(status_code=401, detail="Token is not DPoP bound")

            # 5. Validate the DPoP Proof Header itself
            # The proof is a JWT signed by the client's private key
            proof_jwt = jwt.decode(
                dpop_proof, None
            )  # Decode header first to get public key
            proof_jwk = proof_jwt.header.get("jwk")

            # Re-verify the proof signature using the JWK provided in its header
            # and verify it matches the thumbprint in the Access Token
            verified_proof = jwt.decode(dpop_proof, jwk.import_key(proof_jwk))

            # Compute thumbprint of the JWK to verify against 'cnf'
            # (Note: joserfc provides thumbprint helpers)
            jkt = jwk.thumbprint(proof_jwk, "sha256")
            if jkt != cnf["jkt"]:
                raise HTTPException(status_code=401, detail="DPoP key mismatch")

            # 6. Verify Proof Claims (htu, htm)
            # 'htu' (HTTP URL) and 'htm' (HTTP Method) must match the current request
            expected_htu = str(request.url).split("?")[0]  # Strip query params
            if (
                verified_proof.claims.get("htu") != expected_htu
                or verified_proof.claims.get("htm") != request.method
            ):
                raise HTTPException(
                    status_code=401, detail="DPoP proof claims mismatch"
                )

            # 7. Success: Attach 'sub' to request state
            request.state.user_sub = decoded_token.claims.get("sub")

        except JoseError as e:
            raise HTTPException(status_code=401, detail=f"Invalid Token: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=401, detail="Authentication failed")

        return await call_next(request)
