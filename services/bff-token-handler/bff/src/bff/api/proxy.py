from typing import Annotated
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, HttpUrl, StringConstraints
from shared_core.shared_types.http_request import MethodType
from bff.service_layer.bff_proxy import BFFProxyService
from bff.dependencies.session import get_bff_client
from bff.dependencies.redis_nonce import update_redis_nonce
from bff.config import settings
from bff.api.schemas import CommonBffProxyResponse
import httpx

router = APIRouter(prefix="/proxy", tags=["Proxy"])


# 1. Strip leading/trailing slashes to prevent double slashes in your f-string
# 2. Prevent ".." to block path traversal attempts
def validate_remote_path(v: str) -> str:
    if ".." in v:
        raise ValueError("Path traversal sequences (..) are not allowed")
    return v.strip("/")


def validate_final_url(v: str) -> str:
    try:
        url = httpx.URL(f"{settings.API_GATEWAY_URL}/{v}")
        # Logic check: Ensure it hasn't escaped the gateway's base path
        if not str(url).startswith(str(settings.API_GATEWAY_URL)):
            raise ValueError("Invalid target destination")
        return v
    except Exception:
        raise ValueError("Malformed URL path")



SafePath = Annotated[
    str, 
    StringConstraints(min_length=1, max_length=2048),
    AfterValidator(validate_remote_path)
]

@router.get("/login")
def login_request(
    request: Request
    ):
    raise NotImplementedError


# Routes
@router.get("/api/proxy/{path:path}")
async def proxy_request(
    path: SafePath,
    background_tasks: BackgroundTasks,
    client: httpx.AsyncClient = Depends(get_bff_client),
    session_id: str = Cookie(None, alias=settings.COOKIE_NAME)
):
    # The DPoPAuth inside 'client' will automatically:
    # 1. Sign the request
    # 2. Retry once if a 401 'use_dpop_nonce' is received
    response = await client.get(f"{settings.API_GATEWAY_URL}/{path}")
    
    # Sync the new nonce to Redis so other instances/processes can use it
    background_tasks.add_task(update_redis_nonce, session_id, client)
    
    return response.json()


@router.api_route("/api/{path:path}", methods=MethodType)
async def bff_proxy_handler(
    path: str,
    request: Request,
    proxy: BFFProxyService = Depends(get_proxy_service),
):
    """
    Catch-all route that forwards frontend requests to the Gateway.
    """
    data, status_code = await proxy.forward_to_gateway(request, path)
    return JSONResponse(content=data, status_code=status_code)
