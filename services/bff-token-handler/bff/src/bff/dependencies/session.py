from fastapi import Cookie, HTTPException, Request
from bff.service_layer.bff_manager import RedisBFFManager
import httpx


async def get_session(
    request: Request,
    session_id: str = Cookie(None),
) -> httpx.AsyncClient:
    if not session_id:
        raise HTTPException(401)
    bff: RedisBFFManager = request.app.state.bff
    client: httpx.AsyncClient = await bff.get_client(session_id)
    if client is None:
        raise HTTPException(401)
    return client
