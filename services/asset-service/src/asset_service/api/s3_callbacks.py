import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from asset_service.dependencies.clients import get_kafka_producer
from asset_service.dependencies.domain import get_image_service
from asset_service.domain.images import ImageService
from asset_service.kafka.producer import AssetKafkaProducer
from asset_service.settings import settings
from shared_core.events.kafka_events import ImageRawUploadedEvent

router = APIRouter(prefix="/callback", tags=["callbacks"])

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def verify_rustfs_token(
    request: Request, authorization: Annotated[str | None, Header()] = None
):
    """
    Security dependency to ensure the request actually comes from our Rustfs instance.
    """
    payload = await request.json()
    headers = request.headers
    webhook_token = authorization.split(" ")[1]
    if webhook_token != settings.rustfs_webhook_token:
        log.warning(
            f"Unauthorized callback attempt with token: {webhook_token}. "
            f"Headers {headers} and Payload \n {payload};"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing webhook token.",
        )


@router.post(
    "/rustfs",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
    dependencies=[Depends(verify_rustfs_token)],
)
async def rustfs_event_callback(
    request: Request,
    image_svc: Annotated[ImageService, Depends(get_image_service)],
    kafka_producer: Annotated[AssetKafkaProducer, Depends(get_kafka_producer)],
):
    """
    Unified Webhook for Rustfs events.
    Handles both successful uploads and manual S3 deletions.
    """
    try:
        payload: dict = await request.json()
        records = payload.get("Records", [])

        for record in records:
            event_name = record.get("eventName", "")
            s3_key: str = record["s3"]["object"]["key"].replace("%2F", "/")

            # --- CASE 1: UPLOAD (ObjectCreated) ---
            if "ObjectCreated" in event_name:
                await handle_upload_event(s3_key, image_svc, kafka_producer)

            # --- CASE 2: DELETE (ObjectRemoved) ---
            elif "ObjectRemoved" in event_name:
                await handle_delete_event(s3_key, image_svc)

        return {"status": "success"}

    except Exception as e:
        log.error(f"Rustfs callback failed: {e}")
        raise HTTPException(status_code=500, detail="Internal processing error") from e


async def handle_upload_event(
    s3_key: str, image_svc: ImageService, kafka_producer: AssetKafkaProducer
):
    """Logic for handling successful S3 uploads."""
    image_model = await image_svc.get_by_s3_path(s3_key)
    if not image_model:
        log.warning(f"Upload callback for {s3_key} but no DB record found.")
        return

    event = ImageRawUploadedEvent(
        image_id=image_model.id,
        project_id=image_model.project_id,
        raw_s3_path=image_model.raw_s3_path,
        raw_format=image_model.raw_format,
        file_size_bytes=image_model.file_size_bytes,
    )
    await kafka_producer.publish_image_raw_uploaded(event)
    log.info(f"Verified upload for image: {image_model.id}")


async def handle_delete_event(s3_key: str, image_svc: ImageService):
    """
    Handles out-of-band deletions (e.g. manual S3 delete).
    Ensures the DB record is marked as deleted if the file is gone.
    """
    image_model = await image_svc.get_by_s3_path(s3_key)

    if image_model and not image_model.deleted_at:
        log.info(f"S3 object {s3_key} was deleted externally. Syncing DB...")
        # You'll need to pass the project_id to your existing delete method
        # or create a simpler 'mark_as_deleted' internal method in ImageService
        await image_svc.delete_confirm(
            image_id=image_model.id,
            project_id=image_model.project_id,
        )
