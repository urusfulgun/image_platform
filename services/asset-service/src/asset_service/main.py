"""AssetService — FastAPI application entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from asset_service.api.images import router as images_router
from asset_service.api.projects import router as projects_router
from asset_service.kafka.consumer import start_consumer
from asset_service.kafka.producer import producer
from asset_service.s3.client import ensure_buckets
from asset_service.lifespans.hub import lifespan_manager

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    ensure_buckets()
    await producer.start()
    consumer_task = asyncio.create_task(start_consumer())
    log.info("AssetService started.")
    yield
    # Shutdown
    consumer_task.cancel()
    await asyncio.gather(consumer_task, return_exceptions=True)
    await producer.stop()
    log.info("AssetService shut down.")


lifespan_manager.add_handler(lifespan)


app = FastAPI(
    title="AssetService",
    description="Image and project management for Image Platform",
    version="0.1.0",
    lifespan=lifespan_manager,
)

app.include_router(projects_router)
app.include_router(images_router)


@app.get("/health", tags=["ops"])
async def health():
    return JSONResponse({"status": "ok"})
