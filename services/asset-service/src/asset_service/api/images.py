"""Images API router — handles image registration and presigned URL generation."""

import logging
import uuid
from pathlib import PurePosixPath
from typing import Annotated

from fastapi.responses import JSONResponse
from shared_core.utils.endpoint.rs_dpop import validate_dpop
from shared_core.utils.s3_object_key import get_s3_object_key

from asset_service.api.schemas import PresignRequest, PresignResponse
from asset_service.dependencies.clients import get_kafka_producer
from asset_service.dependencies.domain import get_image_service, get_project_service
from asset_service.kafka.producer import AssetKafkaProducer
from fastapi import APIRouter, Depends, HTTPException, Request, status

from asset_service.api.deps import get_local_user
from asset_service.db.models import ImageMetadataModel, UserModel
from asset_service.domain.images import ImageService
from asset_service.domain.projects import ProjectService
from asset_service.s3.client import generate_upload_presigned_url
from shared_core.events.kafka_events import ImageDeletedEvent, ImageRawUploadedEvent
from shared_core.errors import NotFoundError, ForbiddenError
from shared_core.models.image import (
    ImageSchemaPreview,
    RegisterImageRequest,
    ImageSchema,
)

router = APIRouter(prefix="/projects/{project_id}/images", tags=["images"])

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_image_schema_from_model(image_model: ImageMetadataModel) -> ImageSchema:
    image_schema = ImageSchema(
        id=image_model.id,
        project_id=image_model.project_id,
        original_filename=image_model.original_filename,
        raw_s3_path=image_model.raw_s3_path,
        processed_s3_path=image_model.processed_s3_path,
        file_size_bytes=image_model.file_size_bytes,
        dimensions_px=image_model.dimensions_px,
        status=image_model.status.status,
        retry_count=image_model.status.retry_count,
        last_error_log=image_model.status.last_error_log,
        created_at=image_model.created_at,
    )
    return image_schema


@router.get(
    "/",
    response_model=list[ImageSchema],
    dependencies=[Depends(validate_dpop)],
)
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
    return [get_image_schema_from_model(i) for i in images]


@router.get(
    "/preview",
    response_model=list[ImageSchemaPreview],
    dependencies=[Depends(validate_dpop)],
)
async def list_images_preview(
    project_id: uuid.UUID,
    user: Annotated[UserModel, Depends(get_local_user)],
    project_svc: Annotated[ProjectService, Depends(get_project_service)],
    image_svc: Annotated[ImageService, Depends(get_image_service)],
):
    """List all images in a project with url."""
    # Verify ownership
    try:
        await project_svc.get(project_id=project_id, user_id=user.id)
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=403, detail=str(e))
    images = await image_svc.list_for_project_with_urls(project_id)
    return images


@router.post(
    "/presign",
    response_model=PresignResponse,
    dependencies=[Depends(validate_dpop)],
    status_code=status.HTTP_201_CREATED,
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
    log.info("Presign process started.")
    try:
        project = await project_svc.get(project_id=project_id, user_id=user.id)
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=403, detail=str(e))

    # Build S3 object key
    suffix = PurePosixPath(request_body.file_name).suffix.lstrip(".") or "bin"
    s3_key = get_s3_object_key(project_id, f'normal.{suffix}')

    log.info(f"Project UUID {project.id}")

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
    await kafka_producer.publish_image_raw_presign_link_generated_topic(event)

    # Generate pre-signed URL
    upload_url = generate_upload_presigned_url(key=s3_key)

    return PresignResponse(image_id=image.id, upload_url=upload_url)


@router.delete(
    "/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(validate_dpop)],
)
async def delete_image(
    project_id: uuid.UUID,
    image_id: uuid.UUID,
    user: Annotated[UserModel, Depends(get_local_user)],
    project_svc: Annotated[ProjectService, Depends(get_project_service)],
    image_svc: Annotated[ImageService, Depends(get_image_service)],
    kafka_producer: Annotated[AssetKafkaProducer, Depends(get_kafka_producer)],
):
    """
    Delete an image from a project.
    
    This verifies that the project belongs to the user and that 
    the image belongs to the specified project before deletion.
    """
    # 1. Verify project ownership/access
    try:
        await project_svc.get(project_id=project_id, user_id=user.id)
    except (NotFoundError, ForbiddenError) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    # 2. Perform deletion
    # Note: Depending on your ImageService implementation, you might want to 
    # check if the image exists and belongs to project_id first.
    try:
        images_to_delete = await image_svc.delete(image_id=image_id, project_id=project_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Image {image_id} not found in project {project_id}"
        )
    except Exception as e:
        log.error(f"Failed to delete image {image_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error during deletion"
        )
    
    event = ImageDeletedEvent(
        image_id=image_id,
        project_id=project_id,
        raw_s3_path=images_to_delete.raw_s3_path,
        processed_s3_path=images_to_delete.processed_s3_path,
        preview_s3_path=images_to_delete.preview_s3_path
    )
    
    # If the DB commit succeeds but Kafka fails, the image is "hidden" from the user,
    # but S3 isn't cleaned up. You might want a periodic reconciliation job for this.
    await kafka_producer.publish_image_deleted_topic(event)

    log.info(f"Image {image_id} marked for deletion and cleanup event published.")

    return None
