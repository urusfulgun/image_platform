from datetime import datetime
from typing import Literal
import uuid

from pydantic import BaseModel, Field


class ImageTask(BaseModel):
    """Specific image within a batch to be processed."""

    image_id: uuid.UUID
    storage_key: str = Field(
        ..., description="The S3 path to the raw file (e.g., raw/uuid.jpg)"
    )
    display_name: str


class BatchProcessEvent(BaseModel):
    """
    The event payload sent to the 'batch.created' Kafka topic.
    """

    event_id: uuid.UUID = Field(default_factory=uuid.uuid7)
    version: str = "1.0"
    project_id: uuid.UUID
    batch_id: uuid.UUID
    owner_id: uuid.UUID

    # Configuration for the worker
    target_resolutions: list[Literal["normal", "preview", "thumbnail"]] = Field(
        default=["normal", "preview", "thumbnail"]
    )
    output_format: Literal["AVIF", "WEBP"] = "AVIF"

    # The actual payload
    images: list[ImageTask]

    created_at: datetime = Field(default_factory=lambda: get_utc_now)

    class Config:
        frozen = True  # Events should be immutable
