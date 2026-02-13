from fastapi import Request
import httpx
import redis.asyncio as redis
from shared_core.services.dpop_session import DPoPAuth
from bff.service_layer.redis_schemas import RedisSessionPayload
from bff.service_layer.bff_manager import RedisBFFManager


async def update_redis_nonce(
    request: Request, session_id: str, client: httpx.AsyncClient
) -> None:
    """Background task to sync the latest DPoP-Nonce to Redis."""
    redis_client: redis.Redis = request.app.state.redis_pool
    bff_manager: RedisBFFManager = request.app.state.bff
    await bff_manager.update_redis_nonce(session_id, client, redis_client)
