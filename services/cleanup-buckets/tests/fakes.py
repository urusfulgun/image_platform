"""Test doubles for the aiokafka clients and the aioboto3 session."""

from types import SimpleNamespace
from unittest.mock import AsyncMock


def msg(value):
    """A consumer record as the worker sees it (already deserialized)."""
    return SimpleNamespace(value=value)


class FakeConsumer:
    """Records its constructor args and yields `messages` when iterated.

    Shares `calls` with the producer so tests can check ordering across both.
    """

    def __init__(self, calls, *topics, **kwargs):
        self.topics = topics
        self.kwargs = kwargs
        self.messages = []
        self.calls = calls
        self.start = AsyncMock(side_effect=lambda: calls.append("consumer.start"))
        self.commit = AsyncMock(side_effect=lambda: calls.append("commit"))
        self.stop = AsyncMock(side_effect=lambda: calls.append("consumer.stop"))

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for message in self.messages:
            yield message


class FakeProducer:
    def __init__(self, calls, **kwargs):
        self.kwargs = kwargs
        self.start = AsyncMock(side_effect=lambda: calls.append("producer.start"))
        self.stop = AsyncMock(side_effect=lambda: calls.append("producer.stop"))
        self.send_and_wait = AsyncMock(
            side_effect=lambda *a, **kw: calls.append("send")
        )


class FakeS3Client:
    def __init__(self, failing_keys):
        self.deleted = []
        self._failing_keys = failing_keys

    async def delete_object(self, *, Bucket, Key):
        self.deleted.append((Bucket, Key))
        if Key in self._failing_keys:
            raise self._failing_keys[Key]


class FakeS3Session:
    """Stands in for aioboto3.Session.

    `client_calls` records each `client(service, **cfg)`; `failing_keys` maps an
    object key to the exception its delete raises.
    """

    def __init__(self):
        self.client_calls = []
        self.failing_keys = {}
        self.s3 = FakeS3Client(self.failing_keys)

    def client(self, service, **cfg):
        self.client_calls.append((service, cfg))
        return _ClientContext(self.s3)


class _ClientContext:
    def __init__(self, client):
        self._client = client

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, *exc):
        return False
