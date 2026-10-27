"""Pytest configuration for email-notification tests."""

import importlib
import uuid
from unittest.mock import AsyncMock

import pytest

from shared_core.events.kafka_events import ImageAvifReadyEvent
from tests.fakes import FakeConsumer

# `email_notification.main` is also the name of a stub function in the package
# __init__, so `from email_notification import main` would return that function.
worker_module = importlib.import_module("email_notification.main")
NotificationWorker = worker_module.NotificationWorker


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "known_bug: characterization test pinning current buggy behaviour; "
        "the comment names the roadmap item that changes it",
    )


@pytest.fixture
def consumers(monkeypatch):
    """Patch AIOKafkaConsumer with FakeConsumer; returns every instance created."""
    created = []

    def factory(*topics, **kwargs):
        consumer = FakeConsumer(*topics, **kwargs)
        created.append(consumer)
        return consumer

    monkeypatch.setattr(worker_module, "AIOKafkaConsumer", factory)
    return created


@pytest.fixture
def worker(consumers):
    return NotificationWorker(
        kafka_bootstrap="kafka-test:9092",
        smtp_host="smtp-test",
        smtp_port=2525,
        from_email="sender@test.local",
    )


@pytest.fixture
def consumer(worker):
    return worker.consumer


@pytest.fixture
def smtp_send(monkeypatch):
    """Patch aiosmtplib.send where the worker imported it."""
    send = AsyncMock()
    monkeypatch.setattr(worker_module, "send", send)
    return send


@pytest.fixture
def avif_ready_payload():
    """Factory for an image.avif.ready payload as it arrives off the wire."""

    def make(**overrides):
        image_id = uuid.uuid4()
        fields = {
            "image_id": image_id,
            "project_id": uuid.uuid4(),
            "processed_s3_path": f"processed/{image_id}.avif",
            "preview_s3_path": f"previews/{image_id}.avif",
            "processed_format": "avif",
        }
        fields.update(overrides)
        return ImageAvifReadyEvent(**fields).model_dump(mode="json")

    return make
