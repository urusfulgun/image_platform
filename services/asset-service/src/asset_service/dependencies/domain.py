from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from asset_service.db.session import get_db
from asset_service.domain.images import ImageService
from asset_service.domain.projects import ProjectService


def get_project_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ProjectService:
    return ProjectService(db)


def get_image_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ImageService:
    return ImageService(db)
