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


class StopMain(Exception):
    pass


@pytest.fixture
def worker_kwargs(monkeypatch):
    """Run main() with env vars that a config-driven worker would read."""
    cls = MagicMock(side_effect=StopMain)
    monkeypatch.setattr(worker_module, "KafkaCleanupWorker", cls)
    monkeypatch.setattr(worker_module, "worker_instance", None)
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "env-broker:29092")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://env-s3:9000")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "env-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-secret-key")
    monkeypatch.setenv("RAW_BUCKET", "env-raw")
    monkeypatch.setenv("PROCESSED_BUCKET", "env-processed")

    async def run():
        with pytest.raises(StopMain):
            await worker_module.main()
        cls.assert_called_once()
        return cls.call_args.kwargs

    return run


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_kafka_and_buckets_are_hardcoded(worker_kwargs):
    # CHARACTERIZATION: changes in R11 (workers read topics/config from env)
    kwargs = await worker_kwargs()

    assert kwargs["kafka_bootstrap"] == "kafka:9092"
    assert kwargs["raw_bucket"] == "raw-images"
    assert kwargs["processed_bucket"] == "processed-images"


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_s3_endpoint_and_credentials_are_hardcoded(worker_kwargs):
    # CHARACTERIZATION: changes in R2 (secrets from files/env) and R11.
    # The key values are not repeated here; it is enough that env is ignored.
    s3_config = (await worker_kwargs())["s3_config"]

    assert s3_config["endpoint_url"] == "http://rustfs:9000"
    assert s3_config["region_name"] == "us-east-1"
    assert s3_config["config"].signature_version == "s3v4"
    assert s3_config["aws_access_key_id"] not in ("", "env-access-key")
    assert s3_config["aws_secret_access_key"] not in ("", "env-secret-key")


@pytest.mark.known_bug
def test_project_script_points_to_hello_world_stub():
    # CHARACTERIZATION: changes in R12. The Dockerfile runs
    # `python -m cleanup_buckets.main`; the console script runs a stub.
    scripts = tomllib.loads(PYPROJECT.read_text())["project"]["scripts"]
    assert scripts == {"cleanup-buckets": "cleanup_buckets:main"}

    result = subprocess.run(
        [sys.executable, "-c", "import cleanup_buckets; cleanup_buckets.main()"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "Hello from cleanup-buckets!\n"
