"""BFF Token Handler — FastAPI application.

Routes:
  GET  /login        → Redirect to KeyCloak PKCE auth URL
  GET  /callback     → Exchange code, store session, set HttpOnly cookie
  POST /logout       → Delete session, clear cookie
  GET  /me           → Return user info from current session
  ANY  /proxy/{path} → Authenticated reverse proxy to AssetService
"""

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from bff_token_handler.auth.oauth import (
    TokenSet,
    build_auth_url,
    exchange_code,
    generate_pkce_pair,
    introspect_token,
)
from bff_token_handler.proxy.reverse_proxy import proxy_request
from keycloak import KeycloakOpenID, pkce_utils
from bff_token_handler.session.redis_store import (
    SessionStore,
    CodeVerifierStore,
    RedisSession,
    get_session_store,
    get_code_verifier_store,
    get_redis_session,
)
from bff_token_handler.settings import settings

# --- Temporary in-memory store for PKCE state/verifier (per-request) ---
# In production use Redis with short TTL; fine for demo.
_pkce_cache: dict[str, str] = {}  # state -> code_verifier


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_session = await get_redis_session()
    app.state.redis_session = redis_session
    await redis_session.connect()

    session_store = await get_session_store(redis_client=redis_session.redis)
    app.state.sesson_store = session_store

    verifier_store = await get_code_verifier_store(redis_client=redis_session.redis)
    app.state.verifier_store = verifier_store

    yield
    await redis_session.disconnect()


# Define specifically allowed origins
origins = [
    "http://localhost:4200",  # Angular Default
    "http://127.0.0.1:4200",
    "http://rustfs:9000",
]


app = FastAPI(
    title="BFF Token Handler",
    description="Secure Backend-for-Frontend proxy using OAuth2 PKCE + DPoP",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,  # REQUIRED for HttpOnly Cookies
    allow_methods=["*"],  # Allows GET, POST, OPTIONS, etc.
    allow_headers=["*"],  # Allows DPoP, Authorization, etc.
    # expose_headers=["DPoP"],  # If you need Angular to read DPoP headers
)


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------


@app.get("/login", summary="Initiate OAuth2 PKCE login flow")
async def login(request: Request):
    """Redirect the browser to the KeyCloak authorization endpoint."""
    code_verifier_store: CodeVerifierStore = request.app.state.verifier_store
    state = secrets.token_urlsafe(16)
    code_verifier, code_challenge, code_challenge_method = generate_pkce_pair()
    # store verifier keyed by state
    code_verifier_store.create_pkce(state, 300, code_verifier)
    auth_url = build_auth_url(
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )
    return RedirectResponse(auth_url)


@app.get("/callback", summary="Handle OAuth2 authorization code callback")
async def callback(request: Request, code: str, state: str):
    """Exchange the authorization code for tokens and establish a session."""
    session_store: SessionStore = request.app.state.session_store
    code_verifier_store: CodeVerifierStore = request.app.state.verifier_store
    code_verifier: str = await code_verifier_store.get_pkce(state=state)
    if not code_verifier:
        return JSONResponse({"detail": "Invalid or expired state"}, status_code=400)

    token_set: TokenSet = await exchange_code(code=code, code_verifier=code_verifier)
    session_id = await session_store.create(token_set)

    response = RedirectResponse(url="/")
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        httponly=True,
        samesite="strict",
        secure=False,  # Set True in production with HTTPS
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    return response


@app.post("/logout", summary="Terminate the current session")
async def logout(request: Request):
    """Delete the server-side session and clear the browser cookie."""
    session_id = request.cookies.get(settings.session_cookie_name)
    session_store: SessionStore = request.app.state.session_store
    if session_id:
        await session_store.delete(session_id)

    response = JSONResponse({"detail": "Logged out"})
    response.delete_cookie(key=settings.session_cookie_name, path="/")
    return response


@app.get("/me", summary="Return current user info from session")
async def me(request: Request):
    """Return the authenticated user's identity claims."""
    session_id = request.cookies.get(settings.session_cookie_name)
    session_store: SessionStore = request.app.state.session_store
    if not session_id:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    token_set = await session_store.get(session_id)
    if not token_set:
        return JSONResponse({"detail": "Session expired"}, status_code=401)

    user_info = await introspect_token(token_set.access_token)
    return JSONResponse(user_info)


# ---------------------------------------------------------------------------
# Proxy catch-all — forward /proxy/* to AssetService
# ---------------------------------------------------------------------------


@app.api_route(
    "/proxy/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    summary="Authenticated reverse proxy to AssetService",
)
async def proxy(request: Request, path: str):
    """Forward authenticated requests to the AssetService with DPoP tokens."""
    return await proxy_request(request, downstream_path=path)
