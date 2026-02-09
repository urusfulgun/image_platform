import uuid
from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field

class ImageLifecycleEvent(BaseModel):
    """
    Standardized event for tracking an image from initialization 
    through to successful processing or failure.
    """
    event_id: uuid.UUID = Field(default_factory=uuid.uuid7)
    image_id: uuid.UUID
    batch_id: uuid.UUID
    project_id: uuid.UUID
    owner_id: uuid.UUID

    # The specific transition state
    status: Literal["INITIALIZED", "UPLOADED", "FAILED", "PROCESSED"]
    
    # Metadata for the specific state
    storage_key: str = Field(..., description="The S3 key (e.g., raw/uuid.raw)")
    file_name: Optional[str] = None
    error_reason: Optional[str] = None

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    class Config:
        frozen = True  # Events should not be modified after creation
