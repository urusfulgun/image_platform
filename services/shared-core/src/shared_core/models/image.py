"""Image Pydantic schemas."""
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Optional
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
    processed_s3_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    dimensions_px: Optional[str] = None
    status: ImageStatus = ImageStatus.PENDING
    retry_count: int = 0
    last_error_log: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ImageSchemaPreview(BaseModel):
    """Image metadata representation."""

    id: uuid.UUID
    original_filename: str
    status: ImageStatus = ImageStatus.PENDING
    display_url: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RegisterImageRequest(BaseModel):
    project_id: uuid.UUID
    original_filename: str
    file_size_bytes: Optional[int] = None
