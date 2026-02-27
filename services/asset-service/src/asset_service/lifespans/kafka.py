# --- Lifespan Context Manager ---
import asyncio
from contextlib import asynccontextmanager
import logging

from asset_service.kafka.producer import AssetKafkaProducer
from fastapi import FastAPI
from asset_service.kafka.consumer import consume_user_events


log = logging.getLogger(__name__)


@asynccontextmanager
async def kafka_events_consumer_lifespan(app: FastAPI):
    # STARTUP: Create the background task
    kafka_task = asyncio.create_task(consume_user_events())
    app.state.kafka_task = kafka_task
    print("🚀 Kafka Consumer started in background")

    yield  # The app runs while this is suspended

    # SHUTDOWN: Cancel the task and wait for it to finish
    print("🛑 Shutting down Kafka Consumer...")
    kafka_task.cancel()
    await asyncio.gather(kafka_task, return_exceptions=True)
    try:
        await kafka_task
    except asyncio.CancelledError:
        print("✅ Kafka Consumer task cancelled gracefully")


@asynccontextmanager
async def kafka_events_producer_lifespan(app: FastAPI):
    # Startup
    # ensure_buckets()
    producer = AssetKafkaProducer()
    app.state.kafka_producer = producer
    await producer.start()
    log.info("KafkaProducer started.")
    yield
    await producer.stop()
    log.info("KafkaProducer shut down.")
