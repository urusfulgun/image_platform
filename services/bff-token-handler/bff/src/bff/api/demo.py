import base64
import hashlib
import logging
from urllib.parse import urlencode
from bff.dependencies.redis_nonce import update_redis_nonce
from bff.dependencies.session import get_bff_client
from bff.lifespans.lifespan import lifespan
from bff.service_layer.bff_manager import RedisBFFManager
from fastapi import (
    BackgroundTasks,
    Cookie,
    Depends,
    FastAPI,
    Request,
    HTTPException,
    Response,
)
from fastapi.responses import RedirectResponse
from pydantic import HttpUrl
from shared_core.helpers.key_pair import get_ec_keys
from shared_core.schemas import jwk as jwk_schema
from shared_core.schemas.dpop import (
    AuthorizeRequest,
    DPoPProofHeader,
    DPoPProofPayload,
    AccessTokenRequest,
)
from shared_core.services.dpop_session import DPoPAuth
from shared_core.shared_types.http_request import MethodType
import httpx
import secrets
from joserfc import jwt, jwk
from bff.config import settings
import redis.asyncio as redis


logger = logging.getLogger(__name__)
app = FastAPI(lifespan=lifespan)

# In production, store this in Redis/Session, not a global dict

IDP_TOKEN_URL = "https://idp.example.com/token"
IDP_TOKEN_URL = settings.token_url
RS_API_URL = "https://rs.example.com/api/data"

USER_PRIVATE_KEY, USER_PUBLIC_KEY = get_ec_keys()


def generate_dpop_proof(
    private_key: jwk.ECKey,
    public_key: jwk.ECKey,
    method: MethodType,
    url: HttpUrl,
    ath: str = None,
) -> str:
    """Generates a DPoP Proof JWT."""
    header = DPoPProofHeader(
        typ="dpop+jwt",
        alg="ES256",
        jwk=jwk_schema.DPoPClientPublicKey.model_validate(public_key.as_dict()),
    )
    payload = DPoPProofPayload(
        htm=method,
        htu=url,
        ath=ath,  # Hash of the access token for extra binding
    )
    return jwt.encode(
        header.model_dump(mode="json"),
        payload.model_dump(mode="json"),
        private_key,
    )


def get_redis_pool(request: Request) -> redis.Redis:
    return request.app.state.redis_pool


def get_bff_manager(request: Request) -> RedisBFFManager:
    return request.app.state.bff


@app.get("/login")
async def login(request: Request):
    """
    Starts the OIDC Flow.
    Note: State and Verifier should ideally be stored in a temporary
    short-lived Redis key linked to a 'pre-auth' cookie.
    Request an authorization code
    To get an authorization code, your app redirects the user to
    your authorization server's /authorize endpoint.
    If you're using the org authorization server,
    then your request URL would look something like this:

    https://{AS_BASE_URL}/oauth2/v1/authorize?
    client_id=0oabucvyc38HLL1ef0h7&
    response_type=code&scope=openid&
    redirect_uri=https%3A%2F%2Fexample.com&
    state=state-296bc9a0-a2a2-4a57-be1a-d0e2fd9bb601
    Note the parameters that are being passed:

    `client_id`: The client ID of the app integration that you created earlier.
    Find it in the Admin Console on your app integration's General tab.
    response_type: The value is code, which indicates that you're using
    the Authorization Code grant type.
    `scope`: The value is openid, which means that
    the /token endpoint returns an ID token.
    For custom scopes, see the Create Scopes section of the
    Create an authorization server guide.
    `redirect_uri`: The callback location where the user agent
    is directed to along with the code.
    This URI must match one of the Sign-in redirect URIs that
    you specified when you created your app integration earlier.
    state: An arbitrary alphanumeric string that the authorization
    server reproduces when redirecting the user agent back to the client.
    This is used to help prevent cross-site request forgery.
    """
    state = secrets.token_urlsafe(64)
    code_verifier = secrets.token_urlsafe(64)

    # Calculate PKCE
    hashed = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).decode("ascii").strip("=")

    request_params = AuthorizeRequest(
        client_id=settings.OIDC_CLIENT_ID,
        redirect_uri=settings.redirect_uri,
        scope="openid email profile offline_access",
        state=state,
        code_challenge=code_challenge,
        code_challenge_method="S256",
        response_type="code",
        response_mode="query",
    )

    # Temporarily storing verifier in a cookie for the callback
    response = RedirectResponse(
        url=f"{settings.authorize_url}?{urlencode(request_params.model_dump(mode='json'))}",
        status_code=307,
    )
    response.set_cookie("pkce_verifier", code_verifier, httponly=True, max_age=300)
    return response


@app.get("/authorization-code/callback")
async def callback(
    code: str,
    state: str,
    pkce_verifier: str = Cookie(None),
    bff_manager: RedisBFFManager = Depends(get_bff_manager),
    redis_pool: redis.Redis = Depends(get_redis_pool),
):
    if not pkce_verifier:
        raise HTTPException(status_code=400, detail="Missing PKCE verifier")

    # 1. Generate new DPoP Key Pair for this specific user session
    # We use EC keys (ES256) as defined in our generate_dpop_proof
    priv_key, pub_key = get_ec_keys()
    kid = secrets.token_hex(8)

    # 2. Generate the DPoP Proof for the Token Exchange
    # According to RFC 9449, for the token endpoint:
    # - htm: POST
    # - htu: The token endpoint URL
    # - ath: Omitted (we don't have the token yet)
    dpop_proof: str = generate_dpop_proof(
        private_key=priv_key, public_key=pub_key, method="POST", url=settings.token_url
    )

    # 2. Token Exchange using a one-time DPoP proof
    # (Simplified: in a real scenario, use your generate_dpop_proof helper here)
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            settings.token_url,
            data=AccessTokenRequest(
                grant_type="authorization_code",
                code="code",
                redirect_uri=settings.redirect_uri,
                code_verifier=pkce_verifier,
            ).model_dump(mode='json'),
            # DPoP proof is sent in the 'DPoP' header
            headers={"DPoP": dpop_proof},
            auth=(settings.OIDC_CLIENT_ID, settings.OIDC_CLIENT_SECRET),
        )

        # Check for error responses (e.g., 400 Bad Request)
        if token_resp.is_error:
            logger.error(f"Token exchange failed: {token_resp.text}")
            raise HTTPException(status_code=401, detail="Token exchange failed")

        tokens = token_resp.json()

    # 3. Create persistent Session in Redis via BFF Manager
    # This stores the private_key so the proxy can sign future requests
    session_id = secrets.token_hex(32)

    await bff_manager.create_session(
        session_id=session_id,
        tokens=tokens,
        kid=kid,
        private_key=priv_key,
        redis_client=redis_pool,
    )

    # 4. Finalize response and cleanup temporary PKCE cookie
    response = RedirectResponse(url=settings.HOME_PAGE)
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    response.delete_cookie("pkce_verifier")
    return response


# Routes
@app.get("/api/data")
async def proxy_data(
    background_tasks: BackgroundTasks,
    bff_manager: RedisBFFManager = Depends(get_bff_manager),
    redis_pool: redis.Redis = Depends(get_redis_pool),
    client: httpx.AsyncClient = Depends(get_bff_client),
    session_id: str = Cookie(None, alias=settings.COOKIE_NAME),
):
    # Perform the actual request (DPoPAuth handles retries/refresh internally)
    response = await client.get(RS_API_URL)

    # After the request, the 'client.auth' object contains the newest state
    auth: DPoPAuth = client.auth

    # Schedule the sync
    background_tasks.add_task(
        bff_manager.update_session_data,
        session_id,
        auth.access_token,
        auth.refresh_token,
        auth.server_nonce,
        redis_pool,
    )

    return response.json()


# Routes
@app.get("/api/proxy/{path:path}")
async def proxy_request(
    path: str,
    background_tasks: BackgroundTasks,
    bff_manager: RedisBFFManager = Depends(get_bff_manager),
    redis_pool: redis.Redis = Depends(get_redis_pool),
    client: httpx.AsyncClient = Depends(get_bff_client),
    session_id: str = Cookie(None, alias=settings.COOKIE_NAME),
):
    # Perform the actual request (DPoPAuth handles retries/refresh internally)
    response = await client.get(f"{settings.API_GATEWAY_URL}/{path}")

    # After the request, the 'client.auth' object contains the newest state
    auth: DPoPAuth = client.auth

    # Schedule the sync
    background_tasks.add_task(
        bff_manager.update_session_data,
        session_id,
        auth.access_token,
        auth.refresh_token,
        auth.server_nonce,
        redis_pool,
    )

    return response.json()
