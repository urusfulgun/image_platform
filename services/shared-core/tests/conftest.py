"""Pytest configuration for shared-core tests."""

import pytest


@pytest.fixture
def sample_uuid():
    import uuid

    return uuid.uuid4()
