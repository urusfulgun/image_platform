"""Characterization: /projects routes."""

import uuid

import pytest

from asset_service.db.models import ProjectModel
from tests.api.helpers import later, user_headers


@pytest.mark.asyncio
async def test_list_returns_only_callers_projects_newest_first(client, seed):
    alice = await seed.user("alice@example.com")
    bob = await seed.user("bob@example.com")
    await seed.project(alice, name="old", created_at=later(1))
    await seed.project(alice, name="new", created_at=later(2))
    await seed.project(bob, name="bobs")

    resp = await client.get("/projects/", headers=user_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert [p["name"] for p in body] == ["new", "old"]
    assert {p["user_id"] for p in body} == {str(alice.id)}
    assert set(body[0]) == {"id", "user_id", "name", "status", "created_at"}
    assert body[0]["status"] == "Created"


@pytest.mark.asyncio
async def test_list_is_empty_for_user_without_projects(client, seed):
    alice = await seed.user()

    resp = await client.get("/projects/", headers=user_headers(alice))

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_returns_201_and_persists(client, seed):
    alice = await seed.user()

    resp = await client.post(
        "/projects/", json={"name": "holiday"}, headers=user_headers(alice)
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "holiday"
    assert body["user_id"] == str(alice.id)
    assert body["status"] == "Created"
    stored = await seed.get(ProjectModel, uuid.UUID(body["id"]))
    assert stored.user_id == alice.id
    assert stored.name == "holiday"


@pytest.mark.asyncio
async def test_create_without_name_is_422_with_body_echo(client, seed):
    alice = await seed.user()

    resp = await client.post("/projects/", json={}, headers=user_headers(alice))

    assert resp.status_code == 422
    body = resp.json()
    assert set(body) == {"detail", "body"}
    assert body["body"] == {}
    assert body["detail"][0]["loc"] == ["body", "name"]
    assert body["detail"][0]["type"] == "missing"


@pytest.mark.asyncio
async def test_get_own_project_is_200(client, seed):
    alice = await seed.user()
    project = await seed.project(alice, name="mine")

    resp = await client.get(f"/projects/{project.id}", headers=user_headers(alice))

    assert resp.status_code == 200
    assert resp.json()["id"] == str(project.id)
    assert resp.json()["name"] == "mine"


@pytest.mark.asyncio
async def test_get_missing_project_is_404(client, seed):
    alice = await seed.user()
    missing = uuid.uuid4()

    resp = await client.get(f"/projects/{missing}", headers=user_headers(alice))

    assert resp.status_code == 404
    assert resp.json() == {"detail": f"Project {missing} not found"}


@pytest.mark.asyncio
async def test_get_other_users_project_is_403(client, seed):
    alice = await seed.user("alice@example.com")
    bob = await seed.user("bob@example.com")
    project = await seed.project(bob)

    resp = await client.get(f"/projects/{project.id}", headers=user_headers(alice))

    assert resp.status_code == 403
    assert resp.json() == {"detail": "Access denied"}
