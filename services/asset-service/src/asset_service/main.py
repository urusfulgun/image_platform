"""AssetService — FastAPI application entry point."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from asset_service.api.images import router as images_router
from asset_service.api.projects import router as projects_router
from asset_service.api.s3_callbacks import router as s3_callback_router
from asset_service.lifespans.hub import lifespan_manager

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


origins = [
    "http://localhost:4200",
    "http://rustfs:9000",
]


app = FastAPI(
    title="AssetService",
    description="Image and project management for Image Platform",
    version="0.1.0",
    lifespan=lifespan_manager,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],  # PUT is critical for S3 uploads
    allow_headers=["Content-Type", "Authorization", "DPoP"],
)

app.include_router(projects_router)
app.include_router(images_router)
app.include_router(s3_callback_router)


@app.get("/health", tags=["ops"])
async def health():
    return JSONResponse({"status": "ok"})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: Exception):
    logging.error(f"Validation failed for {request.url}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )
