import hashlib
import base64
from fastapi import FastAPI, Request, Header, HTTPException, status, Response
from joserfc import jwt, jwk, jws
from joserfc.errors import JoseError

app = FastAPI()

# Keycloak/IDP Public Key (Ideally fetched via OIDC well-known JWKS)
# Example: jwk.import_key({"kty": "RSA", "n": "...", "e": "..."})
IDP_PUBLIC_KEY = jwk.import_key("your-idp-public-key-here")

def calculate_jkt(jwk_obj: jwk.Key) -> str:
    """
    Computes the JWK Thumbprint (RFC 7638). 
    joserfc provides thumbprint methods directly on the Key object.
    """
    return jwk_obj.thumbprint()

@app.get("/api/data")
async def protected_resource(
    request: Request, 
    response: Response,
    authorization: str = Header(None), 
    dpop: str = Header(None)
):
    # 1. Scheme Check
    if not authorization or not authorization.startswith("DPoP "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "DPoP token required.")
    
    if not dpop:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "DPoP header missing.")

    access_token = authorization.split(" ", 1)[1]

    try:
        # 2. Verify Access Token (Issued by Keycloak)
        # Verify the signature and standard claims (exp, iss, etc.)
        at_token = jwt.decode(access_token, IDP_PUBLIC_KEY)
        at_claims = at_token.claims
        
        # 3. Verify DPoP Proof (Signed by the Client)
        # Extract the header to get the embedded JWK
        raw_dpop = jws.extract_compact(dpop.encode())
        client_jwk_dict = raw_dpop.protected.get("jwk")
        
        if not client_jwk_dict:
            raise HTTPException(401, "JWK missing in DPoP header")

        # Import the client's public key from the header
        client_public_key = jwk.import_key(client_jwk_dict)
        
        # Verify DPoP Proof signature and typ
        if raw_dpop.protected.get("typ") != "dpop+jwt":
            raise HTTPException(401, "Invalid DPoP type")
            
        dpop_token = jwt.decode(dpop, client_public_key)
        dpop_claims = dpop_token.claims

        # 4. Access Token Hash (ath) Check
        # RFC 9449: Resource servers MUST verify the 'ath' claim matches the access token
        expected_ath = base64.urlsafe_b64encode(
            hashlib.sha256(access_token.encode()).digest()
        ).decode().replace("=", "")
        
        if dpop_claims.get("ath") != expected_ath:
            raise HTTPException(401, "DPoP 'ath' claim mismatch")

        # 5. Cryptographic Binding (cnf match)
        # Compare thumbprint of the client's key to the 'jkt' in the access token
        expected_jkt = at_claims.get("cnf", {}).get("jkt")
        actual_jkt = calculate_jkt(client_public_key)

        if not expected_jkt or actual_jkt != expected_jkt:
            raise HTTPException(401, "Token binding (jkt) validation failed.")

        # 6. Target Verification (HTM/HTU)
        if dpop_claims.get("htm") != request.method:
            raise HTTPException(401, "HTTP Method mismatch")
            
        # Strip query and fragment for strict HTU check
        current_url = str(request.url).split('?')[0].split('#')[0]
        if dpop_claims.get("htu") != current_url:
            raise HTTPException(401, f"HTTP URL mismatch. Expected {current_url}")

        # 7. Nonce and Replay Prevention (Conceptual)
        # In production, check dpop_claims.get("jti") against a Redis 'used' list
        # and verify 'iat' (issued at) is within a small window (e.g., 60 seconds).

    except (JoseError, ValueError) as e:
        raise HTTPException(401, f"Security Validation Failed: {str(e)}")

    return {
        "status": "success",
        "user_id": at_claims.get("sub"),
        "message": "Access granted via sender-constrained token."
    }