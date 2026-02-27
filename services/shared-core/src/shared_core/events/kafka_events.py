"""Kafka event message schemas for inter-service communication."""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from shared_core.utils.utc import get_utc_now


class ImageRawUploadedEvent(BaseModel):
    """Published by AssetService after a raw image is ingested.

    Consumed by ImageProcessor.
    Topic: image.raw.uploaded
    """

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    image_id: uuid.UUID
    project_id: uuid.UUID
    raw_s3_path: str
    raw_format: str  # e.g. "jpeg", "png", "webp"
    file_size_bytes: Optional[int] = None
    occurred_at: datetime = Field(default_factory=get_utc_now)


class ImageAvifReadyEvent(BaseModel):
    """Published by ImageProcessor after AVIF conversion completes.

    Consumed by NotificationWorker and CleanupWorker.
    Topic: image.avif.ready
    """

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    image_id: uuid.UUID
    project_id: uuid.UUID
    processed_s3_path: str
    occurred_at: datetime = Field(default_factory=get_utc_now)


class CleanupRequestedEvent(BaseModel):
    """Published by CleanupWorker to signal deletion of raw source files.

    Topic: image.cleanup.requested
    """

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    image_id: uuid.UUID
    raw_s3_path: str
    occurred_at: datetime = Field(default_factory=get_utc_now)
