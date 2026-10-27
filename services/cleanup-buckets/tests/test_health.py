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


@pytest.mark.parametrize(
    "instance",
    [
        None,
        SimpleNamespace(consumer=None, producer=object()),
        SimpleNamespace(consumer=object(), producer=None),
    ],
    ids=["no-worker", "no-consumer", "no-producer"],
)
@pytest.mark.asyncio
async def test_unavailable(client, monkeypatch, instance):
    monkeypatch.setattr(worker_module, "worker_instance", instance)

    response = await client.get("/health")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_worker_with_consumer_and_producer_is_healthy(client, monkeypatch):
    instance = SimpleNamespace(consumer=object(), producer=object())
    monkeypatch.setattr(worker_module, "worker_instance", instance)

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "worker": "active"}


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_healthy_before_clients_started(
    client, monkeypatch, worker, consumer, producer
):
    # CHARACTERIZATION: changes in R19 (/health reflects the real consumer state)
    monkeypatch.setattr(worker_module, "worker_instance", worker)

    response = await client.get("/health")

    consumer.start.assert_not_awaited()
    producer.start.assert_not_awaited()
    assert response.status_code == 200
