"""Images API router — handles image registration and presigned URL generation."""
import uuid
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from asset_service.api.deps import get_local_user
from asset_service.db.models import UserModel
from asset_service.db.session import get_db
from asset_service.domain.images import ImageService
from asset_service.domain.projects import ProjectService
from asset_service.kafka.producer import producer as kafka_producer
from asset_service.s3.client import generate_upload_presigned_url
from shared_core.events.kafka_events import ImageRawUploadedEvent
from shared_core.errors import NotFoundError, ForbiddenError
from shared_core.models.image import RegisterImageRequest, ImageSchema

router = APIRouter(prefix="/projects/{project_id}/images", tags=["images"])


class PresignRequest(BaseModel):
    filename: str
    file_size_bytes: int | None = None


class PresignResponse(BaseModel):
    image_id: uuid.UUID
    upload_url: str


@router.get("/", response_model=list[ImageSchema])
async def list_images(
    project_id: uuid.UUID,
    user: Annotated[UserModel, Depends(get_local_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List all images in a project."""
    # Verify ownership
    proj_svc = ProjectService(db)
    try:
        await proj_svc.get(project_id=project_id, user_id=user.id)
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=403, detail=str(e))
    img_svc = ImageService(db)
    images = await img_svc.list_for_project(project_id)
    return [ImageSchema.model_validate(i) for i in images]


@router.post("/presign", response_model=PresignResponse, status_code=201)
async def get_presigned_upload_url(
    project_id: uuid.UUID,
    req: PresignRequest,
    user: Annotated[UserModel, Depends(get_local_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Register a new image and return a pre-signed S3 upload URL.

    Flow:
    1. Create an image_metadata row with PENDING status.
    2. Generate a pre-signed PUT URL pointing at raw-images/<project_id>/<image_id>/<filename>.
    3. Publish an ImageRawUploadedEvent to Kafka.
    4. Return the pre-signed URL to the browser for direct upload.
    """
    # Verify project ownership
    proj_svc = ProjectService(db)
    try:
        await proj_svc.get(project_id=project_id, user_id=user.id)
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=403, detail=str(e))

    # Build S3 object key
    suffix = PurePosixPath(req.filename).suffix.lstrip(".") or "bin"
    s3_key = f"{project_id}/{uuid.uuid4()}/{req.filename}"

    # Register image
    img_svc = ImageService(db)
    image = await img_svc.register(
        req=RegisterImageRequest(
            project_id=project_id,
            original_filename=req.filename,
            file_size_bytes=req.file_size_bytes,
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
        file_size_bytes=req.file_size_bytes,
    )
    await kafka_producer.publish_image_raw_uploaded(event)

    # Generate pre-signed URL
    upload_url = generate_upload_presigned_url(key=s3_key)

    return PresignResponse(image_id=image.id, upload_url=upload_url)
