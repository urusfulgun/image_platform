import asyncio
import io
import json
import logging
import signal
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiobotocore.config import AioConfig
from PIL import Image, ImageFile
import aioboto3
from shared_core.events.kafka_events import (
    DLQImageProcessingEventPayload,
    ImageAvifReadyEvent,
    ImageRawUploadedEvent,
)

from shared_core.utils.s3_object_key import (
    get_new_s3_path,
    get_s3_object_key,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KafkaImageProcessor")

ImageFile.LOAD_TRUNCATED_IMAGES = True


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

        # Topics
        self.INPUT_TOPIC = "image.raw.uploaded"
        self.SUCCESS_TOPIC = "image.avif.ready"
        self.DLQ_TOPIC = "image.raw.failed"

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
            f"Processor live. Raw Bucket: {self.raw_bucket} -> Processed Bucket: {self.processed_bucket}"
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

    async def handle_processing(self, event: ImageRawUploadedEvent):
        """Moves data from raw_bucket to processed_bucket after conversion."""
        async with self.session.client("s3", **self.s3_config) as s3:
            # 1. Download from RAW bucket
            response = await s3.get_object(
                Bucket=self.raw_bucket, Key=event.raw_s3_path
            )
            raw_bytes = await response["Body"].read()

            # 2. Convert to AVIF
            loop = asyncio.get_running_loop()
            avif_bytes, avif_path = await loop.run_in_executor(
                None,
                self._to_avif,
                raw_bytes,
                event.raw_s3_path,
                event.project_id,
            )

            # 3. Upload to PROCESSED bucket
            await s3.put_object(
                Bucket=self.processed_bucket,
                Key=avif_path,
                Body=avif_bytes,
                ContentType="image/avif",
            )

            # 4. Produce Success Event
            ready_event = ImageAvifReadyEvent(
                image_id=event.image_id,
                project_id=event.project_id,
                processed_s3_path=avif_path,
            )
            await self.producer.send_and_wait(
                self.SUCCESS_TOPIC, ready_event.model_dump(mode="json")
            )
            logger.info(f"Processed: {event.image_id} -> {avif_path}")

    def _get_s3_key(self, project_id: str, sufix: str) -> str:
        return get_s3_object_key(
            project_id=project_id,
            sufix=sufix,
        )

    def _to_avif(
        self, data: bytes, original_path: str, project_id: str
    ) -> tuple[bytes, str]:
        """Synchronous CPU-intensive conversion."""
        with Image.open(io.BytesIO(data)) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")

            buf = io.BytesIO()
            # AVIF settings: quality 60 (high efficiency), speed 6 (balanced)
            img.save(buf, format="AVIF", quality=60, speed=6)

            # Create path for processed bucket
            # Example: "uploads/image.jpg" -> "uploads/image.avif"
            new_path = self._get_s3_key(project_id, "optimized.avif")
            return buf.getvalue(), new_path


# --- Main Entry ---
async def main():
    s3_settings = {
        "endpoint_url": "http://rustfs:9000",
        "aws_access_key_id": "OAhzGogEY7X61ZwjnSmH",
        "aws_secret_access_key": "5XItB3Pon6syp7e1cxNvJOTfWlzigEZQkK2FM8Vh",
        "config": AioConfig(signature_version="s3v4"),
        "region_name": "us-east-1",
    }

    worker = KafkaImageWorker(
        kafka_bootstrap="kafka:9092",
        s3_config=s3_settings,
        raw_bucket="raw-images",
        processed_bucket="processed-images",
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    worker_task = asyncio.create_task(worker.run())

    try:
        await stop_event.wait()
        logger.info("Shutdown signal received.")
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        logger.info("Worker stopped gracefully.")


if __name__ == "__main__":
    asyncio.run(main())
