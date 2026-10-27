"""Characterization tests for NotificationWorker.run (the consumer loop)."""

import json
import logging

import pytest
from aiosmtplib import SMTPException

from tests.fakes import msg

# --- consumer config -------------------------------------------------------


def test_consumer_subscribes_to_avif_ready_with_manual_commit(consumer):
    assert consumer.topics == ("image.avif.ready",)
    assert consumer.kwargs["bootstrap_servers"] == "kafka-test:9092"
    assert consumer.kwargs["group_id"] == "notification-group"
    assert consumer.kwargs["enable_auto_commit"] is False


def test_deserializer_turns_json_bytes_into_dict(consumer):
    deserialize = consumer.kwargs["value_deserializer"]
    assert deserialize(b'{"image_id": "abc"}') == {"image_id": "abc"}


@pytest.mark.known_bug
def test_deserializer_raises_on_tombstone(consumer):
    # CHARACTERIZATION: changes in R14 (tombstones must not kill the consumer)
    with pytest.raises(AttributeError):
        consumer.kwargs["value_deserializer"](None)


@pytest.mark.known_bug
def test_deserializer_raises_on_invalid_json(consumer):
    # CHARACTERIZATION: changes in R14 (poison messages must not kill the consumer)
    with pytest.raises(json.JSONDecodeError):
        consumer.kwargs["value_deserializer"](b"not json")


# --- loop ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_event_is_sent_then_committed(
    worker, consumer, smtp_send, avif_ready_payload
):
    consumer.messages = [msg(avif_ready_payload())]

    await worker.run()

    smtp_send.assert_awaited_once()
    assert consumer.calls == ["start", "commit", "stop"]


@pytest.mark.asyncio
async def test_each_message_is_committed(
    worker, consumer, smtp_send, avif_ready_payload
):
    consumer.messages = [msg(avif_ready_payload()), msg(avif_ready_payload())]

    await worker.run()

    assert smtp_send.await_count == 2
    assert consumer.calls == ["start", "commit", "commit", "stop"]


@pytest.mark.asyncio
async def test_invalid_payload_is_logged_skipped_and_committed(
    worker, consumer, smtp_send, avif_ready_payload, caplog
):
    invalid = avif_ready_payload()
    del invalid["project_id"]
    consumer.messages = [msg(invalid), msg(avif_ready_payload())]

    with caplog.at_level(logging.ERROR, logger="NotificationWorker"):
        await worker.run()

    assert smtp_send.await_count == 1  # only the valid follow-up
    assert consumer.calls == ["start", "commit", "commit", "stop"]
    assert f"Failed to notify for image {invalid['image_id']}" in caplog.text


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_smtp_failure_is_committed_and_lost(
    worker, consumer, smtp_send, avif_ready_payload, caplog
):
    # CHARACTERIZATION: changes in R19 (SMTP failures retry or go to a DLQ)
    failing = avif_ready_payload()
    consumer.messages = [msg(failing), msg(avif_ready_payload())]
    smtp_send.side_effect = [SMTPException("mailpit down"), None]

    with caplog.at_level(logging.ERROR, logger="NotificationWorker"):
        await worker.run()

    assert smtp_send.await_count == 2
    assert consumer.calls == ["start", "commit", "commit", "stop"]
    assert (
        f"Failed to notify for image {failing['image_id']}: mailpit down" in caplog.text
    )


@pytest.mark.known_bug
@pytest.mark.parametrize(
    "value", [None, ["not", "a", "dict"]], ids=["tombstone", "list"]
)
@pytest.mark.asyncio
async def test_non_dict_value_kills_the_loop(
    worker, consumer, smtp_send, avif_ready_payload, value
):
    # CHARACTERIZATION: changes in R14. `msg.value.get` in the except handler
    # raises AttributeError, which escapes run(); later messages are never read.
    consumer.messages = [msg(value), msg(avif_ready_payload())]

    with pytest.raises(AttributeError):
        await worker.run()

    smtp_send.assert_not_awaited()
    assert consumer.calls == ["start", "commit", "stop"]


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_redelivered_event_sends_a_second_email(
    worker, consumer, smtp_send, avif_ready_payload
):
    # CHARACTERIZATION: changes in R15 (idempotent processing, no duplicate emails)
    payload = avif_ready_payload()
    consumer.messages = [msg(payload), msg(dict(payload))]

    await worker.run()

    assert smtp_send.await_count == 2
    first, second = (call.args[0] for call in smtp_send.await_args_list)
    assert first["Subject"] == second["Subject"]
