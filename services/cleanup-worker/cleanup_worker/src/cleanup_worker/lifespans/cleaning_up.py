import asyncio
from contextlib import asynccontextmanager

import aioboto3
from mypy_boto3_s3 import S3Client
from cleanup_worker.service_layer.clean_up import consume_cleanup_events
from cleanup_worker.config import settings


@asynccontextmanager
async def s3_lifespan_raw(app: FastAPI):
    # 1. Initialize the Session and Client once
    session = aioboto3.Session()
    # We use an ExitStack or simply enter the context manager here
    async with session.client("s3", **RUSTFS_PARAMS) as s3_client:
        s3_client: S3Client  # Manual type hint for IDE support
        # 2. Store the persistent client in app.state
        app.state.s3_client_raw = s3_client
        await s3_client.put_bucket_lifecycle_configuration(
            Bucket=settings.S3_BUCKET_UPLOADS,
            LifecycleConfiguration=LIFECYCLE_CONFIG,
        )
        yield


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup S3 Client using the session factory pattern
    async with get_s3_client() as s3:
        # Start the cleanup task
        cleanup_task = asyncio.create_task(consume_cleanup_events(s3, settings))

        yield  # Worker is running

        cleanup_task.cancel()
        await asyncio.gather(cleanup_task, return_exceptions=True)
