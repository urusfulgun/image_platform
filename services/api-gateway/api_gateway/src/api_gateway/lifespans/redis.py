from contextlib import asynccontextmanager
from fastapi import FastAPI
import redis.asyncio as redis


# 1. Define the lifespan logic
@asynccontextmanager
async def redis_lifespan(app: FastAPI):
    # Startup: Create the Redis connection pool
    print("Connecting to Redis...")
    pool = redis.ConnectionPool.from_url("redis://localhost", decode_responses=True)
    app.state.redis = redis.Redis(connection_pool=pool)
    
    yield  # The app runs while execution is paused here
    
    # Shutdown: Close the connection pool
    print("Closing Redis connection...")
    await app.state.redis.close()
    await pool.disconnect()