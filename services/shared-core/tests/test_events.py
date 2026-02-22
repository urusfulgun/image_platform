"""Tests for Kafka event schemas."""
import uuid
from datetime import datetime, timezone

from shared_core.events.kafka_events import (
    UserRegisteredEvent,
    ImageRawUploadedEvent,
    ImageAvifReadyEvent,
    CleanupRequestedEvent,
)


def test_user_registered_event_defaults():
    event = UserRegisteredEvent(
        kc_sub=uuid.uuid4(),
        email="bob@example.com",
    )
    assert event.event_id is not None
    assert event.email == "bob@example.com"
    assert event.occurred_at is not None


def test_image_raw_uploaded_event():
    image_id = uuid.uuid4()
    project_id = uuid.uuid4()
    event = ImageRawUploadedEvent(
        image_id=image_id,
        project_id=project_id,
        raw_s3_path="raw/photo.jpg",
        raw_format="jpeg",
        file_size_bytes=1024000,
    )
    assert event.image_id == image_id
    assert event.raw_format == "jpeg"
    assert event.file_size_bytes == 1024000


def test_image_avif_ready_event():
    event = ImageAvifReadyEvent(
        image_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        processed_s3_path="processed/photo.avif",
    )
    assert event.processed_s3_path == "processed/photo.avif"


def test_event_json_roundtrip():
    event = ImageRawUploadedEvent(
        image_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        raw_s3_path="raw/test.png",
        raw_format="png",
    )
    json_str = event.model_dump_json()
    restored = ImageRawUploadedEvent.model_validate_json(json_str)
    assert restored.image_id == event.image_id
    assert restored.raw_format == event.raw_format


def test_cleanup_requested_event():
    event = CleanupRequestedEvent(
        image_id=uuid.uuid4(),
        raw_s3_path="raw/old.jpg",
    )
    assert event.raw_s3_path == "raw/old.jpg"
