from fastapi import Cookie, HTTPException, Request, Depends
from bff.service_layer.bff_manager import RedisBFFManager
from bff.config import settings
import httpx
import redis.asyncio as redis


async def get_bff_client(
    request: Request, session_id: str = Cookie(None, alias=settings.COOKIE_NAME)
) -> httpx.AsyncClient:
    if not session_id:
        raise HTTPException(status_code=401, detail="Session Cookie Missing")

    # Access instances from app.state (initialized in lifespan)
    bff_manager: RedisBFFManager = request.app.state.bff
    redis_client: redis.Redis = request.app.state.redis_pool

    client = await bff_manager.get_client(session_id, redis_client, settings)
    if not client:
        raise HTTPException(status_code=401, detail="Session Expired")

    return client
