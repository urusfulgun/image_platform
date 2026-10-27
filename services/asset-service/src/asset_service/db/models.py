"""SQLAlchemy async ORM models for AssetService.

Mirrors the init-db/postgres-image-metadata/01._init.sql schema.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    """Shadow user synced from KeyCloak via Debezium/Kafka."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid7
    )
    kc_sub: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    projects: Mapped[list[ProjectModel]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ProjectModel(Base):
    """A project groups a set of image uploads."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid7
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    user: Mapped[UserModel] = relationship(back_populates="projects")
    images: Mapped[list[ImageMetadataModel]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ImageMetadataModel(Base):
    """Insert-only static metadata for each uploaded image."""

    __tablename__ = "image_metadata"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid7
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_format: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_s3_path: Mapped[str] = mapped_column(Text, nullable=False)
    processed_format: Mapped[str] = mapped_column(String(255), nullable=True)
    processed_s3_path: Mapped[str | None] = mapped_column(Text)
    preview_s3_path: Mapped[str | None] = mapped_column(Text)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    dimensions_px: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    deleted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=None, nullable=True
    )
    deleted: Mapped[bool] = mapped_column(default=False)

    project: Mapped[ProjectModel] = relationship(back_populates="images")
    status: Mapped[ImageProcessingStatusModel] = relationship(
        back_populates="image", cascade="all, delete-orphan"
    )


class ImageProcessingStatusModel(Base):
    """High-volatility status table — HOT update optimised (fillfactor=80)."""

    __tablename__ = "image_processing_status"

    image_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("image_metadata.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_log: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    image: Mapped[ImageMetadataModel] = relationship(back_populates="status")
