"""Fixtures for API characterization tests.

The real app and domain services run against in-memory SQLite. Kafka, S3 presigning
and DPoP validation are faked; the lifespan never runs.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from helpers import BASE_URL, T0
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from asset_service.db.models import (
    Base,
    ImageMetadataModel,
    ImageProcessingStatusModel,
    ProjectModel,
    UserModel,
)
from asset_service.db.session import get_db
from asset_service.kafka.producer import AssetKafkaProducer
from asset_service.main import app
from shared_core.utils.endpoint.rs_dpop import validate_dpop


def fake_presigned_url(op: str, Params: dict, ExpiresIn: int) -> str:
    return f"https://s3.test/{Params['Bucket']}/{Params['Key']}?op={op}"


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def kafka_producer():
    producer = AsyncMock(spec=AssetKafkaProducer)
    app.state.kafka_producer = producer
    yield producer
    del app.state.kafka_producer


@pytest.fixture
def presign_upload(mocker):
    return mocker.patch(
        "asset_service.api.images.generate_upload_presigned_url",
        side_effect=lambda key: f"https://s3.test/raw-images/{key}?op=put_object",
    )


@pytest.fixture
def s3_client(mocker):
    client = MagicMock()
    client.generate_presigned_url.side_effect = fake_presigned_url
    mocker.patch("asset_service.domain.images.get_s3_client", return_value=client)
    return client


@pytest_asyncio.fixture
async def client(session_factory, kafka_producer, presign_upload, s3_client):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[validate_dpop] = lambda: None
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as c:
        yield c
    app.dependency_overrides.clear()


class Seed:
    """Inserts rows directly and reads them back in fresh sessions."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def _add(self, *rows):
        async with self._sf() as session:
            for row in rows:
                session.add(row)
                await session.flush()
            await session.commit()
        return rows[0]

    async def user(self, email: str = "alice@example.com") -> UserModel:
        return await self._add(UserModel(kc_sub=uuid.uuid4(), email=email))

    async def project(
        self, user: UserModel, name: str = "proj", created_at: datetime = T0
    ) -> ProjectModel:
        return await self._add(
            ProjectModel(user_id=user.id, name=name, created_at=created_at)
        )

    async def image(
        self,
        project: ProjectModel,
        *,
        status: str = "PENDING",
        deleted: bool = False,
        deleted_at: datetime | None = None,
        created_at: datetime = T0,
        raw_s3_path: str | None = None,
        processed_s3_path: str | None = None,
        preview_s3_path: str | None = None,
        processed_format: str | None = None,
        original_filename: str = "cat.png",
    ) -> ImageMetadataModel:
        image_id = uuid.uuid7()
        image = ImageMetadataModel(
            id=image_id,
            project_id=project.id,
            original_filename=original_filename,
            raw_format="png",
            raw_s3_path=raw_s3_path or f"{project.id}/{uuid.uuid4()}/normal.png",
            processed_s3_path=processed_s3_path,
            preview_s3_path=preview_s3_path,
            processed_format=processed_format,
            file_size_bytes=1234,
            created_at=created_at,
            deleted=deleted,
            deleted_at=deleted_at,
        )
        return await self._add(
            image, ImageProcessingStatusModel(image_id=image_id, status=status)
        )

    async def get(self, model, pk):
        async with self._sf() as session:
            return await session.get(model, pk)

    async def get_status(self, image_id: uuid.UUID) -> str:
        row = await self.get(ImageProcessingStatusModel, image_id)
        return row.status


@pytest.fixture
def seed(session_factory) -> Seed:
    return Seed(session_factory)
