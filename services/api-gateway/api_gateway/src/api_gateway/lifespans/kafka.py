import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
import logging

from api_gateway.message_handlers.user_synchronization import consume_user_events
from api_gateway.utils.kafka_producer import create_producer
from api_gateway.config import settings
from fastapi import FastAPI
from api_gateway.db import async_session_factory


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway-kafka")


# --- Kafka producer Lifespan ---
@asynccontextmanager
async def kafka_producer_lifespan(app: FastAPI):
    producer = create_producer(settings)
    await producer.start()
    print("Kafka Producer started")
    app.state.kafka_producer = producer
    try:
        yield
    finally:
        await producer.stop()
        print("Kafka Producer stopped")


@asynccontextmanager
async def user_synchronization_consumer_lifespan(app: FastAPI):
    task = asyncio.create_task(consume_user_events(async_session_factory))
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Kafka consumer task cancelled gracefully")
