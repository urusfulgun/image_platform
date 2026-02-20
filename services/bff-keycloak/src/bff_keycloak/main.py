# bff.py
import base64
import hashlib
import json
import secrets
import time
from typing import Annotated
import uuid
import httpx
import jwt
from fastapi import Cookie, Depends, FastAPI, Request, Response, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from keycloak import KeycloakOpenID, pkce_utils
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import BaseModel, ConfigDict, Field, field_validator
import redis.asyncio as redis

class PresignedUrlRequestBFF(BaseModel):
    # Matches Angular's camelCase exactly
    file_name: str = Field(..., alias="fileName")

    # This allows the model to accept the alias but still let you 
    # access it via .file_name in your Python code
    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True
    )

class PresignedUrlRequest(BaseModel):
    # Matches { "fileName": "..." } from Angular
    file_name: str = Field(alias="fileName")

    @field_validator("file_name")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Filename cannot be empty")
        # Basic security: prevent path traversal
        if "/" in v or "\\" in v:
            raise ValueError("Filename cannot contain directory paths")
        return v


class PresignedUrlResponse(BaseModel):
    url: str

app = FastAPI(title="BFF - PKCE & DPoP Gateway")


# Define specifically allowed origins
origins = [
    "http://localhost:4200",  # Angular Default
    "http://127.0.0.1:4200",
    "http://rustfs:9000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,  # REQUIRED for HttpOnly Cookies
    allow_methods=["*"],  # Allows GET, POST, OPTIONS, etc.
    allow_headers=["*"],  # Allows DPoP, Authorization, etc.
    expose_headers=["DPoP"],  # If you need Angular to read DPoP headers
)

http_client = httpx.AsyncClient(timeout=10.0)

async def forward_to_rs(method: str, url: str, token: str, content: bytes | None = None):
    # 1. Generate DPoP Proof for the RS target
    dpop_proof = create_dpop_proof(method, url, token)

    # 2. Prepare Clean Headers
    headers = {
        "Authorization": f"DPoP {token}",
        "DPoP": dpop_proof,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        # 3. Execute request using the pooled client
        rp_resp = await http_client.request(
            method=method,
            url=url,
            headers=headers,
            content=content
        )
        
        # 4. Clean up response headers for the browser
        # Strips hop-by-hop headers that can break proxying (like Content-Length)
        excluded = {"content-encoding", "transfer-encoding", "content-length", "connection"}
        safe_headers = {k: v for k, v in rp_resp.headers.items() if k.lower() not in excluded}

        return Response(
            content=rp_resp.content,
            status_code=rp_resp.status_code,
            headers=safe_headers
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream Resource Server error: {exc}")


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

EXCLUDED_HEADERS = ["host", "content-length", "authorization", "dpop", "cookie"]

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


async def get_rs_token(bff_session: str | None = Cookie(None)) -> str:
    if not bff_session:
        raise HTTPException(status_code=401, detail="No session found")
        
    session_data_raw = await redis_client.get(f"session:{bff_session}")
    if not session_data_raw:
        raise HTTPException(status_code=401, detail="Session expired")
    
    return json.loads(session_data_raw).get("access_token")


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
            # url="http://localhost:8000/docs"
            url="http://localhost:4200"
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
        raise HTTPException(
            status_code=401, detail="No session cookie found. Please /login first."
        )
    
    # 2. Extract Body and Validate (If it's a POST to presign)
    body_bytes = await request.body()
    
    # If the path is 'presign', we can validate the body specifically
    if path == "presign" and request.method == "POST":
        try:
            # This ensures the body is valid JSON and contains 'fileName'
            valid_data = PresignedUrlRequestBFF.model_validate_json(body_bytes)
            # You can even modify/clean the data here if needed
            body_bytes = valid_data.model_dump_json(by_alias=True).encode()
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid upload request format")

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
        # We extract necessary headers but skip 'host' and 'content-length'
        # as httpx will recalculate them for the new request.
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in EXCLUDED_HEADERS
        }

        headers.update(
            {
                "Authorization": f"DPoP {access_token}",
                "DPoP": dpop_proof,
            }
        )

        try:
            proxy_req = client.build_request(
                method=request.method,
                url=target_url,
                headers=headers,
                params=dict(request.query_params),  # Forward query strings
                content=await request.body(),
            )
            rp_resp = await client.send(proxy_req)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"RS unreachable: {exc}")
    # 5. Return Response
    # Filter out sensitive hop-by-hop headers from RS before returning to Angular
    resp_headers = {
        k: v
        for k, v in rp_resp.headers.items()
        if k.lower()
        not in [
            "content-encoding",
            "transfer-encoding",
            "content-length",
        ]
    }

    return Response(
        content=rp_resp.content,
        status_code=rp_resp.status_code,
        headers=resp_headers,
    )

@app.post("/presign", response_model=PresignedUrlResponse)
async def get_upload_link(
    data: PresignedUrlRequestBFF, 
    token: Annotated[str, Depends(get_rs_token)]
):
    """BFF Endpoint: Validate filename and request upload link from RS."""
    # We explicitly point to the RS /presign route
    target_url = f"{RS_URL}/api/presign"
    
    return await forward_to_rs(
        method="POST",
        url=target_url,
        token=token,
        content=data.model_dump_json(by_alias=True).encode()
    )

@app.get("/files/{key:path}")
async def get_file_link(
    key: str, 
    token: Annotated[str, Depends(get_rs_token)]
):
    """BFF Endpoint: Request a download link for a specific key."""
    target_url = f"{RS_URL}/files/{key}"
    
    return await forward_to_rs(
        method="GET",
        url=target_url,
        token=token
    )
