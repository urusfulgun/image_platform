"""Characterization: POST /projects/{id}/images/presign."""

import re
import uuid

import pytest
import pytest_asyncio
from helpers import user_headers

from asset_service.db.models import ImageMetadataModel
from shared_core.events.kafka_events import ImageRawUploadedEvent


def presign_url(project_id) -> str:
    return f"/projects/{project_id}/images/presign"


@pytest_asyncio.fixture
async def owner_and_project(seed):
    alice = await seed.user()
    return alice, await seed.project(alice)


@pytest.mark.asyncio
async def test_presign_registers_pending_image_and_returns_upload_url(
    client, seed, owner_and_project, kafka_producer, presign_upload
):
    alice, project = owner_and_project

    resp = await client.post(
        presign_url(project.id),
        json={"fileName": "cat.PNG", "fileSizeBytes": 2048},
        headers=user_headers(alice),
    )

    assert resp.status_code == 201
    body = resp.json()
    assert set(body) == {"image_id", "upload_url"}
    image_id = uuid.UUID(body["image_id"])

    image = await seed.get(ImageMetadataModel, image_id)
    assert image.project_id == project.id
    assert image.original_filename == "cat.PNG"
    assert image.file_size_bytes == 2048
    # The key ignores the original name: {project_id}/{random uuid}/normal.{ext}
    assert re.fullmatch(rf"{project.id}/[0-9a-f-]{{36}}/normal\.PNG", image.raw_s3_path)
    assert image.raw_format == "PNG"
    assert image.deleted is False
    assert await seed.get_status(image_id) == "PENDING"

    presign_upload.assert_called_once_with(key=image.raw_s3_path)
    assert body["upload_url"] == (
        f"https://s3.test/raw-images/{image.raw_s3_path}?op=put_object"
    )

    kafka_producer.publish_image_raw_presign_link_generated_topic.assert_awaited_once()
    event = (
        kafka_producer.publish_image_raw_presign_link_generated_topic.await_args.args[0]
    )
    assert isinstance(event, ImageRawUploadedEvent)
    assert event.image_id == image_id
    assert event.project_id == project.id
    assert event.raw_s3_path == image.raw_s3_path
    assert event.raw_format == "PNG"
    assert event.file_size_bytes == 2048


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_presign_publishes_before_upload_on_link_generated_topic(
    client, owner_and_project, kafka_producer
):
    # CHARACTERIZATION: changes in R15. An ImageRawUploadedEvent goes out when the
    # link is issued, before any bytes reach S3; the real upload event only comes
    # from the RustFS callback.
    alice, project = owner_and_project

    resp = await client.post(
        presign_url(project.id),
        json={"fileName": "cat.png", "fileSizeBytes": 1},
        headers=user_headers(alice),
    )

    assert resp.status_code == 201
    kafka_producer.publish_image_raw_presign_link_generated_topic.assert_awaited_once()
    kafka_producer.publish_image_raw_uploaded.assert_not_awaited()


@pytest.mark.asyncio
async def test_presign_without_extension_falls_back_to_bin(
    client, seed, owner_and_project
):
    alice, project = owner_and_project

    resp = await client.post(
        presign_url(project.id),
        json={"fileName": "README", "fileSizeBytes": None},
        headers=user_headers(alice),
    )

    assert resp.status_code == 201
    image = await seed.get(ImageMetadataModel, uuid.UUID(resp.json()["image_id"]))
    assert image.raw_s3_path.endswith("/normal.bin")
    assert image.raw_format == "bin"
    assert image.file_size_bytes is None


@pytest.mark.known_bug
@pytest.mark.parametrize(
    "file_name",
    ["   ", "../etc/passwd", "dir\\cat.png"],
    ids=["blank", "slash", "backslash"],
)
@pytest.mark.asyncio
async def test_presign_rejected_file_name_is_500(
    client, owner_and_project, kafka_producer, file_name
):
    # CHARACTERIZATION: no roadmap item yet. The PresignRequest validator rejects
    # the name, but main.py's RequestValidationError handler echoes exc.errors(),
    # whose ctx holds the raw ValueError; JSONResponse can't serialize it, so the
    # client gets 500 instead of 422. Nothing is registered or published.
    alice, project = owner_and_project

    resp = await client.post(
        presign_url(project.id),
        json={"fileName": file_name, "fileSizeBytes": 1},
        headers=user_headers(alice),
    )

    assert resp.status_code == 500
    kafka_producer.publish_image_raw_presign_link_generated_topic.assert_not_awaited()


@pytest.mark.parametrize(
    "payload",
    [
        {"fileName": "cat.png"},
        {"file_name": "cat.png", "file_size_bytes": 1},
    ],
    ids=["missing-size", "snake-case"],
)
@pytest.mark.asyncio
async def test_presign_invalid_body_is_422(
    client, owner_and_project, kafka_producer, payload
):
    alice, project = owner_and_project

    resp = await client.post(
        presign_url(project.id), json=payload, headers=user_headers(alice)
    )

    assert resp.status_code == 422
    assert set(resp.json()) == {"detail", "body"}
    kafka_producer.publish_image_raw_presign_link_generated_topic.assert_not_awaited()


@pytest.mark.asyncio
async def test_presign_on_other_users_project_is_403(client, seed, kafka_producer):
    alice = await seed.user("alice@example.com")
    bob = await seed.user("bob@example.com")
    project = await seed.project(bob)

    resp = await client.post(
        presign_url(project.id),
        json={"fileName": "cat.png", "fileSizeBytes": 1},
        headers=user_headers(alice),
    )

    assert resp.status_code == 403
    assert resp.json() == {"detail": "Access denied"}
    kafka_producer.publish_image_raw_presign_link_generated_topic.assert_not_awaited()


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_presign_on_missing_project_is_403(client, seed):
    # CHARACTERIZATION: changes in R1 or later API cleanup. NotFoundError is
    # mapped to 403 on image routes, unlike GET /projects/{id} which returns 404.
    alice = await seed.user()
    missing = uuid.uuid4()

    resp = await client.post(
        presign_url(missing),
        json={"fileName": "cat.png", "fileSizeBytes": 1},
        headers=user_headers(alice),
    )

    assert resp.status_code == 403
    assert resp.json() == {"detail": f"Project {missing} not found"}
