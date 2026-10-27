"""Pytest configuration for shared-core tests."""

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "known_bug: characterization test pinning current buggy behaviour; "
        "the comment names the roadmap item that changes it",
    )


@pytest.fixture
def sample_uuid():
    import uuid

    return uuid.uuid4()
