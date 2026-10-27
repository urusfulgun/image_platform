"""Image Pydantic schemas."""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ImageStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    OPTIMIZED = "OPTIMIZED"
    FAILED = "FAILED"


class ImageSchema(BaseModel):
    """Image metadata representation."""

    id: uuid.UUID
    project_id: uuid.UUID
    original_filename: str
    raw_s3_path: str
    processed_s3_path: str | None = None
    file_size_bytes: int | None = None
    dimensions_px: str | None = None
    status: ImageStatus = ImageStatus.PENDING
    retry_count: int = 0
    last_error_log: str | None = None
    processed_format: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ImageSchemaPreview(BaseModel):
    """Image metadata representation."""

    id: uuid.UUID
    original_filename: str
    status: ImageStatus = ImageStatus.PENDING
    display_url: str
    created_at: datetime
    raw_image_url: str | None
    processed_image_url: str | None
    processed_format: str | None

    model_config = {"from_attributes": True}


class RegisterImageRequest(BaseModel):
    project_id: uuid.UUID
    original_filename: str
    file_size_bytes: int | None = None
