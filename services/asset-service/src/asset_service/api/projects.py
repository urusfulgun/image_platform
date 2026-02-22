"""Projects API router."""
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from asset_service.api.deps import get_local_user
from asset_service.db.models import UserModel
from asset_service.db.session import get_db
from asset_service.domain.projects import ProjectService
from shared_core.errors import NotFoundError, ForbiddenError
from shared_core.models.project import CreateProjectRequest, ProjectSchema

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/", response_model=list[ProjectSchema])
async def list_projects(
    user: Annotated[UserModel, Depends(get_local_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List all projects belonging to the current user."""
    svc = ProjectService(db)
    projects = await svc.list_for_user(user.id)
    return [ProjectSchema.model_validate(p) for p in projects]


@router.post("/", response_model=ProjectSchema, status_code=201)
async def create_project(
    req: CreateProjectRequest,
    user: Annotated[UserModel, Depends(get_local_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new project for the current user."""
    svc = ProjectService(db)
    project = await svc.create(user_id=user.id, req=req)
    return ProjectSchema.model_validate(project)


@router.get("/{project_id}", response_model=ProjectSchema)
async def get_project(
    project_id: uuid.UUID,
    user: Annotated[UserModel, Depends(get_local_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get a specific project (only accessible by its owner)."""
    svc = ProjectService(db)
    try:
        project = await svc.get(project_id=project_id, user_id=user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=e.message)
    return ProjectSchema.model_validate(project)
