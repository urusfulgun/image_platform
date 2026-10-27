"""Tests for shared-core Pydantic models."""

import uuid
from datetime import datetime, timezone
import pytest

from shared_core.models.user import UserSchema
from shared_core.models.project import ProjectSchema, ProjectStatus
from shared_core.models.image import ImageSchema, ImageStatus


def test_user_schema_roundtrip():
    now = datetime.now(tz=timezone.utc)
    user = UserSchema(
        id=uuid.uuid4(),
        kc_sub=uuid.uuid4(),
        email="alice@example.com",
        created_at=now,
    )
    assert user.email == "alice@example.com"
    dumped = user.model_dump()
    restored = UserSchema(**dumped)
    assert restored.id == user.id


def test_project_status_enum():
    assert ProjectStatus.Created == "Created"
    assert ProjectStatus.Processing == "Processing"
    assert ProjectStatus.Completed == "Completed"


def test_project_schema_defaults():
    now = datetime.now(tz=timezone.utc)
    project = ProjectSchema(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="My Gallery",
        created_at=now,
    )
    assert project.status == ProjectStatus.Created


def test_image_status_enum():
    assert ImageStatus.PENDING == "PENDING"
    assert ImageStatus.OPTIMIZED == "OPTIMIZED"
    assert ImageStatus.FAILED == "FAILED"


def test_image_schema_optional_fields():
    now = datetime.now(tz=timezone.utc)
    img = ImageSchema(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        original_filename="photo.jpg",
        raw_s3_path="raw/photo.jpg",
        created_at=now,
    )
    assert img.processed_s3_path is None
    assert img.status == ImageStatus.PENDING
