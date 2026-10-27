import asyncio
import json
import logging
import signal
import aioboto3
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiobotocore.config import AioConfig
from shared_core.events.kafka_events import (
    ImageDeletedEvent,
    DLQImageProcessingEventPayload,  # Reusing payload for consistency
)
from fastapi import FastAPI, Response, status
import uvicorn


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KafkaCleanupWorker")


# --- FastAPI Setup ---
app = FastAPI()
worker_instance = None  # Global reference for the health check to inspect


@app.get("/health")
async def health_check():
    """
    Checks if the Kafka consumer and producer are still connected.
    """
    if not worker_instance:
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    # Check if Kafka components are running
    # Note: _closed is an internal state, but useful for basic liveness
    is_consumer_ok = worker_instance.consumer is not None
    is_producer_ok = worker_instance.producer is not None

    if is_consumer_ok and is_producer_ok:
        return {"status": "healthy", "worker": "active"}

    return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


class KafkaCleanupWorker:
    def __init__(
        self,
        kafka_bootstrap: str,
        s3_config: dict,
        raw_bucket: str,
        processed_bucket: str,
    ):
        self.kafka_bootstrap = kafka_bootstrap
        self.s3_config = s3_config
        self.raw_bucket = raw_bucket
        self.processed_bucket = processed_bucket
        self.session = aioboto3.Session()

        self.INPUT_TOPIC = "image.all.deleted"
        self.OUTPUT_TOPIC = "image.bucket.deleted"
        self.DLQ_TOPIC = "image.cleanup.failed"

        self.consumer = AIOKafkaConsumer(
            self.INPUT_TOPIC,
            bootstrap_servers=self.kafka_bootstrap,
            group_id="image-cleanup-group",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            enable_auto_commit=False,
        )
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

    async def run(self):
        await self.consumer.start()
        await self.producer.start()
        logger.info(f"Cleanup Worker live. Monitoring: {self.INPUT_TOPIC}")

        try:
            async for msg in self.consumer:
                try:
                    event = ImageDeletedEvent(**msg.value)
                    await self.handle_cleanup(event)
                except Exception as e:
                    logger.error(
                        f"Cleanup failed for image {msg.value.get('image_id')}: {e}"
                    )
                    await self.send_to_dlq(msg.value, str(e))
                finally:
                    # We commit only after processing or moving to DLQ
                    await self.consumer.commit()
        finally:
            await self.consumer.stop()
            await self.producer.stop()

    async def send_to_dlq(self, original_payload: dict, error_message: str):
        """Ensures we don't lose track of files that failed to delete."""
        try:
            dlq_payload = DLQImageProcessingEventPayload(
                original_event=original_payload,
                error=error_message,
                processor_version="1.0.0-py3.14.2-cleanup",
            )
            await self.producer.send_and_wait(
                self.DLQ_TOPIC, dlq_payload.model_dump(mode="json")
            )
            logger.warning(
                f"Sent cleanup event {original_payload.get('image_id')} to DLQ."
            )
        except Exception as dlq_err:
            logger.critical(f"Cleanup DLQ failure: {dlq_err}")

    async def handle_cleanup(self, event: ImageDeletedEvent):
        """Purges all associated S3 objects for a deleted image."""
        async with self.session.client("s3", **self.s3_config) as s3:
            deletion_tasks = []

            # 1. Raw Image (Source of truth)
            if event.raw_s3_path:
                deletion_tasks.append(
                    s3.delete_object(Bucket=self.raw_bucket, Key=event.raw_s3_path)
                )

            # 2. Optimized/Processed Image
            if event.processed_s3_path:
                deletion_tasks.append(
                    s3.delete_object(
                        Bucket=self.processed_bucket, Key=event.processed_s3_path
                    )
                )

            # 3. Preview Tile
            if event.preview_s3_path:
                deletion_tasks.append(
                    s3.delete_object(
                        Bucket=self.processed_bucket, Key=event.preview_s3_path
                    )
                )

            if deletion_tasks:
                # Use return_exceptions=True so one missing file doesn't stop others
                results = await asyncio.gather(*deletion_tasks, return_exceptions=True)

                for res in results:
                    if isinstance(res, Exception):
                        # Log error but don't necessarily crash; check S3 404s specifically
                        logger.error(f"S3 deletion error for {event.image_id}: {res}")

            logger.info(f"Purged S3 assets for image: {event.image_id}")


# --- Main Entry ---
async def main():
    global worker_instance
    s3_settings = {
        "endpoint_url": "http://rustfs:9000",
        "aws_access_key_id": "OAhzGogEY7X61ZwjnSmH",
        "aws_secret_access_key": "5XItB3Pon6syp7e1cxNvJOTfWlzigEZQkK2FM8Vh",
        "config": AioConfig(signature_version="s3v4"),
        "region_name": "us-east-1",
    }

    worker_instance = KafkaCleanupWorker(
        kafka_bootstrap="kafka:9092",
        s3_config=s3_settings,
        raw_bucket="raw-images",
        processed_bucket="processed-images",
    )

    # Setup FastAPI server to run in the background
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="error")
    server = uvicorn.Server(config)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        # Structured Concurrency: TaskGroup manages the lifetime of all tasks
        async with asyncio.TaskGroup() as tg:
            w_task = tg.create_task(worker_instance.run())
            _ = tg.create_task(server.serve())

            # Wait until a shutdown signal is received
            await stop_event.wait()
            logger.info("Shutdown signal received.")
            # Signal the server and worker to wind down
            server.should_exit = True
            logger.info("Initiating graceful shutdown...")
            w_task.cancel()

            # When we exit this block, all remaining tasks (worker/server)
            # are automatically cancelled and awaited.
    except* asyncio.CancelledError:
        # This is expected when we cancel w_task
        pass
    except* Exception as eg:
        # Python 3.11+ ExceptionGroup handling
        for error in eg.exceptions:
            logger.error(f"Task error: {error}")
    finally:
        logger.info("Worker and Health server stopped gracefully.")


if __name__ == "__main__":
    asyncio.run(main())
