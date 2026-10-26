"""BFF Token Handler — FastAPI application.

Routes:
  GET  /login        → Redirect to KeyCloak PKCE auth URL
  GET  /callback     → Exchange code, store session, set HttpOnly cookie
  POST /logout       → Delete session, clear cookie
  GET  /me           → Return user info from current session
  ANY  /proxy/{path} → Authenticated reverse proxy to AssetService
"""

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from keycloak import KeycloakAuthenticationError, KeycloakOpenID, pkce_utils
from shared_core.dto.key_pair import KeyPair
from shared_core.schemas.responses.profile import UserProfileResponse
from shared_core.schemas.security.token_set import TokenSet
from shared_core.schemas.security.user_session import UserSession

from bff_token_handler.auth.dpop import decode_jwt_token, generate_ec_key_pair
from bff_token_handler.auth.oauth import (
    build_auth_url,
    exchange_code,
    generate_pkce_pair,
    get_keycloak_openid,
    introspect_token,
    revoke_token_at_keycloak,
)
from bff_token_handler.proxy.reverse_proxy import proxy_request
from bff_token_handler.session.redis_store import (
    CodeVerifierStore,
    RedisSession,
    SessionStore,
    get_code_verifier_store,
    get_redis_session,
    get_session_store,
)
from bff_token_handler.settings import keycloak_config, settings

# --- Temporary in-memory store for PKCE state/verifier (per-request) ---
# In production use Redis with short TTL; fine for demo.
_pkce_cache: dict[str, str] = {}  # state -> code_verifier

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_session = await get_redis_session()
    app.state.redis_session = redis_session
    await redis_session.connect()

    session_store = await get_session_store(redis_client=redis_session.redis)
    app.state.session_store = session_store

    app.state.ec_key_pair = generate_ec_key_pair()

    verifier_store = await get_code_verifier_store(redis_client=redis_session.redis)
    app.state.verifier_store = verifier_store
    keycloak_openid = await get_keycloak_openid(keycloak_config=keycloak_config)
    app.state.keycloak_openid = keycloak_openid

    yield
    await redis_session.disconnect()


# Define specifically allowed origins
origins = [
    "http://localhost:80",  # Angular Default
    "http://127.0.0.1:80",
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

@app.get("/health", tags=["ops"])
async def health():
    return JSONResponse({"status": "ok"})

# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------


@app.get("/login", summary="Initiate OAuth2 PKCE login flow")
async def login(request: Request):
    """Redirect the browser to the KeyCloak authorization endpoint."""
    code_verifier_store: CodeVerifierStore = request.app.state.verifier_store
    keycloak_openid: KeycloakOpenID = request.app.state.keycloak_openid
    state = secrets.token_urlsafe(16)
    code_verifier, code_challenge, code_challenge_method = generate_pkce_pair()
    # store verifier keyed by state
    await code_verifier_store.create_pkce(state, 300, code_verifier)
    auth_url = build_auth_url(
        keycloak_openid=keycloak_openid,
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )
    return RedirectResponse(auth_url)


@app.get(
    "/authorization-code/callback", summary="Handle OAuth2 authorization code callback"
)
async def callback(request: Request, code: str, state: str):
    """Exchange the authorization code for tokens and establish a session."""
    session_store: SessionStore = request.app.state.session_store
    code_verifier_store: CodeVerifierStore = request.app.state.verifier_store
    key_pair: KeyPair = request.app.state.ec_key_pair
    code_verifier: str = await code_verifier_store.get_pkce(state=state)
    log.info(f"CODE: {code} VERIFIER: {code_verifier}")
    if code_verifier is None:
        return JSONResponse({"detail": "Invalid or expired state"}, status_code=400)

    token_set: TokenSet = await exchange_code(
        code=code,
        code_verifier=code_verifier,
        key_pair=key_pair,
    )

    session_id = await session_store.create(token_set, key_pair)

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


@app.post("/logout", summary="Terminate the current session and revoke tokens")
async def logout(request: Request):
    session_id = request.cookies.get(settings.session_cookie_name)
    session_store: SessionStore = request.app.state.session_store

    if not session_id:
        return JSONResponse({"detail": "Already logged out"}, status_code=200)

    # 1. Retrieve tokens and DPoP key from the secure store
    user_session: UserSession = await session_store.get(session_id)
    token_set: TokenSet = user_session.token_set
    key_pair: KeyPair = user_session.key_pair

    if user_session:
        # 2. Revoke the Refresh Token at Keycloak (DPoP bound) (leverage DPoP private key)
        # This prevents anyone from using the stolen refresh token later.
        # await revoke_token_at_keycloak(
        #     refresh_token=token_set.refresh_token,
        #     dpop_key_pair=key_pair,
        # )

        # 3. Delete the server-side session
        await session_store.delete(session_id)

    # 4. Prepare the OIDC End Session URL for the frontend
    # Including id_token_hint prevents the Keycloak "Do you want to logout?" prompt.
    keycloak_logout_url = (
        f"{settings.keycloak_url}/realms/{settings.realm}/protocol/openid-connect/logout"
        f"?id_token_hint={token_set.id_token}"
        f"&post_logout_redirect_uri={settings.frontend_url}"
    )

    response = JSONResponse(
        {"detail": "Logged out locally and revoked", "logoutUrl": keycloak_logout_url}
    )

    # 5. Clear the HttpOnly session cookie
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",  # or "strict"
        secure=True,
    )

    return response


@app.get(
    "/me",
    summary="Return current user info from session",
    response_model=UserProfileResponse,
)
async def me(request: Request):
    """Return the authenticated user's identity claims."""
    session_id = request.cookies.get(settings.session_cookie_name)
    session_store: SessionStore = request.app.state.session_store
    if not session_id:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    user_session: UserSession = await session_store.get(session_id)
    if not user_session.token_set:
        return JSONResponse({"detail": "Session expired"}, status_code=401)

    token_set: TokenSet = user_session.token_set
    key_pair: KeyPair = user_session.key_pair
    try:
        user_info_token = await introspect_token(key_pair, token_set.access_token)
    except KeycloakAuthenticationError as e:
        return JSONResponse({"detail": f"Not authenticated extra: {e.error_message}"}, status_code=e.response_code)
    # Userinfo is plain JSON unless the client has signed userinfo responses enabled
    if isinstance(user_info_token, dict):
        claims = user_info_token
    else:
        _, claims, _ = decode_jwt_token(user_info_token)
    user_info = UserProfileResponse.model_validate(claims)
    return JSONResponse({"id_token": user_info.model_dump(mode="json")})


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
    session_id = request.cookies.get(settings.session_cookie_name)
    session_store: SessionStore = request.app.state.session_store
    if not session_id:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    user_session: UserSession = await session_store.get(session_id)
    if not user_session.token_set:
        return JSONResponse({"detail": "Session expired"}, status_code=401)
    return await proxy_request(request, downstream_path=path)
