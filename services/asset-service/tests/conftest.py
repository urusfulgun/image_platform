"""Pytest configuration for AssetService tests."""

import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

# Required settings with no default. Set before any test imports asset_service.
os.environ.setdefault("S3_ACCESS_KEY", "test-access-key")
os.environ.setdefault("S3_SECRET_KEY", "test-secret-key")
os.environ.setdefault("RUSTFS_WEBHOOK_TOKEN", "test-webhook-token")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "known_bug: characterization test pinning current buggy behaviour; "
        "the comment names the roadmap item that changes it",
    )


@pytest.fixture
def sample_user_id():
    return uuid.uuid4()


@pytest.fixture
def sample_project_id():
    return uuid.uuid4()


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    return session
