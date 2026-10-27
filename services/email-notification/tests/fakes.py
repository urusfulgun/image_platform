"""Test double for the aiokafka consumer used by NotificationWorker."""

from types import SimpleNamespace
from unittest.mock import AsyncMock


def msg(value):
    """A consumer record as the worker sees it (already deserialized)."""
    return SimpleNamespace(value=value)


class FakeConsumer:
    """Records its constructor args and yields `messages` when iterated.

    `calls` logs start/commit/stop in the order they happen.
    """

    def __init__(self, *topics, **kwargs):
        self.topics = topics
        self.kwargs = kwargs
        self.messages = []
        self.calls = []
        self.start = AsyncMock(side_effect=lambda: self.calls.append("start"))
        self.commit = AsyncMock(side_effect=lambda: self.calls.append("commit"))
        self.stop = AsyncMock(side_effect=lambda: self.calls.append("stop"))

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for message in self.messages:
            yield message
