import uuid
from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlmodel import select, and_
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.engine.result import Result, ScalarResult, TupleResult

# Internal modules
from api_gateway.db import get_db_session
from api_gateway.domain.models import (
    Project,
    ImageMetadata,
    ProjectAccessControl,
    ShadowUser,
    get_utc_now,
)
from api_gateway.api.schemas import (
    ProjectCreate,
    ProjectUpdate,
    ImageRename,
    AccessGrant,
)

router = APIRouter(prefix="/projects", tags=["Project Aggregate"])


# Helper for current user (Extracted from DPoP Token by middleware)
async def get_current_user_id() -> uuid.UUID:
    # Logic to return user_id from shadow_users table
    ...


# --- Project Operations ---


@router.post("/", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    session: AsyncSession = Depends(get_db_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    # 1. Verify that the Shadow User exists in the local database.
    # This user should have been created via the Kafka sync from Keycloak.
    user_stmt = select(ShadowUser).where(ShadowUser.user_id == user_id)
    user_res: TupleResult = await session.exec(user_stmt)
    if not user_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not synchronized. Please try again in a moment."
        )

    # 2. Initialize the Project Aggregate Root
    # We use native uuid.uuid7() and timezone-aware UTC datetimes.
    now = get_utc_now()
    
    project = Project(
        project_id=uuid.uuid7(),
        owner_id=user_id,
        name=data.name,
        target_resolutions=data.target_resolutions,
        naming_template=data.naming_template,
        created_at=now,
        updated_at=now
    )

    # 3. Persistence
    try:
        session.add(project)
        await session.commit()
        # Refresh to ensure we return the object with DB-generated defaults if any
        await session.refresh(project)
    except Exception as e:
        await session.rollback()
        # Log error here
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize project aggregate."
        )

    return project


@router.patch("/{project_id}", response_model=Project)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    session: AsyncSession = Depends(get_db_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    # 1. Fetch the existing project
    stmt = select(Project).where(
        and_(Project.project_id == project_id, Project.owner_id == user_id)
    )
    result: TupleResult = await session.exec(stmt)
    db_project: Project | None = result.scalar_one_or_none()

    if not db_project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or you are not the owner",
        )

    # 2. Extract only the fields provided in the request
    update_data = data.model_dump(exclude_unset=True)

    # 3. Apply updates and set the new timestamp
    db_project.sqlmodel_update(update_data)
    db_project.updated_at = datetime.now(timezone.utc)

    # 4. Save and return
    session.add(db_project)
    await session.commit()
    await session.refresh(db_project)

    return db_project


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    # Check ownership OR ACL read access
    stmt = select(Project).where(Project.project_id == project_id)
    result: TupleResult = await session.exec(stmt)
    project: Project | None = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Security check
    if project.owner_id != user_id:
        acl_stmt = select(ProjectAccessControl).where(
            and_(
                ProjectAccessControl.project_id == project_id,
                ProjectAccessControl.grantee_user_id == user_id,
            )
        )
        acl_res = await session.exec(acl_stmt)
        if not acl_res.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Access denied")

    return project


# --- Image Metadata CRUD (Renaming) ---


@router.patch("/{project_id}/images/{image_id}", response_model=ImageMetadata)
async def rename_image(
    project_id: uuid.UUID,
    image_id: uuid.UUID,
    data: ImageRename,
    session: AsyncSession = Depends(get_db_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    # Fetch image and verify project/owner context
    stmt = select(ImageMetadata).where(
        and_(
            ImageMetadata.image_id == image_id,
            ImageMetadata.owner_id == user_id,  # Only owner can rename
        )
    )
    result: TupleResult = await session.exec(stmt)
    image: ImageMetadata = result.scalar_one_or_none()

    if not image:
        raise HTTPException(status_code=404, detail="Image metadata not found")

    image.display_name = data.new_display_name
    image.updated_at = datetime.now(timezone.utc)

    session.add(image)
    await session.commit()
    await session.refresh(image)
    return image


# --- Access Control (Sharing) ---


@router.post("/{project_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def grant_read_access(
    project_id: uuid.UUID,
    grant_raw: dict,  # Receive raw to pass context to Pydantic
    session: AsyncSession = Depends(get_db_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    # 1. Validate the Grant with current user context (prevents self-sharing)
    try:
        grant = AccessGrant.model_validate(
            grant_raw, context={"current_user_id": user_id}
        )
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

    # 2. Verify the requester owns the project
    project_stmt = select(Project).where(
        and_(Project.project_id == project_id, Project.owner_id == user_id)
    )
    project_res: TupleResult = await session.exec(project_stmt)
    if not project_res.scalar_one_or_none():
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Only project owners can manage permissions.",
        )

    # 3. Verify the Target User (Grantee) exists in the Shadow User table
    user_stmt = select(ShadowUser).where(ShadowUser.user_id == grant.target_user_id)
    user_res: TupleResult = await session.exec(user_stmt)
    if not user_res.scalar_one_or_none():
        raise HTTPException(
            status_code=404, detail="The target user does not exist in the system."
        )

    # 4. Create the ACL entry (Using uuid7 natively)
    acl_entry = ProjectAccessControl(
        access_id=uuid.uuid7(),
        project_id=project_id,
        grantee_user_id=grant.target_user_id,
        access_level=grant.access_level,
    )

    # 5. Atomic Commit
    try:
        session.add(acl_entry)
        await session.commit()
    except Exception:  # Handle potential unique constraint violations
        await session.rollback()
        # If user already has access, we can silently succeed or update
        raise HTTPException(
            status_code=409, detail="User already has access to this project."
        )
