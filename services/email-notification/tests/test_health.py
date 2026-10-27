"""Characterization tests for the /health endpoint."""

from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio

from tests.conftest import worker_module


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=worker_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://worker") as c:
        yield c


@pytest.mark.asyncio
async def test_no_worker_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(worker_module, "worker_instance", None)

    response = await client.get("/health")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_worker_with_consumer_is_healthy(client, monkeypatch):
    monkeypatch.setattr(
        worker_module, "worker_instance", SimpleNamespace(consumer=object())
    )

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "worker": "active"}


@pytest.mark.asyncio
async def test_worker_without_consumer_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(
        worker_module, "worker_instance", SimpleNamespace(consumer=None)
    )

    response = await client.get("/health")

    assert response.status_code == 503


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_healthy_before_consumer_started(client, monkeypatch, worker, consumer):
    # CHARACTERIZATION: changes in R19 (/health reflects the real consumer state)
    monkeypatch.setattr(worker_module, "worker_instance", worker)

    response = await client.get("/health")

    consumer.start.assert_not_awaited()
    assert response.status_code == 200
