"""Characterization tests for the config main() wires into the worker.

The worker class is replaced by a mock that raises, so main() stops before it
starts the TaskGroup, uvicorn or the signal handlers.
"""

import subprocess
import sys
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


@pytest.mark.known_bug
def test_project_script_points_to_hello_world_stub():
    # CHARACTERIZATION: changes in R12. The Dockerfile runs
    # `python -m email_notification.main`; the console script runs a stub.
    scripts = tomllib.loads(PYPROJECT.read_text())["project"]["scripts"]
    assert scripts == {"email-notification": "email_notification:main"}

    result = subprocess.run(
        [sys.executable, "-c", "import email_notification; email_notification.main()"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "Hello from email-notification!\n"
