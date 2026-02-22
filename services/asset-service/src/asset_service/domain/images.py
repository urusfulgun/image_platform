"""Image domain service."""
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from asset_service.db.models import ImageMetadataModel, ImageProcessingStatusModel
from shared_core.errors import NotFoundError, ForbiddenError
from shared_core.models.image import RegisterImageRequest


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

    async def list_for_project(self, project_id: uuid.UUID) -> list[ImageMetadataModel]:
        result = await self.db.execute(
            select(ImageMetadataModel)
            .where(ImageMetadataModel.project_id == project_id)
            .options(selectinload(ImageMetadataModel.status))
            .order_by(ImageMetadataModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        image_id: uuid.UUID,
        new_status: str,
        processed_s3_path: str | None = None,
        error_log: str | None = None,
    ) -> None:
        """Update the processing status of an image."""
        status_row = await self.db.get(ImageProcessingStatusModel, image_id)
        if not status_row:
            raise NotFoundError(f"Status row for image {image_id} not found")
        status_row.status = new_status
        if error_log:
            status_row.last_error_log = error_log
        if processed_s3_path:
            image = await self.db.get(ImageMetadataModel, image_id)
            if image:
                image.processed_s3_path = processed_s3_path
        await self.db.commit()
