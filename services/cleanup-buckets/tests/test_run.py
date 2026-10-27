"""Characterization tests for KafkaCleanupWorker.run (the consumer loop)."""

import json
import logging
from datetime import datetime

import pytest
from pydantic import ValidationError
from shared_core.events.kafka_events import ImageDeletedEvent

from tests.fakes import msg

STARTED = ["consumer.start", "producer.start"]
STOPPED = ["consumer.stop", "producer.stop"]


# --- Kafka config ----------------------------------------------------------


def test_consumer_subscribes_to_all_deleted_with_manual_commit(consumer):
    assert consumer.topics == ("image.all.deleted",)
    assert consumer.kwargs["bootstrap_servers"] == "kafka-test:9092"
    assert consumer.kwargs["group_id"] == "image-cleanup-group"
    assert consumer.kwargs["enable_auto_commit"] is False


def test_deserializer_turns_json_bytes_into_dict(consumer):
    assert consumer.kwargs["value_deserializer"](b'{"a": 1}') == {"a": 1}


@pytest.mark.known_bug
@pytest.mark.parametrize(
    ("raw", "error"), [(None, AttributeError), (b"not json", json.JSONDecodeError)]
)
def test_deserializer_raises_on_tombstone_or_invalid_json(consumer, raw, error):
    # CHARACTERIZATION: changes in R14 (poison messages must not kill the consumer)
    with pytest.raises(error):
        consumer.kwargs["value_deserializer"](raw)


def test_producer_serializer_turns_dict_into_json_bytes(producer):
    assert producer.kwargs["bootstrap_servers"] == "kafka-test:9092"
    serialize = producer.kwargs["value_serializer"]
    assert json.loads(serialize({"a": 1})) == {"a": 1}
    assert isinstance(serialize({"a": 1}), bytes)


# --- loop ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_event_is_handled_then_committed(
    worker, consumer, s3, calls, image_deleted_payload
):
    consumer.messages = [msg(image_deleted_payload())]

    await worker.run()

    assert len(s3.s3.deleted) == 3
    assert calls == [*STARTED, "commit", *STOPPED]


@pytest.mark.asyncio
async def test_invalid_payload_goes_to_dlq_then_is_committed(
    worker, consumer, producer, s3, calls, image_deleted_payload
):
    invalid = image_deleted_payload()
    del invalid["raw_s3_path"]
    with pytest.raises(ValidationError) as exc_info:
        ImageDeletedEvent(**invalid)
    follow_up = image_deleted_payload()
    consumer.messages = [msg(invalid), msg(follow_up)]

    await worker.run()

    producer.send_and_wait.assert_awaited_once()
    topic, payload = producer.send_and_wait.await_args.args
    assert topic == "image.cleanup.failed"
    assert set(payload) == {"original_event", "error", "failed_at", "processor_version"}
    assert payload["original_event"] == invalid
    assert payload["error"] == str(exc_info.value)
    assert payload["processor_version"] == "1.0.0-py3.14.2-cleanup"
    datetime.fromisoformat(payload["failed_at"])
    assert calls == [*STARTED, "send", "commit", "commit", *STOPPED]
    assert ("raw-test", follow_up["raw_s3_path"]) in s3.s3.deleted


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_failed_dlq_send_is_logged_and_still_committed(
    worker, consumer, producer, calls, image_deleted_payload, caplog
):
    # CHARACTERIZATION: changes in R19 (a failed DLQ send must not commit)
    invalid = image_deleted_payload()
    del invalid["raw_s3_path"]
    consumer.messages = [msg(invalid), msg(image_deleted_payload())]
    producer.send_and_wait.side_effect = RuntimeError("broker gone")

    with caplog.at_level(logging.CRITICAL, logger="KafkaCleanupWorker"):
        await worker.run()  # does not raise

    assert "Cleanup DLQ failure: broker gone" in caplog.text
    assert calls == [*STARTED, "commit", "commit", *STOPPED]


@pytest.mark.known_bug
@pytest.mark.parametrize(
    "value", [None, ["not", "a", "dict"]], ids=["tombstone", "list"]
)
@pytest.mark.asyncio
async def test_non_dict_value_kills_the_loop(
    worker, consumer, producer, s3, calls, image_deleted_payload, value
):
    # CHARACTERIZATION: changes in R14. `msg.value.get` in the except handler
    # raises AttributeError before the DLQ send, and it escapes run().
    consumer.messages = [msg(value), msg(image_deleted_payload())]

    with pytest.raises(AttributeError):
        await worker.run()

    producer.send_and_wait.assert_not_awaited()
    assert s3.s3.deleted == []
    assert calls == [*STARTED, "commit", *STOPPED]


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_output_topic_is_never_produced(
    worker, consumer, producer, image_deleted_payload
):
    # CHARACTERIZATION: changes in R12 (dead OUTPUT_TOPIC)
    consumer.messages = [msg(image_deleted_payload())]

    await worker.run()

    assert worker.OUTPUT_TOPIC == "image.bucket.deleted"
    producer.send_and_wait.assert_not_awaited()
