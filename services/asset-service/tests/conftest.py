"""Pytest configuration for AssetService tests."""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock


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
