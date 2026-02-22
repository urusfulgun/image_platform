"""Pytest configuration for BFF Token Handler tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_redis():
    """Mock aioredis client."""
    redis = AsyncMock()
    redis.setex = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock()
    return redis
