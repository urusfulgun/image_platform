"""Pytest configuration for cleanup-buckets tests."""

import importlib
import uuid

import pytest
from shared_core.events.kafka_events import ImageDeletedEvent

from tests.fakes import FakeConsumer, FakeProducer, FakeS3Session

# `cleanup_buckets.main` is also the name of a stub function in the package
# __init__, so `from cleanup_buckets import main` would return that function.
worker_module = importlib.import_module("cleanup_buckets.main")
KafkaCleanupWorker = worker_module.KafkaCleanupWorker

S3_CONFIG = {"endpoint_url": "http://s3-test:9000", "region_name": "test-region"}


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "known_bug: characterization test pinning current buggy behaviour; "
        "the comment names the roadmap item that changes it",
    )


@pytest.fixture
def calls(monkeypatch):
    """Patch the aiokafka clients with fakes; returns their shared call log."""
    log = []
    monkeypatch.setattr(
        worker_module, "AIOKafkaConsumer", lambda *t, **kw: FakeConsumer(log, *t, **kw)
    )
    monkeypatch.setattr(
        worker_module, "AIOKafkaProducer", lambda **kw: FakeProducer(log, **kw)
    )
    return log


@pytest.fixture
def worker(calls):
    w = KafkaCleanupWorker(
        kafka_bootstrap="kafka-test:9092",
        s3_config=S3_CONFIG,
        raw_bucket="raw-test",
        processed_bucket="processed-test",
    )
    w.session = FakeS3Session()
    return w


@pytest.fixture
def consumer(worker):
    return worker.consumer


@pytest.fixture
def producer(worker):
    return worker.producer


@pytest.fixture
def s3(worker):
    return worker.session


@pytest.fixture
def image_deleted_payload():
    """Factory for an image.all.deleted payload as it arrives off the wire."""

    def make(**overrides):
        image_id = uuid.uuid4()
        fields = {
            "image_id": image_id,
            "project_id": uuid.uuid4(),
            "raw_s3_path": f"raw/{image_id}.jpg",
            "processed_s3_path": f"processed/{image_id}.avif",
            "preview_s3_path": f"previews/{image_id}.avif",
        }
        fields.update(overrides)
        return ImageDeletedEvent(**fields).model_dump(mode="json")

    return make
