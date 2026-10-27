from contextlib import asynccontextmanager
import logging

from asset_service.s3.client import ensure_buckets
from fastapi import FastAPI


log = logging.getLogger(__name__)


@asynccontextmanager
async def s3_client_lifespan(app: FastAPI):
    # Startup
    ensure_buckets()
    log.info("S3 lifespan started.")
    yield
    log.info("S3 lifespan shut down.")
