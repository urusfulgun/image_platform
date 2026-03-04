"""Kafka producer for AssetService."""

import json
import logging

from aiokafka import AIOKafkaProducer

from asset_service.settings import settings
from shared_core.events.kafka_events import ImageDeletedEvent, ImageRawUploadedEvent

log = logging.getLogger(__name__)


class AssetKafkaProducer:
    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await self._producer.start()
        log.info("Kafka producer started.")

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()

    async def publish_image_raw_uploaded(self, event: ImageRawUploadedEvent) -> None:
        """Publish an ImageRawUploadedEvent to the image.raw.uploaded topic."""
        await self._producer.send_and_wait(
            settings.image_raw_uploaded_topic,
            value=event.model_dump(mode="json"),
            key=str(event.image_id).encode(),
        )
        log.info("Published image.raw.uploaded for image_id=%s", event.image_id)

    async def publish_image_raw_presign_link_generated_topic(
        self, event: ImageRawUploadedEvent
    ) -> None:
        """Publish an ImageRawUploadedEvent to the image.raw.uploading_link_generated topic."""
        await self._producer.send_and_wait(
            settings.image_raw_presign_link_generated_topic,
            value=event.model_dump(mode="json"),
            key=str(event.image_id).encode(),
        )
        log.info(
            "Published image.raw.uploading_link_generated for image_id=%s",
            event.image_id,
        )

    async def publish_image_deleted_topic(
        self,
        event: ImageDeletedEvent,
    ) -> None:
        """
        Publish an ImageDeletedEvent to the image.deleted topic.
        This triggers the cleanup service to purge S3 assets.
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        # Using send_and_wait ensures the message is acknowledged by Kafka
        # before the API returns success to the user.
        await self._producer.send_and_wait(
            settings.image_deleted_topic,
            value=event.model_dump(mode="json"),
            key=str(event.image_id).encode(),
        )

        log.info(
            "Published image.deleted event for image_id=%s. Cleanup pending.",
            event.image_id,
        )


producer = AssetKafkaProducer()
