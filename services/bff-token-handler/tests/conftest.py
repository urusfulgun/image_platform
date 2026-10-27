"""Pytest configuration for BFF Token Handler tests."""

import os
from unittest.mock import AsyncMock

import pytest

# Required setting with no default. Set before any test imports bff_token_handler.
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")


@pytest.fixture
def mock_redis():
    """Mock aioredis client."""
    redis = AsyncMock()
    redis.setex = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock()
    return redis
