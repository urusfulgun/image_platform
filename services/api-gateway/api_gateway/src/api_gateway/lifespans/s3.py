import asyncio
from contextlib import asynccontextmanager
import aioboto3
from aiokafka import AIOKafkaConsumer
from api_gateway.config import RUSTFS_PARAMS, LIFECYCLE_CONFIG, settings
from fastapi import FastAPI
from types_aiobotocore_s3 import S3Client
from asyncio import Task


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
    # 3. Connection is automatically closed when the app shuts down


@asynccontextmanager
async def s3_lifespan_processed(app: FastAPI):
    # 1. Initialize the Session and Client once
    session = aioboto3.Session()
    # We use an ExitStack or simply enter the context manager here
    async with session.client("s3", **RUSTFS_PARAMS) as s3_client:
        s3_client: S3Client  # Manual type hint for IDE support
        # 2. Store the persistent client in app.state
        app.state.s3_client_processed = s3_client
        await s3_client.put_bucket_lifecycle_configuration(
            Bucket=settings.S3_BUCKET_PROCESSED,
            LifecycleConfiguration=LIFECYCLE_CONFIG,
        )
        yield
    # 3. Connection is automatically closed when the app shuts down
