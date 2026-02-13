from contextlib import asynccontextmanager
from fastapi import FastAPI
import redis.asyncio as redis
from shared_core.abstract.dpop_key_registry import DPoPKeyRegistry
from bff.service_layer.bff_manager import RedisBFFManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    print("[Lifespan] Initializing Redis connection pool...")
    app.state.redis_pool = redis.from_url(
        "redis://localhost:6379/0", decode_responses=True
    )

    # Initialize the Registry and Manager
    registry = DPoPKeyRegistry()
    app.state.bff = await RedisBFFManager.create(registry)

    yield  # The application runs while this is suspended

    # --- SHUTDOWN ---
    # --- SHUTDOWN LOGIC ---
    print("Shutting down: Closing DPoP clients and Redis...")
    await app.state.bff.shutdown()
    await app.state.redis_pool.close()
    print("Shutdown complete.")
