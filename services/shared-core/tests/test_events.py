"""Tests for Kafka event schemas."""

import uuid

from shared_core.events.kafka_events import (
    CleanupRequestedEvent,
    ImageAvifReadyEvent,
    ImageRawUploadedEvent,
)
from shared_core.schemas.debezium.events import KeycloakUserEvent


def test_keycloak_user_event_from_debezium_payload():
    kc_id = str(uuid.uuid4())
    event = KeycloakUserEvent.model_validate(
        {"id": kc_id, "email": "bob@example.com", "__op": "c", "__deleted": "false"}
    )
    assert event.sub == kc_id
    assert event.email == "bob@example.com"
    assert event.op == "c"
    assert event.deleted is False
    assert event.enabled is True


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
        preview_s3_path="processed/preview_tile.avif",
        processed_format="avif",
    )
    assert event.processed_s3_path == "processed/photo.avif"
    assert event.preview_s3_path == "processed/preview_tile.avif"
    assert event.processed_format == "avif"


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


def test_keycloak_user_event_deleted_flag_parsed_as_bool():
    event = KeycloakUserEvent.model_validate(
        {"id": str(uuid.uuid4()), "__op": "d", "__deleted": "true"}
    )
    assert event.deleted is True
