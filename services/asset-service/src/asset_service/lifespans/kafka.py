# --- Lifespan Context Manager ---
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from asset_service.kafka.consumer import consume_user_events


@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP: Create the background task
    app.state.kafka_task = asyncio.create_task(consume_user_events())
    print("🚀 Kafka Consumer started in background")

    yield  # The app runs while this is suspended

    # SHUTDOWN: Cancel the task and wait for it to finish
    print("🛑 Shutting down Kafka Consumer...")
    app.state.kafka_task.cancel()
    try:
        await app.state.kafka_task
    except asyncio.CancelledError:
        print("✅ Kafka Consumer task cancelled gracefully")
