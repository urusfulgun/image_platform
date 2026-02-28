"""AssetService — FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logging.error(f"Validation failed for {request.url}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )
