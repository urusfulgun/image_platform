"""Project domain services."""
import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from asset_service.db.models import ProjectModel
from shared_core.errors import NotFoundError, ForbiddenError
from shared_core.models.project import ProjectSchema, CreateProjectRequest


class ProjectService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, user_id: uuid.UUID, req: CreateProjectRequest) -> ProjectModel:
        project = ProjectModel(user_id=user_id, name=req.name)
        self.db.add(project)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def list_for_user(self, user_id: uuid.UUID) -> list[ProjectModel]:
        result = await self.db.execute(
            select(ProjectModel)
            .where(ProjectModel.user_id == user_id)
            .order_by(ProjectModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, project_id: uuid.UUID, user_id: uuid.UUID) -> ProjectModel:
        project = await self.db.get(
            ProjectModel,
            project_id,
            options=[selectinload(ProjectModel.images)],
        )
        if not project:
            raise NotFoundError(f"Project {project_id} not found")
        if project.user_id != user_id:
            raise ForbiddenError("Access denied")
        return project
