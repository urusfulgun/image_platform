# bff.py
import base64
import hashlib
import json
import secrets
import time
import uuid
import httpx
import jwt
from fastapi import Cookie, FastAPI, Request, Response, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from keycloak import KeycloakOpenID, pkce_utils
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import redis.asyncio as redis

app = FastAPI(title="BFF - PKCE & DPoP Gateway")


# Define specifically allowed origins
origins = [
    "http://localhost:4200",  # Angular Default
    "http://127.0.0.1:4200",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,     # REQUIRED for HttpOnly Cookies
    allow_methods=["*"],        # Allows GET, POST, OPTIONS, etc.
    allow_headers=["*"],        # Allows DPoP, Authorization, etc.
    expose_headers=["DPoP"],    # If you need Angular to read DPoP headers
)


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

# Redis setup (Assume redis is available at this hostname)
redis_client = redis.from_url("redis://redis:6379/0", decode_responses=True)


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

    # Generate a temporary flow ID to link the callback to the verifier
    flow_id = str(uuid.uuid4())
    await redis_client.setex(f"pkce:{flow_id}", 300, verifier)

    # Store verifier in a secure session/cookie (omitted for brevity)
    auth_url = keycloak_openid.auth_url(
        redirect_uri="http://localhost:8000/callback",
        scope="openid",
        state=flow_id,
        code_challenge=challenge,
        code_challenge_method=code_challenge_method,
    )
    resp = RedirectResponse(auth_url)
    return resp


@app.get("/callback")
async def callback(code: str, state: str):
    # 1. Retrieve the PKCE verifier stored during the initial /login
    verifier = await redis_client.get(f"pkce:{state}")
    if not verifier:
        raise HTTPException(
            status_code=400, detail="Invalid session or expired PKCE verifier"
        )

    # 2. Define the Token Endpoint for the DPoP proof
    # Keycloak Token Exchange with DPoP
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

        # 6. Create Opaque Session
        session_id = secrets.token_urlsafe(32)
        # Store the tokens in Redis (TTL matched to refresh token or arbitrary 1 hour)
        await redis_client.setex(
            f"session:{session_id}", 3600, json.dumps(token_response)
        )
        await redis_client.delete(f"pkce:{state}")  # Cleanup

        # 7. Return Opaque Token via Secure Cookie
        response = RedirectResponse(
            url="http://localhost:8000/docs"
        )  # Redirect to UI for example "http://localhost:3000/dashboard"
        response.set_cookie(
            key="bff_session",
            value=session_id,
            httponly=True,
            secure=False,  # Set to False only for local non-https dev # MUST be False for http://localhost dev
            samesite="lax",
            max_age=3600,
        )

        return response

    except Exception as e:
        # If Keycloak returns an error (like invalid DPoP), it will be caught here
        raise HTTPException(status_code=400, detail=str(e))


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_to_rs(
    path: str,
    request: Request,
    bff_session: str | None = Cookie(None),
):
    if not bff_session:
        raise HTTPException(status_code=401, detail="No session cookie found. Please /login first.")
    # 1. Lookup session in Redis
    session_data_raw = await redis_client.get(f"session:{bff_session}")
    if not session_data_raw:
        raise HTTPException(status_code=401, detail="Session expired")
    
    session_data = json.loads(session_data_raw)
    access_token = session_data.get("access_token")

    # 2. Proxy request to Resource Server with DPoP
    target_url = f"{RS_URL}/files/{path}"
    dpop_proof = create_dpop_proof(request.method, target_url, access_token)

    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"DPoP {access_token}",
            "DPoP": dpop_proof,
        }
        
        proxy_req = client.build_request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=await request.body(),
        )
        rp_resp = await client.send(proxy_req)

    return Response(content=rp_resp.content, status_code=rp_resp.status_code, headers=dict(rp_resp.headers))
