"""Characterization: DELETE /projects/{id}/images/{image_id}."""

import uuid

import pytest
import pytest_asyncio
from helpers import user_headers
from shared_core.events.kafka_events import ImageDeletedEvent

from asset_service.db.models import ImageMetadataModel
from asset_service.domain.images import ImageService


def delete_url(project_id, image_id) -> str:
    return f"/projects/{project_id}/images/{image_id}"


@pytest_asyncio.fixture
async def owner_and_project(seed):
    alice = await seed.user()
    return alice, await seed.project(alice)


@pytest.mark.asyncio
async def test_delete_soft_deletes_and_publishes_cleanup_event(
    client, seed, owner_and_project, kafka_producer
):
    alice, project = owner_and_project
    image = await seed.image(
        project,
        status="OPTIMIZED",
        processed_s3_path="p/img.avif",
        preview_s3_path="p/img-preview.avif",
    )

    resp = await client.delete(
        delete_url(project.id, image.id), headers=user_headers(alice)
    )

    assert resp.status_code == 204
    assert resp.content == b""
    stored = await seed.get(ImageMetadataModel, image.id)
    assert stored.deleted is True

    kafka_producer.publish_image_deleted_topic.assert_awaited_once()
    event = kafka_producer.publish_image_deleted_topic.await_args.args[0]
    assert event == ImageDeletedEvent(
        image_id=image.id,
        project_id=project.id,
        raw_s3_path=image.raw_s3_path,
        processed_s3_path="p/img.avif",
        preview_s3_path="p/img-preview.avif",
    )


@pytest.mark.asyncio
async def test_delete_of_unprocessed_image_sends_null_paths(
    client, seed, owner_and_project, kafka_producer
):
    alice, project = owner_and_project
    image = await seed.image(project)

    resp = await client.delete(
        delete_url(project.id, image.id), headers=user_headers(alice)
    )

    assert resp.status_code == 204
    event = kafka_producer.publish_image_deleted_topic.await_args.args[0]
    assert event.processed_s3_path is None
    assert event.preview_s3_path is None


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_delete_leaves_deleted_at_unset(client, seed, owner_and_project):
    # CHARACTERIZATION: changes in R10 or later. ImageService.delete has the
    # deleted_at assignment commented out; only the RustFS ObjectRemoved callback
    # (delete_confirm) sets it.
    alice, project = owner_and_project
    image = await seed.image(project)

    resp = await client.delete(
        delete_url(project.id, image.id), headers=user_headers(alice)
    )

    assert resp.status_code == 204
    stored = await seed.get(ImageMetadataModel, image.id)
    assert stored.deleted_at is None


@pytest.mark.parametrize("case", ["missing", "already-deleted", "other-project"])
@pytest.mark.asyncio
async def test_delete_unknown_image_is_404(
    client, seed, owner_and_project, kafka_producer, case
):
    alice, project = owner_and_project
    if case == "missing":
        image_id = uuid.uuid4()
    elif case == "already-deleted":
        image_id = (await seed.image(project, deleted=True)).id
    else:
        other = await seed.project(alice, name="other")
        image_id = (await seed.image(other)).id

    resp = await client.delete(
        delete_url(project.id, image_id), headers=user_headers(alice)
    )

    assert resp.status_code == 404
    assert resp.json() == {
        "detail": f"Image {image_id} not found in project {project.id}"
    }
    kafka_producer.publish_image_deleted_topic.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_unexpected_error_is_500(
    client, seed, owner_and_project, kafka_producer, mocker
):
    alice, project = owner_and_project
    image = await seed.image(project)
    mocker.patch.object(ImageService, "delete", side_effect=RuntimeError("db down"))

    resp = await client.delete(
        delete_url(project.id, image.id), headers=user_headers(alice)
    )

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error during deletion"}
    kafka_producer.publish_image_deleted_topic.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_on_other_users_project_is_403(client, seed, kafka_producer):
    alice = await seed.user("alice@example.com")
    bob = await seed.user("bob@example.com")
    project = await seed.project(bob)
    image = await seed.image(project)

    resp = await client.delete(
        delete_url(project.id, image.id), headers=user_headers(alice)
    )

    assert resp.status_code == 403
    assert resp.json() == {"detail": "Access denied"}
    stored = await seed.get(ImageMetadataModel, image.id)
    assert stored.deleted is False
    kafka_producer.publish_image_deleted_topic.assert_not_awaited()


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_delete_on_missing_project_is_403(client, seed):
    # CHARACTERIZATION: changes in R1 or later API cleanup. NotFoundError is
    # mapped to 403 on image routes.
    alice = await seed.user()
    missing = uuid.uuid4()

    resp = await client.delete(
        delete_url(missing, uuid.uuid4()), headers=user_headers(alice)
    )

    assert resp.status_code == 403
    assert resp.json() == {"detail": f"Project {missing} not found"}
