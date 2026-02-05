import uuid
from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlmodel import or_, select, and_, exists
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.engine.result import Result, ScalarResult, TupleResult
from sqlalchemy.exc import NoResultFound, MultipleResultsFound

# Internal modules
from api_gateway.db import get_db_session
from api_gateway.domain.models import (
    Project,
    Batch,
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
    try:
        user_res.scalar_one()
    except NoResultFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not synchronized. Please try again in a moment.",
        )
    except MultipleResultsFound:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Multiple user profiles found. Not Ok.",
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
        updated_at=now,
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
            detail="Failed to initialize project aggregate.",
        )

    return project


@router.patch("/{project_id}", response_model=Project)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    session: AsyncSession = Depends(get_db_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    # 1. Fetch the existing project within the ownership boundary
    # This prevents users from even knowing if a project exists if they don't own it
    stmt = select(Project).where(
        and_(Project.project_id == project_id, Project.owner_id == user_id)
    )
    result: TupleResult = await session.exec(stmt)
    try:
        db_project: Project = result.scalar_one()
    except NoResultFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or you do not have permission to modify it.",
        )
    except MultipleResultsFound:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Multiple projects not found. Not Ok.",
        )

    # 2. Extract only the fields explicitly provided in the request
    # exclude_unset=True is vital for PATCH to avoid overwriting with defaults
    update_data = data.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid update fields provided.",
        )

    # 3. Apply updates to the SQLModel instance
    # This automatically handles the mapping of dictionary keys to model attributes
    db_project.sqlmodel_update(update_data)

    # 4. Update the audit timestamp
    db_project.updated_at = datetime.now(timezone.utc)

    # 5. Persist the changes
    try:
        session.add(db_project)
        await session.commit()
        await session.refresh(db_project)
    except Exception:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the project.",
        )

    return db_project


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    # 1. Combined Query: Find project where (User is Owner) OR (User has ACL Entry)
    # We use a subquery for the ACL check to keep the main SELECT clean
    has_acl = exists().where(
        ProjectAccessControl.project_id == project_id,
        ProjectAccessControl.grantee_user_id == user_id,
    )

    stmt = select(Project).where(
        Project.project_id == project_id, or_(Project.owner_id == user_id, has_acl)
    )

    # 2. Execute and handle results
    result: TupleResult = await session.exec(stmt)
    project: Project | None = result.scalar_one_or_none()

    # 3. Security-First Response
    # Returning 404 for both 'Does not exist' and 'No permission' is a security best practice
    # to avoid revealing the existence of IDs to unauthorized users.
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

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
    # 1. Fetch image with strict ownership and project context
    # We join or verify the project_id to ensure the image actually belongs to the specified project
    # Context Safety: Join Image -> Batch and filter by Project + Owner
    stmt = (
        select(ImageMetadata)
        .join(Batch, ImageMetadata.batch_id == Batch.batch_id)
        .where(
            and_(
                ImageMetadata.image_id == image_id,
                Batch.project_id == project_id,  # Project Context Lock
                ImageMetadata.owner_id == user_id,  # Ownership Lock
            )
        )
    )

    # In SQLModel async, session.execute() is the standard for fetching
    result: TupleResult = await session.exec(stmt)
    try:
        image: ImageMetadata = result.scalar_one()
    except NoResultFound:
        # We return 404 to avoid leaking whether an image ID exists globally
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found in this project.",
        )
    except MultipleResultsFound:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Multiple images found. Not Ok",
        )

    # 2. Apply the logical rename
    # The physical S3 key (image_id.avif) remains unchanged
    image.display_name = data.new_display_name
    image.updated_at = datetime.now(timezone.utc)

    # 3. Commit the metadata change
    try:
        session.add(image)
        await session.commit()
        await session.refresh(image)
    except Exception:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update image metadata.",
        )

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


@router.delete(
    "/{project_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_image(
    project_id: uuid.UUID,
    image_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    # 1. Join with Batch to verify this image belongs to a project owned by the user
    # Context Safety: Ensure the path Image -> Batch -> Project is valid for this user
    stmt = (
        select(ImageMetadata)
        .join(Batch)
        .join(Project)
        .where(
            and_(
                ImageMetadata.image_id == image_id,
                Project.project_id == project_id,
                Project.owner_id == user_id,
            )
        )
    )

    result: TupleResult = await session.exec(stmt)
    image = result.scalar_one_or_none()

    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found in this project context",
        )

    # 2. Perform the deletion
    await session.delete(image)
    await session.commit()

    # Optional: Send 'ImageDeleted' event to Kafka for S3 cleanup
    # await producer.send("image-lifecycle", {"action": "DELETE", "id": str(image_id)})
