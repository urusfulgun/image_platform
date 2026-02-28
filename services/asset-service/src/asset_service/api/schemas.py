import uuid
from pydantic import BaseModel, Field, field_validator


class PresignResponse(BaseModel):
    image_id: uuid.UUID
    upload_url: str


class PresignRequest(BaseModel):
    file_name: str = Field(alias="fileName")
    file_size_bytes: int | None = Field(alias="fileSizeBytes")

    @field_validator("file_name")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Filename cannot be empty")
        # Basic security: prevent path traversal
        if "/" in v or "\\" in v:
            raise ValueError("Filename cannot contain directory paths")
        return v
