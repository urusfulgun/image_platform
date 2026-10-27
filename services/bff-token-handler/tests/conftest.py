"""Pytest configuration for BFF Token Handler tests."""

import os
from unittest.mock import AsyncMock

import pytest

# Required setting with no default. Set before any test imports bff_token_handler.
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "known_bug: characterization test pinning current buggy behaviour; "
        "the comment names the roadmap item that changes it",
    )


@pytest.fixture
def mock_redis():
    """Mock aioredis client."""
    redis = AsyncMock()
    redis.setex = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock()
    return redis
