"""Image domain service."""

import logging
import uuid
from asset_service.s3.client import get_s3_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from asset_service.db.models import ImageMetadataModel, ImageProcessingStatusModel
from shared_core.errors import NotFoundError, ForbiddenError
from shared_core.models.image import ImageSchemaPreview, RegisterImageRequest

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class ImageService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(
        self,
        req: RegisterImageRequest,
        raw_s3_path: str,
        raw_format: str,
    ) -> ImageMetadataModel:
        """Register a new image record and its initial PENDING status."""
        image = ImageMetadataModel(
            project_id=req.project_id,
            original_filename=req.original_filename,
            raw_s3_path=raw_s3_path,
            file_size_bytes=req.file_size_bytes,
            raw_format=raw_format,
        )
        self.db.add(image)
        await self.db.flush()  # get ID before commit

        status = ImageProcessingStatusModel(
            image_id=image.id,
            status="PENDING",
        )
        self.db.add(status)
        await self.db.commit()
        await self.db.refresh(image)
        return image

    async def get_by_s3_path(self, s3_path: str) -> ImageMetadataModel | None:
        """
        Lookup an image by its raw S3 path.
        Crucial for processing Rustfs/S3 webhooks where only the file key is known.
        """
        stmt = (
            select(ImageMetadataModel)
            .where(ImageMetadataModel.raw_s3_path == s3_path)
            # We load the status relationship immediately so the Kafka event
            # generator has access to image.status.status if needed.
            .options(selectinload(ImageMetadataModel.status))
        )
        result = await self.db.execute(stmt)
        return result.scalars().one_or_none()

    async def _get_display_url(self, image: ImageMetadataModel) -> str:
        s3_client = get_s3_client()
        status: str = image.status.status
        if status == "OPTIMIZED":
            bucket = "processed-images"
            # s3_key = image.processed_s3_path
            s3_key = image.preview_s3_path
        else:
            s3_key = image.raw_s3_path
            bucket = "raw-images"
        display_url = s3_client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": s3_key}, ExpiresIn=3600
        )
        return display_url

    async def list_for_project_with_urls(
        self, project_id: uuid.UUID
    ) -> list[ImageSchemaPreview]:
        images = await self.list_for_project(project_id)
        enriched_images = []

        for img in images:
            # Generate a GET URL valid for 1 hour
            display_url = await self._get_display_url(img)

            # Combine DB model with the temporary URL
            img_data = {
                "id": str(img.id),
                "original_filename": img.original_filename,
                "status": img.status.status,  # Accessing the relationship
                "display_url": display_url,
                "created_at": img.created_at.isoformat(),
            }
            enriched_images.append(img_data)

        return enriched_images

    async def list_for_project(self, project_id: uuid.UUID) -> list[ImageMetadataModel]:
        result = await self.db.execute(
            select(ImageMetadataModel)
            .where(ImageMetadataModel.project_id == project_id)
            .options(selectinload(ImageMetadataModel.status))
            .order_by(ImageMetadataModel.created_at.desc())
        )
        images = list(result.scalars().all())
        if images:
            image = images[0]
            log.info(f"first image status {image.status.status}")
        return images

    async def update_status(
        self,
        image_id: uuid.UUID,
        new_status: str,
        processed_s3_path: str | None = None,
        preview_s3_path: str | None = None,
        error_log: str | None = None,
    ) -> None:
        """Update the processing status of an image."""
        image = None
        status_row = await self.db.get(ImageProcessingStatusModel, image_id)
        if not status_row:
            raise NotFoundError(f"Status row for image {image_id} not found")
        status_row.status = new_status
        if error_log:
            status_row.last_error_log = error_log
        if processed_s3_path:
            image: ImageMetadataModel = await self.db.get(ImageMetadataModel, image_id)
            if image:
                image.processed_s3_path = processed_s3_path
        if preview_s3_path and image:
            image.preview_s3_path = preview_s3_path
        await self.db.commit()
