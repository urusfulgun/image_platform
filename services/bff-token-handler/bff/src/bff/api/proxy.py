from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import HttpUrl
from shared_core.shared_types.http_request import MethodType
from bff.service_layer.bff_proxy import BFFProxyService
from bff.dependencies.session import get_session
from bff.dependencies.redis_nonce import update_redis_nonce
from bff.config import settings
from bff.api.schemas import CommonBffProxyResponse
import httpx

router = APIRouter(prefix="/proxy", tags=["Proxy"])


# Routes
@router.get("/api/proxy/{path:path}")
async def proxy_request(
    background_tasks: BackgroundTasks,
    client: httpx.AsyncClient = Depends(get_bff_client),
    session_id: str = Cookie(None, alias=settings.COOKIE_NAME)
):
    # The DPoPAuth inside 'client' will automatically:
    # 1. Sign the request
    # 2. Retry once if a 401 'use_dpop_nonce' is received
    response = await client.get(f"{settings.API_GATEWAY_URL}/data")
    
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
