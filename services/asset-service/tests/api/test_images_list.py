"""Characterization: GET /projects/{id}/images/ and /images/preview."""

import uuid

import pytest
import pytest_asyncio
from helpers import later, user_headers


def get_url(bucket: str, key: str) -> str:
    return f"https://s3.test/{bucket}/{key}?op=get_object"


@pytest_asyncio.fixture
async def owner_and_project(seed):
    alice = await seed.user()
    return alice, await seed.project(alice)


@pytest.mark.asyncio
async def test_list_excludes_deleted_and_orders_newest_first(
    client, seed, owner_and_project
):
    alice, project = owner_and_project
    old = await seed.image(project, created_at=later(1), original_filename="old.png")
    new = await seed.image(
        project,
        created_at=later(2),
        original_filename="new.png",
        status="OPTIMIZED",
        processed_s3_path="p/new.avif",
        processed_format="avif",
    )
    await seed.image(project, created_at=later(3), deleted=True)
    other_project = await seed.project(alice, name="other")
    await seed.image(other_project, created_at=later(4))

    resp = await client.get(
        f"/projects/{project.id}/images/", headers=user_headers(alice)
    )

    assert resp.status_code == 200
    body = resp.json()
    assert [i["id"] for i in body] == [str(new.id), str(old.id)]
    assert set(body[0]) == {
        "id",
        "project_id",
        "original_filename",
        "raw_s3_path",
        "processed_s3_path",
        "file_size_bytes",
        "dimensions_px",
        "status",
        "retry_count",
        "last_error_log",
        "processed_format",
        "created_at",
    }
    assert body[0]["status"] == "OPTIMIZED"
    assert body[0]["processed_s3_path"] == "p/new.avif"
    assert body[0]["processed_format"] == "avif"
    assert body[0]["retry_count"] == 0
    assert body[1]["status"] == "PENDING"
    assert body[1]["raw_s3_path"] == old.raw_s3_path


@pytest.mark.parametrize(
    ("status", "display", "raw", "processed"),
    [
        ("OPTIMIZED", "preview", "raw", "processed"),
        ("PENDING", "raw", "raw", None),
        ("PROCESSING", "raw", None, None),
        ("FAILED", "raw", None, None),
    ],
)
@pytest.mark.asyncio
async def test_preview_url_selection_by_status(
    client, seed, owner_and_project, status, display, raw, processed
):
    alice, project = owner_and_project
    image = await seed.image(
        project,
        status=status,
        raw_s3_path="r/img.png",
        processed_s3_path="p/img.avif",
        preview_s3_path="p/img-preview.avif",
        processed_format="avif",
    )
    urls = {
        "raw": get_url("raw-images", "r/img.png"),
        "processed": get_url("processed-images", "p/img.avif"),
        "preview": get_url("processed-images", "p/img-preview.avif"),
        None: None,
    }

    resp = await client.get(
        f"/projects/{project.id}/images/preview", headers=user_headers(alice)
    )

    assert resp.status_code == 200
    [item] = resp.json()
    assert item["id"] == str(image.id)
    assert item["original_filename"] == "cat.png"
    assert item["status"] == status
    assert item["processed_format"] == "avif"
    assert item["display_url"] == urls[display]
    assert item["raw_image_url"] == urls[raw]
    assert item["processed_image_url"] == urls[processed]


@pytest.mark.asyncio
async def test_preview_excludes_deleted(client, seed, owner_and_project):
    alice, project = owner_and_project
    await seed.image(project, deleted=True)

    resp = await client.get(
        f"/projects/{project.id}/images/preview", headers=user_headers(alice)
    )

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.parametrize("path", ["", "preview"])
@pytest.mark.asyncio
async def test_other_users_project_is_403(client, seed, path):
    alice = await seed.user("alice@example.com")
    bob = await seed.user("bob@example.com")
    project = await seed.project(bob)
    await seed.image(project)

    resp = await client.get(
        f"/projects/{project.id}/images/{path}", headers=user_headers(alice)
    )

    assert resp.status_code == 403
    assert resp.json() == {"detail": "Access denied"}


@pytest.mark.known_bug
@pytest.mark.parametrize("path", ["", "preview"])
@pytest.mark.asyncio
async def test_missing_project_is_403(client, seed, path):
    # CHARACTERIZATION: changes in R1 or later API cleanup. NotFoundError is
    # mapped to 403 on image routes.
    alice = await seed.user()
    missing = uuid.uuid4()

    resp = await client.get(
        f"/projects/{missing}/images/{path}", headers=user_headers(alice)
    )

    assert resp.status_code == 403
    assert resp.json() == {"detail": f"Project {missing} not found"}
