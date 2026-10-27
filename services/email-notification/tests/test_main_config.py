"""Characterization tests for the config main() wires into the worker.

The worker class is replaced by a mock that raises, so main() stops before it
starts the TaskGroup, uvicorn or the signal handlers.
"""

import inspect
import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.conftest import worker_module

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
ENV_VARS = ("KAFKA_BOOTSTRAP_SERVERS", "SMTP_HOST", "SMTP_PORT", "FROM_EMAIL")


class StopMain(Exception):
    pass


@pytest.fixture
def worker_cls(monkeypatch):
    cls = MagicMock(side_effect=StopMain)
    monkeypatch.setattr(worker_module, "NotificationWorker", cls)
    monkeypatch.setattr(worker_module, "worker_instance", None)
    return cls


@pytest.mark.asyncio
async def test_defaults_without_env(worker_cls, monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(StopMain):
        await worker_module.main()

    worker_cls.assert_called_once_with(
        kafka_bootstrap="kafka:9092",
        smtp_host="mailpit",
        smtp_port=1025,
        from_email="noreply@image-platform.local",
    )


@pytest.mark.asyncio
async def test_values_come_from_env(worker_cls, monkeypatch):
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "broker:29092")
    monkeypatch.setenv("SMTP_HOST", "smtp.example")
    monkeypatch.setenv("SMTP_PORT", "2526")
    monkeypatch.setenv("FROM_EMAIL", "bot@example.test")

    with pytest.raises(StopMain):
        await worker_module.main()

    worker_cls.assert_called_once_with(
        kafka_bootstrap="broker:29092",
        smtp_host="smtp.example",
        smtp_port=2526,
        from_email="bot@example.test",
    )


def test_package_has_no_console_script_stub():
    # The Dockerfile runs `python -m email_notification.main`; the hello-world stub
    # is gone. `email_notification.main` may still exist as the imported submodule.
    project = tomllib.loads(PYPROJECT.read_text())["project"]
    assert "scripts" not in project

    import email_notification

    assert not inspect.isfunction(getattr(email_notification, "main", None))
