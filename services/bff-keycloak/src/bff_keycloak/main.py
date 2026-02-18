# bff.py
import base64
import hashlib
import secrets
import time
import uuid
import httpx
import jwt
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import RedirectResponse
from keycloak import KeycloakOpenID, pkce_utils
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

app = FastAPI(title="BFF - PKCE & DPoP Gateway")

KEYCLOAK_BASE_URL = "http://keycloak:8080"

# Configuration
KC_CONFIG = {
    # "server_url": "https://keycloak.example.com/",
    "server_url": KEYCLOAK_BASE_URL,
    "client_id": "bff-client",
    "realm_name": "myrealm",
    "client_secret_key": "your-secret",
}
keycloak_openid = KeycloakOpenID(**KC_CONFIG)
RS_URL = "http://resource-server:8001"

# DPoP Private Key (Persistent per BFF instance)
PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
PUBLIC_KEY_JWK = {
    "kty": "EC",
    "crv": "P-256",
    "x": base64.urlsafe_b64encode(
        PRIVATE_KEY.public_key().public_numbers().x.to_bytes(32, "big")
    )
    .decode()
    .rstrip("="),
    "y": base64.urlsafe_b64encode(
        PRIVATE_KEY.public_key().public_numbers().y.to_bytes(32, "big")
    )
    .decode()
    .rstrip("="),
}


def create_dpop_proof(method: str, url: str, access_token: str = None):
    """Generates a DPoP Proof JWT."""
    header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": PUBLIC_KEY_JWK}
    payload = {
        "jti": secrets.token_hex(16),
        "htm": method.upper(),
        "htu": url.split("?")[0],
        "iat": int(time.time()),
    }
    if access_token:  # 'ath' claim required for resource access
        ath = (
            base64.urlsafe_b64encode(hashlib.sha256(access_token.encode()).digest())
            .decode()
            .rstrip("=")
        )
        payload["ath"] = ath

    return jwt.encode(payload, PRIVATE_KEY, algorithm="ES256", headers=header)


@app.get("/login")
async def login():
    # PKCE: Generate verifier and challenge
    code_challenge_method = "S256"
    verifier = pkce_utils.generate_code_verifier()
    challenge, _ = pkce_utils.generate_code_challenge(
        verifier, method=code_challenge_method
    )

    # Store verifier in a secure session/cookie (omitted for brevity)
    auth_url = keycloak_openid.auth_url(
        redirect_uri="http://localhost:8000/callback",
        scope="openid",
        state="state",
        code_challenge=challenge,
        code_challenge_method=code_challenge_method,
    )
    resp = RedirectResponse(auth_url)
    resp.set_cookie("pkce_verifier", verifier, httponly=True)
    return resp


@app.get("/callback")
async def callback(code: str, request: Request):
    # 1. Retrieve the PKCE verifier stored during the initial /login
    verifier = request.cookies.get("pkce_verifier")
    if not verifier:
        raise HTTPException(status_code=400, detail="PKCE verifier missing")

    # 2. Define the Token Endpoint for the DPoP proof
    # In Docker, this is usually http://keycloak:8080/...
    token_url = f"{KEYCLOAK_BASE_URL}/realms/myrealm/protocol/openid-connect/token"

    # 3. Generate a fresh DPoP proof for this specific POST request
    dpop_header = create_dpop_proof("POST", token_url)

    # 4. RE-INITIALIZE the client with the custom DPoP header
    # This ensures the library attaches 'DPoP: <proof>' to the outgoing call
    dynamic_client = KeycloakOpenID(
        server_url=KEYCLOAK_BASE_URL,
        client_id="bff-client",
        realm_name="myrealm",
        # client_secret_key="your-client-secret", # Required if client is confidential
        custom_headers={"DPoP": dpop_header},
    )

    try:
        # 5. Perform the exchange
        token_response = dynamic_client.token(
            grant_type="authorization_code",
            code=code,
            redirect_uri="http://localhost:8000/callback",
            code_verifier=verifier,
        )
        return token_response

    except Exception as e:
        # If Keycloak returns an error (like invalid DPoP), it will be caught here
        raise HTTPException(status_code=400, detail=str(e))


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_to_rs(path: str, request: Request):
    # 1. Safely extract the token
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").replace("DPoP ", "").strip()

    if not token:
        return Response(content="Missing Token", status_code=401)

    target_url = f"{RS_URL}/{path}"

    # 2. Generate DPoP Proof
    # Ensure this returns a valid JWT string, not None!
    dpop_proof = create_dpop_proof(request.method, target_url, token)

    if not dpop_proof:
        return Response(content="DPoP Generation Failed", status_code=500)

    async with httpx.AsyncClient() as client:
        # 3. Use a clean header dictionary
        headers = {
            "Authorization": f"DPoP {token}",  # Double check: no space if token is empty
            "DPoP": dpop_proof.strip(),  # Strip any accidental newlines
        }

        # Forward existing headers but override Auth/DPoP
        # (Be careful not to forward 'Host' header from the original request)

        proxy_req = client.build_request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=await request.body(),
        )
        rp_resp = await client.send(proxy_req)

    return Response(content=rp_resp.content, status_code=rp_resp.status_code)
