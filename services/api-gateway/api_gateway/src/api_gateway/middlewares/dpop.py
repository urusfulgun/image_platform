import time
import base64
import hashlib
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from joserfc import jwt, jwk
from joserfc.jwk import thumbprint
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
        auth_header = request.headers.get("Authorization")
        dpop_proof = request.headers.get("DPoP")

        if not auth_header or not auth_header.startswith("DPoP "):
            return await call_next(request)

        try:
            access_token = auth_header.split(" ")[1]
            key = jwk.import_key(KEYCLOAK_PUBLIC_KEY)

            # 1. Decode and verify the Access Token signature
            # joserfc returns a Token object
            token = jwt.decode(access_token, key)
            
            # 2. Manual Claim Validation in joserfc
            now = int(time.time())
            claims = token.claims
            
            # Basic validation: expiry and issuer
            if claims.get("iss") != ALLOWED_ISSUER:
                raise HTTPException(status_code=401, detail="Invalid issuer")
            if claims.get("exp", 0) < now:
                raise HTTPException(status_code=401, detail="Token expired")

            # 3. DPoP Binding check (cnf claim)
            cnf = claims.get("cnf")
            if not cnf or "jkt" not in cnf:
                raise HTTPException(status_code=401, detail="Token is not DPoP bound")

            # 4. Decode the Proof Header to get the ephemeral Public Key (JWK)
            # We don't verify the signature yet; we just extract the key
            unverified_proof = jwt.decode(dpop_proof, None)
            proof_jwk_dict = unverified_proof.header.get("jwk")
            if not proof_jwk_dict:
                raise HTTPException(status_code=401, detail="DPoP proof missing JWK header")
            
            proof_jwk = jwk.import_key(proof_jwk_dict)

            # 5. Verify the DPoP Proof signature with its own embedded key
            verified_proof = jwt.decode(dpop_proof, proof_jwk)
            
            # 6. Verify thumbprint (jkt) matches the Access Token cnf
            # In joserfc, thumbprint is a standalone utility
            jkt = thumbprint(proof_jwk, "sha256")
            if jkt != cnf["jkt"]:
                raise HTTPException(status_code=401, detail="DPoP key mismatch")

            # 7. Verify htu and htm
            current_htu = str(request.url).split('?')[0]
            if verified_proof.claims.get("htu") != current_htu or \
               verified_proof.claims.get("htm") != request.method:
                raise HTTPException(status_code=401, detail="DPoP proof target mismatch")

            # Success: Inject into request state
            request.state.user_sub = claims.get("sub")

        except Exception as e:
            # Catching joserfc.errors.JoseError and others
            raise HTTPException(status_code=401, detail=f"Auth error: {str(e)}")

        return await call_next(request)
