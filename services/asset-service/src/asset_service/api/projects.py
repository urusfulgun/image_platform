"""Projects API router."""

import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from shared_core.utils.endpoint.rs_dpop import validate_dpop
from sqlalchemy.ext.asyncio import AsyncSession

from asset_service.api.deps import get_local_user
from asset_service.db.models import UserModel
from asset_service.db.session import get_db
from asset_service.domain.projects import ProjectService
from shared_core.errors import NotFoundError, ForbiddenError
from shared_core.models.project import CreateProjectRequest, ProjectSchema
from asset_service.dependencies.domain import get_image_service, get_project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get(
    "/",
    response_model=list[ProjectSchema],
    dependencies=[Depends(validate_dpop)],
)
async def list_projects(
    user: Annotated[UserModel, Depends(get_local_user)],
    project_svc: Annotated[ProjectService, Depends(get_project_service)],
):
    """List all projects belonging to the current user."""
    projects = await project_svc.list_for_user(user.id)
    return [ProjectSchema.model_validate(p) for p in projects]


@router.post(
    "/",
    response_model=ProjectSchema,
    dependencies=[Depends(validate_dpop)],
    status_code=201,
)
async def create_project(
    req: CreateProjectRequest,
    user: Annotated[UserModel, Depends(get_local_user)],
    project_svc: Annotated[ProjectService, Depends(get_project_service)],
):
    """Create a new project for the current user."""
    project = await project_svc.create(user_id=user.id, req=req)
    return ProjectSchema.model_validate(project)


@router.get(
    "/{project_id}",
    dependencies=[Depends(validate_dpop)],
    response_model=ProjectSchema,
)
async def get_project(
    project_id: uuid.UUID,
    user: Annotated[UserModel, Depends(get_local_user)],
    project_svc: Annotated[ProjectService, Depends(get_project_service)],
):
    """Get a specific project (only accessible by its owner)."""
    try:
        project = await project_svc.get(project_id=project_id, user_id=user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=e.message)
    return ProjectSchema.model_validate(project)
