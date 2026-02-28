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

    async def list_for_project_with_urls(self, project_id: uuid.UUID) -> list[ImageSchemaPreview]:
        images = await self.list_for_project(project_id)
        enriched_images = []
        
        for img in images:
            s3_client = get_s3_client()
            # Generate a GET URL valid for 1 hour
            display_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': 'raw-images', 'Key': img.raw_s3_path},
                ExpiresIn=3600
            )
            
            # Combine DB model with the temporary URL
            img_data = {
                "id": str(img.id),
                "original_filename": img.original_filename,
                "status": img.status.status, # Accessing the relationship
                "display_url": display_url,
                "created_at": img.created_at.isoformat()
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
            log.info(f"first image status {image.status}")
        return images

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
