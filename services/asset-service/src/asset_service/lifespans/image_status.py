import asyncio
import logging
import json
from contextlib import asynccontextmanager
from asset_service.db.session import AsyncSessionLocal
from fastapi import FastAPI
from aiokafka import AIOKafkaConsumer

# Assuming these are imported from your project structure
from asset_service.domain.images import ImageService
from shared_core.events.kafka_events import ImageAvifReadyEvent
from asset_service.settings import settings

log = logging.getLogger(__name__)


async def kafka_consumer_task(topic: str, bootstrap_servers: str):
    """
    Background worker that consumes AVIF readiness events.
    """
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        group_id="asset_service_status_updater",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        enable_auto_commit=True,
    )

    await consumer.start()
    log.info(f"Kafka consumer started on topic: {topic}")

    try:
        async for msg in consumer:
            try:
                # Validate the incoming event
                event_data = ImageAvifReadyEvent.model_validate(msg.value)
                log.info(f"Processing avif.ready for image: {event_data.image_id}")

                # We need a fresh session for each background processing task
                async with AsyncSessionLocal() as db:
                    image_service = ImageService(db)
                    await image_service.update_status(
                        image_id=event_data.image_id,
                        new_status="OPTIMIZED",
                        processed_s3_path=event_data.processed_s3_path,
                        preview_s3_path=event_data.preview_s3_path,
                        processed_format=event_data.processed_format,
                    )

                log.info(f"Successfully updated status for {event_data.image_id}")

            except Exception as e:
                log.error(f"Error processing Kafka message: {e}", exc_info=True)

    except asyncio.CancelledError:
        log.info("Kafka consumer task is shutting down.")
    finally:
        await consumer.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup: Create the background task
    # Note: Replace with your actual Kafka connection string
    kafka_task = asyncio.create_task(
        kafka_consumer_task("image.avif.ready", settings.kafka_bootstrap_servers)
    )

    yield  # --- App is running and serving requests ---

    # 2. Shutdown: Cancel the background task and wait for it to finish
    log.info("Shutting down background image update tasks...")
    kafka_task.cancel()
    try:
        await kafka_task
    except asyncio.CancelledError:
        log.info("Background Kafka image update task cancelled successfully.")
