"""Characterization: how asset-service resolves the caller (api/deps.py)."""

import uuid

import pytest

from asset_service.main import app
from shared_core.utils.endpoint.rs_dpop import validate_dpop
from tests.api.helpers import user_headers


@pytest.mark.asyncio
async def test_missing_user_sub_is_401(client):
    resp = await client.get("/projects/")

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Missing user identity"}


@pytest.mark.asyncio
async def test_non_uuid_user_sub_is_401(client):
    resp = await client.get("/projects/", headers={"X-User-Sub": "not-a-uuid"})

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid user identity format"}


@pytest.mark.asyncio
async def test_unknown_user_sub_is_404(client):
    resp = await client.get("/projects/", headers={"X-User-Sub": str(uuid.uuid4())})

    assert resp.status_code == 404
    assert resp.json() == {"detail": "User not synced yet"}


@pytest.mark.asyncio
async def test_known_user_sub_resolves_user(client, seed):
    alice = await seed.user()

    resp = await client.get("/projects/", headers=user_headers(alice))

    assert resp.status_code == 200


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_any_caller_can_impersonate_by_setting_user_sub(client, seed):
    # CHARACTERIZATION: changes in R1. X-User-Sub is trusted as sent, with no tie
    # to the access token's sub, so whoever reaches asset-service picks the user.
    alice = await seed.user("alice@example.com")
    bob = await seed.user("bob@example.com")
    await seed.project(alice, name="alice-private")
    # Bob's token passes DPoP validation...
    app.dependency_overrides[validate_dpop] = lambda: {"sub": str(bob.kc_sub)}

    # ...but he sends Alice's sub.
    resp = await client.get("/projects/", headers=user_headers(alice))

    assert resp.status_code == 200
    assert [p["name"] for p in resp.json()] == ["alice-private"]


@pytest.mark.asyncio
async def test_dpop_validation_is_wired_on_project_routes(client, seed):
    app.dependency_overrides.pop(validate_dpop)
    alice = await seed.user()

    resp = await client.get("/projects/", headers=user_headers(alice))

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Missing Security Headers"}
