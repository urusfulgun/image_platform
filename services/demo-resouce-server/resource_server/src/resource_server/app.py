import hashlib
import base64
import json
from fastapi import FastAPI, Request, Header, HTTPException, status
from joserfc import jwt, jwk
from joserfc.errors import JoseError

app = FastAPI()

# In a real scenario, this would be the public key from your Authorization Server
IDP_PUBLIC_KEY = "your-idp-public-key-here"

def calculate_jkt(jwk_dict: dict) -> str:
    """
    Computes the JWK Thumbprint (RFC 7638) for the 'cnf' claim comparison.
    Standardized JWK thumbprints only use required fields in lexicographic order.
    """
    # For RSA: e, kty, n. For EC: crv, kty, x, y.
    # This is a simplified helper; authlib has built-in tools for this.
    required_keys = {
        "RSA": ["e", "kty", "n"],
        "EC": ["crv", "kty", "x", "y"],
        "OKP": ["crv", "kty", "x"]
    }
    kty = jwk_dict.get("kty")
    relevant_data = {k: jwk_dict[k] for k in required_keys.get(kty, [])}
    json_data = json.dumps(relevant_data, separators=(",", ":"), sort_keys=True)
    
    hash_obj = hashlib.sha256(json_data.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(hash_obj).decode("utf-8").replace("=", "")

@app.get("/api/data")
async def protected_resource(
    request: Request, 
    authorization: str = Header(None), 
    dpop: str = Header(None)
):
    # 1. Check for DPoP Scheme and Header Presence
    if not authorization or not authorization.startswith("DPoP "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid authorization scheme. DPoP required."
        )
    
    if not dpop:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="DPoP header missing."
        )

    access_token = authorization.split(" ", 1)[1]

    try:
        # 2. Verify Access Token (Issued by the IDP)
        # The 'at_claims' should contain the 'cnf' (confirmation) claim
        # at_claims = jwt.decode(access_token, IDP_PUBLIC_KEY)
        at_token: jwt.Token = jwt.decode(access_token, IDP_PUBLIC_KEY)
        at_header: jwt.Header = at_token.header
        at_claims: jwt.Claims = at_token.claims
        
        # 3. Verify DPoP Proof (Signed by the Client)
        # We extract the JWK from the DPoP JWT header itself to verify the signature
        dpop_header = jwt.get_unverified_header(dpop)
        # dpop_header = jwt.
        client_public_key = dpop_header.get("jwk")
        
        if not client_public_key:
            raise HTTPException(status_code=401, detail="JWK missing in DPoP header")

        # Verify the proof signature using the key the client provided
        dpop_claims = jwt.decode(dpop, client_public_key)

        # 4. Cryptographic Binding Check (The 'cnf' match)
        # Does the key used for this proof match the key bound to the access token?
        expected_jkt = at_claims.get("cnf", {}).get("jkt")
        actual_jkt = calculate_jkt(client_public_key)

        if not expected_jkt or actual_jkt != expected_jkt:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Token binding validation failed."
            )

        # 5. Target Verification (HTM/HTU)
        # Ensures the proof wasn't intercepted and replayed against a different endpoint
        if dpop_claims.get("htm") != request.method:
            raise HTTPException(status_code=401, detail="HTM mismatch")
            
        if dpop_claims.get("htu") != str(request.url).split('?')[0]: # Strip query params per spec
            raise HTTPException(status_code=401, detail="HTU mismatch")

        # 6. Nonce Check
        provided_nonce = dpop_claims.get("nonce")
        nonce_key = f"dpop_nonce:{provided_nonce}"
        
        # Check if nonce exists in Redis
        if not provided_nonce or not await cache.exists(nonce_key):
            # Generate a fresh nonce for the client to use in the retry
            fresh_nonce = await create_new_nonce()
            
            # RFC 9449: Return 401 with the DPoP-Nonce header
            response.headers["DPoP-Nonce"] = fresh_nonce
            raise HTTPException(
                status_code=401, 
                detail="Invalid or expired DPoP nonce. Please retry with the provided nonce."
            )

        # 7. Prevent Replay Attack
        # Once a nonce is used, it MUST be invalidated immediately.

    except JoseError as e:
        raise HTTPException(status_code=401, detail=f"JWT Verification Error: {str(e)}")

    return {
        "status": "success",
        "user": at_claims.get("sub"),
        "data": "This is proof-bound data."
    }