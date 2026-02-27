"""AssetService — FastAPI application entry point."""
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from asset_service.api.images import router as images_router
from asset_service.api.projects import router as projects_router
from asset_service.lifespans.hub import lifespan_manager

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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
