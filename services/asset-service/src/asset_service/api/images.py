"""Images API router — handles image registration and presigned URL generation."""

import uuid
from pathlib import PurePosixPath
from typing import Annotated

from asset_service.kafka.producer import AssetKafkaProducer
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from asset_service.api.deps import get_local_user
from asset_service.db.models import UserModel
from asset_service.db.session import get_db
from asset_service.domain.images import ImageService
from asset_service.domain.projects import ProjectService
from asset_service.s3.client import generate_upload_presigned_url
from shared_core.events.kafka_events import ImageRawUploadedEvent
from shared_core.errors import NotFoundError, ForbiddenError
from shared_core.models.image import RegisterImageRequest, ImageSchema

router = APIRouter(prefix="/projects/{project_id}/images", tags=["images"])


def get_project_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ProjectService:
    return ProjectService(db)


def get_image_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ImageService:
    return ImageService(db)


def get_kafka_producer(request: Request) -> AssetKafkaProducer:
    # Accessing the producer from app.state (set during startup)
    return request.app.state.kafka_producer


class PresignRequest(BaseModel):
    file_name: str = Field(alias="fileName")
    file_size_bytes: int | None = None

    @field_validator("file_name")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Filename cannot be empty")
        # Basic security: prevent path traversal
        if "/" in v or "\\" in v:
            raise ValueError("Filename cannot contain directory paths")
        return v


class PresignResponse(BaseModel):
    image_id: uuid.UUID
    upload_url: str


@router.get("/", response_model=list[ImageSchema])
async def list_images(
    project_id: uuid.UUID,
    user: Annotated[UserModel, Depends(get_local_user)],
    project_svc: Annotated[ProjectService, Depends(get_project_service)],
    image_svc: Annotated[ImageService, Depends(get_image_service)],
):
    """List all images in a project."""
    # Verify ownership
    try:
        await project_svc.get(project_id=project_id, user_id=user.id)
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=403, detail=str(e))
    images = await image_svc.list_for_project(project_id)
    return [ImageSchema.model_validate(i) for i in images]


@router.post(
    "/presign", response_model=PresignResponse, status_code=status.HTTP_201_CREATED
)
async def get_presigned_upload_url(
    project_id: uuid.UUID,
    request_body: PresignRequest,
    user: Annotated[UserModel, Depends(get_local_user)],
    project_svc: Annotated[ProjectService, Depends(get_project_service)],
    image_svc: Annotated[ImageService, Depends(get_image_service)],
    kafka_producer: Annotated[AssetKafkaProducer, Depends(get_kafka_producer)],
):
    """Register a new image and return a pre-signed S3 upload URL.

    Flow:
    1. Create an image_metadata row with PENDING status.
    2. Generate a pre-signed PUT URL pointing at raw-images/<project_id>/<image_id>/<filename>.
    3. Publish an ImageRawUploadedEvent to Kafka.
    4. Return the pre-signed URL to the browser for direct upload.
    """
    # Verify project ownership
    try:
        await project_svc.get(project_id=project_id, user_id=user.id)
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=403, detail=str(e))

    # Build S3 object key
    suffix = PurePosixPath(request_body.file_name).suffix.lstrip(".") or "bin"
    s3_key = f"{project_id}/{uuid.uuid4()}/{request_body.file_name}"

    # Register image
    image = await image_svc.register(
        req=RegisterImageRequest(
            project_id=project_id,
            original_filename=request_body.file_name,
            file_size_bytes=request_body.file_size_bytes,
        ),
        raw_s3_path=s3_key,
        raw_format=suffix,
    )

    # Publish Kafka event
    event = ImageRawUploadedEvent(
        image_id=image.id,
        project_id=project_id,
        raw_s3_path=s3_key,
        raw_format=suffix,
        file_size_bytes=request_body.file_size_bytes,
    )
    await kafka_producer.publish_image_raw_uploaded(event)

    # Generate pre-signed URL
    upload_url = generate_upload_presigned_url(key=s3_key)

    return PresignResponse(image_id=image.id, upload_url=upload_url)
