"""Characterization tests for KafkaCleanupWorker.handle_cleanup."""

import logging

import pytest
from botocore.exceptions import ClientError
from shared_core.events.kafka_events import ImageDeletedEvent

from tests.conftest import S3_CONFIG


@pytest.mark.asyncio
async def test_deletes_raw_processed_and_preview_from_their_buckets(
    worker, s3, image_deleted_payload
):
    event = ImageDeletedEvent(**image_deleted_payload())

    await worker.handle_cleanup(event)

    assert sorted(s3.s3.deleted) == sorted(
        [
            ("raw-test", event.raw_s3_path),
            ("processed-test", event.processed_s3_path),
            ("processed-test", event.preview_s3_path),
        ]
    )


@pytest.mark.parametrize("missing", [None, ""], ids=["none", "empty"])
@pytest.mark.asyncio
async def test_missing_paths_are_skipped(worker, s3, image_deleted_payload, missing):
    event = ImageDeletedEvent(
        **image_deleted_payload(processed_s3_path=missing, preview_s3_path=missing)
    )

    await worker.handle_cleanup(event)

    assert s3.s3.deleted == [("raw-test", event.raw_s3_path)]


@pytest.mark.asyncio
async def test_empty_raw_path_is_skipped(worker, s3, image_deleted_payload):
    event = ImageDeletedEvent(**image_deleted_payload(raw_s3_path=""))

    await worker.handle_cleanup(event)

    assert ("raw-test", "") not in s3.s3.deleted
    assert len(s3.s3.deleted) == 2


@pytest.mark.asyncio
async def test_s3_client_is_created_with_s3_config(worker, s3, image_deleted_payload):
    await worker.handle_cleanup(ImageDeletedEvent(**image_deleted_payload()))

    assert s3.client_calls == [("s3", S3_CONFIG)]


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_a_new_s3_client_is_created_per_event(worker, s3, image_deleted_payload):
    # CHARACTERIZATION: changes in R11 (one S3 client per event, not shared)
    await worker.handle_cleanup(ImageDeletedEvent(**image_deleted_payload()))
    await worker.handle_cleanup(ImageDeletedEvent(**image_deleted_payload()))

    assert len(s3.client_calls) == 2


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_s3_delete_error_is_swallowed(worker, s3, image_deleted_payload, caplog):
    # CHARACTERIZATION: changes in R19 (S3 failures go to a DLQ or retry).
    # gather(return_exceptions=True) only logs; the other deletes still run.
    event = ImageDeletedEvent(**image_deleted_payload())
    s3.failing_keys[event.processed_s3_path] = ClientError(
        {"Error": {"Code": "InternalError", "Message": "boom"}}, "DeleteObject"
    )

    with caplog.at_level(logging.INFO, logger="KafkaCleanupWorker"):
        await worker.handle_cleanup(event)  # does not raise

    assert len(s3.s3.deleted) == 3
    assert f"S3 deletion error for {event.image_id}" in caplog.text
    assert f"Purged S3 assets for image: {event.image_id}" in caplog.text
