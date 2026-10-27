import asyncio
import io
import json
import logging
import signal

import aioboto3
import uvicorn
from aiobotocore.config import AioConfig
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from fastapi import FastAPI, Response, status
from PIL import Image, ImageFile

from shared_core.events.kafka_events import (
    DLQImageProcessingEventPayload,
    # Note: You may need to update this schema to include preview_s3_path
    ImageAvifReadyEvent,
    ImageRawUploadedEvent,
)
from shared_core.utils.s3_object_key import get_s3_object_key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KafkaImageProcessor")

ImageFile.LOAD_TRUNCATED_IMAGES = True

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


class KafkaImageWorker:
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

        self.INPUT_TOPIC = "image.raw.uploaded"
        self.SUCCESS_TOPIC = "image.avif.ready"
        self.DLQ_TOPIC = "image.raw.failed"

        # Preview Settings
        self.PREVIEW_SIZE = (300, 300)

        self.consumer = AIOKafkaConsumer(
            self.INPUT_TOPIC,
            bootstrap_servers=self.kafka_bootstrap,
            group_id="image-processor-group",
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
        logger.info(
            f"Processor live. Raw Bucket: {self.raw_bucket} -> "
            f"Processed Bucket: {self.processed_bucket}"
        )

        try:
            async for msg in self.consumer:
                try:
                    event = ImageRawUploadedEvent(**msg.value)
                    await self.handle_processing(event)
                except Exception as e:
                    logger.error(
                        f"Processing failed for image {msg.value.get('image_id')}: {e}"
                    )
                    await self.send_to_dlq(msg.value, str(e))
                finally:
                    await self.consumer.commit()
        finally:
            await self.consumer.stop()
            await self.producer.stop()

    async def send_to_dlq(self, original_payload: dict, error_message: str):
        """Wraps the failed message with error metadata and sends to DLQ."""
        try:
            dlq_payload = DLQImageProcessingEventPayload(
                original_event=original_payload,
                error=error_message,
                processor_version="1.0.0-py3.14.2",
            )
            await self.producer.send_and_wait(
                self.DLQ_TOPIC, dlq_payload.model_dump(mode="json")
            )
            logger.warning(f"Sent event {original_payload.get('image_id')} to DLQ.")
        except Exception as dlq_err:
            logger.critical(f"Critical failure: Could not send to DLQ: {dlq_err}")

    # ... (run and send_to_dlq methods remain the same) ...

    async def handle_processing(self, event: ImageRawUploadedEvent):
        """Processes raw image into a high-res AVIF and a small preview tile."""
        async with self.session.client("s3", **self.s3_config) as s3:
            # 1. Download
            response = await s3.get_object(
                Bucket=self.raw_bucket, Key=event.raw_s3_path
            )
            raw_bytes = await response["Body"].read()

            # 2. Process Images (Offload CPU bound task to executor)
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                None, self._process_image_variants, raw_bytes, event.project_id
            )

            main_img, preview_img = results

            # 3. Upload both variants
            uploads = [
                s3.put_object(
                    Bucket=self.processed_bucket,
                    Key=main_img["path"],
                    Body=main_img["bytes"],
                    ContentType="image/avif",
                ),
                s3.put_object(
                    Bucket=self.processed_bucket,
                    Key=preview_img["path"],
                    Body=preview_img["bytes"],
                    ContentType="image/avif",
                ),
            ]
            await asyncio.gather(*uploads)

            # 4. Produce Success Event
            # Ensure your ImageAvifReadyEvent schema supports preview_s3_path
            ready_event = ImageAvifReadyEvent(
                image_id=event.image_id,
                project_id=event.project_id,
                processed_s3_path=main_img["path"],
                preview_s3_path=preview_img["path"],
                processed_format="avif",
            )
            await self.producer.send_and_wait(
                self.SUCCESS_TOPIC, ready_event.model_dump(mode="json")
            )
            logger.info(f"Processed variants for: {event.image_id}")

    def _process_image_variants(self, data: bytes, project_id: str) -> tuple:
        """Synchronous transformation of images."""
        with Image.open(io.BytesIO(data)) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")

            # --- Generate Main High-Res ---
            main_buf = io.BytesIO()
            img.save(main_buf, format="AVIF", quality=60, speed=6)
            main_path = get_s3_object_key(project_id, "optimized.avif")

            # --- Generate Preview Tile ---
            # Use thumbnail() to maintain aspect ratio
            preview_img = img.copy()
            preview_img.thumbnail(self.PREVIEW_SIZE, Image.Resampling.LANCZOS)

            preview_buf = io.BytesIO()
            # Lower quality is fine for tiny tiles to save bandwidth
            preview_img.save(preview_buf, format="AVIF", quality=40, speed=8)
            preview_path = get_s3_object_key(project_id, "preview_tile.avif")

            return (
                {"bytes": main_buf.getvalue(), "path": main_path},
                {"bytes": preview_buf.getvalue(), "path": preview_path},
            )


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

    worker_instance = KafkaImageWorker(
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
