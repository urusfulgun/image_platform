"""Characterization: POST /callback/rustfs (RustFS bucket notifications)."""

import pytest
import pytest_asyncio
from helpers import WEBHOOK_TOKEN, later
from shared_core.events.kafka_events import ImageRawUploadedEvent

from asset_service.db.models import ImageMetadataModel

AUTH = {"Authorization": f"Bearer {WEBHOOK_TOKEN}"}


def records(*pairs: tuple[str, str]) -> dict:
    return {
        "Records": [
            {"eventName": name, "s3": {"object": {"key": key}}} for name, key in pairs
        ]
    }


@pytest_asyncio.fixture
async def project(seed):
    return await seed.project(await seed.user())


@pytest.mark.parametrize(
    "event_name", ["s3:ObjectCreated:Put", "s3:ObjectCreated:CompleteMultipartUpload"]
)
@pytest.mark.asyncio
async def test_object_created_publishes_raw_uploaded(
    client, seed, project, kafka_producer, event_name
):
    image = await seed.image(project, raw_s3_path="p1/u1/normal.png")

    resp = await client.post(
        "/callback/rustfs", json=records((event_name, "p1/u1/normal.png")), headers=AUTH
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "success"}
    kafka_producer.publish_image_raw_uploaded.assert_awaited_once()
    event = kafka_producer.publish_image_raw_uploaded.await_args.args[0]
    assert isinstance(event, ImageRawUploadedEvent)
    assert event.image_id == image.id
    assert event.project_id == project.id
    assert event.raw_s3_path == "p1/u1/normal.png"
    assert event.raw_format == "png"
    assert event.file_size_bytes == 1234


@pytest.mark.asyncio
async def test_object_created_decodes_url_encoded_slashes(
    client, seed, project, kafka_producer
):
    image = await seed.image(project, raw_s3_path="p1/u1/normal.png")

    resp = await client.post(
        "/callback/rustfs",
        json=records(("s3:ObjectCreated:Put", "p1%2Fu1%2Fnormal.png")),
        headers=AUTH,
    )

    assert resp.status_code == 200
    event = kafka_producer.publish_image_raw_uploaded.await_args.args[0]
    assert event.image_id == image.id


@pytest.mark.parametrize(
    "event_name", ["s3:ObjectCreated:Put", "s3:ObjectRemoved:Delete"]
)
@pytest.mark.asyncio
async def test_unknown_key_is_ignored(client, kafka_producer, event_name):
    resp = await client.post(
        "/callback/rustfs", json=records((event_name, "nope/nope/x.png")), headers=AUTH
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "success"}
    kafka_producer.publish_image_raw_uploaded.assert_not_awaited()


@pytest.mark.asyncio
async def test_object_removed_confirms_deletion(client, seed, project, kafka_producer):
    image = await seed.image(project, raw_s3_path="p1/u1/normal.png")

    resp = await client.post(
        "/callback/rustfs",
        json=records(("s3:ObjectRemoved:Delete", "p1/u1/normal.png")),
        headers=AUTH,
    )

    assert resp.status_code == 200
    stored = await seed.get(ImageMetadataModel, image.id)
    assert stored.deleted is True
    assert stored.deleted_at is not None
    kafka_producer.publish_image_raw_uploaded.assert_not_awaited()
    kafka_producer.publish_image_deleted_topic.assert_not_awaited()


@pytest.mark.asyncio
async def test_object_removed_is_noop_when_deleted_at_already_set(
    client, seed, project
):
    # deleted=False with deleted_at set shows the guard reads only deleted_at.
    image = await seed.image(
        project, raw_s3_path="p1/u1/normal.png", deleted_at=later(1)
    )

    resp = await client.post(
        "/callback/rustfs",
        json=records(("s3:ObjectRemoved:Delete", "p1/u1/normal.png")),
        headers=AUTH,
    )

    assert resp.status_code == 200
    stored = await seed.get(ImageMetadataModel, image.id)
    assert stored.deleted is False
    assert stored.deleted_at.replace(tzinfo=None) == later(1).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_other_event_names_are_ignored(client, seed, project, kafka_producer):
    image = await seed.image(project, raw_s3_path="p1/u1/normal.png")

    resp = await client.post(
        "/callback/rustfs",
        json=records(("s3:ObjectAccessed:Get", "p1/u1/normal.png")),
        headers=AUTH,
    )

    assert resp.status_code == 200
    kafka_producer.publish_image_raw_uploaded.assert_not_awaited()
    stored = await seed.get(ImageMetadataModel, image.id)
    assert stored.deleted is False


@pytest.mark.asyncio
async def test_empty_or_missing_records_is_success(client, kafka_producer):
    for payload in ({"Records": []}, {}):
        resp = await client.post("/callback/rustfs", json=payload, headers=AUTH)

        assert resp.status_code == 200
        assert resp.json() == {"status": "success"}
    kafka_producer.publish_image_raw_uploaded.assert_not_awaited()


@pytest.mark.asyncio
async def test_multiple_records_are_handled_in_order(
    client, seed, project, kafka_producer
):
    first = await seed.image(project, raw_s3_path="p1/a/normal.png")
    second = await seed.image(project, raw_s3_path="p1/b/normal.png")
    removed = await seed.image(project, raw_s3_path="p1/c/normal.png")

    resp = await client.post(
        "/callback/rustfs",
        json=records(
            ("s3:ObjectCreated:Put", "p1/a/normal.png"),
            ("s3:ObjectRemoved:Delete", "p1/c/normal.png"),
            ("s3:ObjectCreated:Put", "p1/b/normal.png"),
        ),
        headers=AUTH,
    )

    assert resp.status_code == 200
    published = [
        c.args[0].image_id
        for c in kafka_producer.publish_image_raw_uploaded.await_args_list
    ]
    assert published == [first.id, second.id]
    assert (await seed.get(ImageMetadataModel, removed.id)).deleted is True


@pytest.mark.asyncio
async def test_record_without_key_is_500(client):
    resp = await client.post(
        "/callback/rustfs",
        json={"Records": [{"eventName": "s3:ObjectCreated:Put", "s3": {}}]},
        headers=AUTH,
    )

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal processing error"}


@pytest.mark.asyncio
async def test_wrong_token_is_403(client, kafka_producer):
    resp = await client.post(
        "/callback/rustfs",
        json=records(("s3:ObjectCreated:Put", "p1/u1/normal.png")),
        headers={"Authorization": "Bearer wrong"},
    )

    assert resp.status_code == 403
    assert resp.json() == {"detail": "Invalid or missing webhook token."}
    kafka_producer.publish_image_raw_uploaded.assert_not_awaited()


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_hardcoded_secret_is_accepted_with_any_scheme(client):
    # CHARACTERIZATION: changes in R2 / R4. The secret is a module constant, the
    # scheme before the space is never checked, and the compare is a plain !=.
    resp = await client.post(
        "/callback/rustfs",
        json={"Records": []},
        headers={"Authorization": f"Anything {WEBHOOK_TOKEN}"},
    )

    assert resp.status_code == 200


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_missing_authorization_is_500(client):
    # CHARACTERIZATION: changes in R4. None.split() raises AttributeError.
    resp = await client.post("/callback/rustfs", json={"Records": []})

    assert resp.status_code == 500


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_authorization_without_space_is_500(client):
    # CHARACTERIZATION: changes in R4. split(" ")[1] raises IndexError.
    resp = await client.post(
        "/callback/rustfs",
        json={"Records": []},
        headers={"Authorization": WEBHOOK_TOKEN},
    )

    assert resp.status_code == 500


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_non_json_body_is_500(client):
    # CHARACTERIZATION: changes in R4. The auth dependency parses the body before
    # checking the token, so invalid JSON fails before auth.
    resp = await client.post(
        "/callback/rustfs",
        content=b"not json",
        headers={**AUTH, "Content-Type": "application/json"},
    )

    assert resp.status_code == 500
