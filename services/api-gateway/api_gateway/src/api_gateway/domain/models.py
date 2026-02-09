from datetime import datetime, timezone
from uuid import UUID
import uuid
from api_gateway.utils.utc import get_utc_now
from sqlmodel import Field, SQLModel, Relationship, Column, JSON


class ShadowUser(SQLModel, table=True):
    __tablename__ = "shadow_users"

    user_id: UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    keycloak_sub: str = Field(unique=True, index=True)
    email: str
    created_at: datetime = Field(default_factory=get_utc_now)

    # Relationships
    owned_projects: list["Project"] = Relationship(back_populates="owner")
    shared_access: list["ProjectAccessControl"] = Relationship(back_populates="grantee")


class BatchStatusLookup(SQLModel, table=True):
    __tablename__ = "batch_statuses"
    status_id: str = Field(primary_key=True)  # PENDING, PROCESSING, etc.


class ImageStatusLookup(SQLModel, table=True):
    __tablename__ = "image_statuses"
    status_id: str = Field(primary_key=True)  # UPLOADED, CONVERTED, ERROR


class ResolutionTypeLookup(SQLModel, table=True):
    __tablename__ = "resolution_types"
    res_id: str = Field(primary_key=True)  # NORMAL, PREVIEW, THUMBNAIL


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    project_id: UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    owner_id: UUID = Field(foreign_key="shadow_users.user_id", index=True)
    name: str
    naming_template: str | None = None

    # target_resolutions as JSONB in Postgres
    target_resolutions: list[str] = Field(
        default=["normal"], sa_column=Column(JSON, nullable=False)
    )

    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    # Relationships
    owner: ShadowUser = Relationship(back_populates="owned_projects")
    batches: list["Batch"] = Relationship(back_populates="project")
    access_list: list["ProjectAccessControl"] = Relationship(back_populates="project")


class ProjectAccessControl(SQLModel, table=True):
    __tablename__ = "project_access_control"

    access_id: UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.project_id", index=True)
    grantee_user_id: UUID = Field(foreign_key="shadow_users.user_id", index=True)
    access_level: str = Field(default="READ_ONLY")
    granted_at: datetime = Field(default_factory=get_utc_now)

    project: Project = Relationship(back_populates="access_list")
    grantee: ShadowUser = Relationship(back_populates="shared_access")


class Batch(SQLModel, table=True):
    __tablename__ = "batches"

    batch_id: UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.project_id", index=True)
    status: str = Field(default="PENDING", foreign_key="batch_statuses.status_id")
    created_at: datetime = Field(default_factory=get_utc_now)

    project: Project = Relationship(back_populates="batches")
    images: list["ImageMetadata"] = Relationship(back_populates="batch")


class ImageMetadata(SQLModel, table=True):
    __tablename__ = "image_metadata"

    image_id: UUID = Field(default_factory=uuid.uuid7, primary_key=True)  # S3 Physical Filename
    batch_id: UUID = Field(foreign_key="batches.batch_id", index=True)
    owner_id: UUID = Field(foreign_key="shadow_users.user_id")

    original_filename: str
    display_name: str
    file_extension: str
    status: str = Field(default="UPLOADED", foreign_key="image_statuses.status_id")
    error_message: str | None = None
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)
    storage_key: str

    batch: Batch = Relationship(back_populates="images")
    variants: list["ImageVariant"] = Relationship(back_populates="parent_image")


class ImageVariant(SQLModel, table=True):
    __tablename__ = "image_variants"

    variant_id: UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    parent_image_id: UUID = Field(foreign_key="image_metadata.image_id", index=True)
    res_type: str = Field(foreign_key="resolution_types.res_id")
    s3_path: str
    file_size_bytes: int | None = None
    created_at: datetime = Field(default_factory=get_utc_now)

    parent_image: ImageMetadata = Relationship(back_populates="variants")
