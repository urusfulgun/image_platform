import logging
from typing import Annotated

from asset_service.dependencies.clients import get_kafka_producer
from asset_service.dependencies.domain import get_image_service
from asset_service.domain.images import ImageService
from asset_service.kafka.producer import AssetKafkaProducer
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from shared_core.events.kafka_events import ImageRawUploadedEvent


router = APIRouter(prefix="/callback", tags=["callbacks"])

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# This should match the 'auth_token' in your rustfs config.toml
RUSTFS_SECRET_TOKEN = "your-secure-shared-secret"

async def verify_rustfs_token(request: Request, authorization: Annotated[str | None, Header()] = None):
    """
    Security dependency to ensure the request actually comes from our Rustfs instance.
    """
    payload = await request.json()
    headers = request.headers
    webhook_token = authorization.split(' ')[1]
    if webhook_token != RUSTFS_SECRET_TOKEN:
        log.warning(f"Unauthorized callback attempt with token: {webhook_token}. Headers {headers} and Payload \n {payload};")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Invalid or missing webhook token."
        )


@router.post(
    "/rustfs",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,  # Usually hide internal webhooks from public docs
    dependencies=[Depends(verify_rustfs_token)],
)
async def rustfs_upload_callback(
    request: Request,
    image_svc: Annotated[ImageService, Depends(get_image_service)],
    kafka_producer: Annotated[AssetKafkaProducer, Depends(get_kafka_producer)],
):
    """
    Webhook called by Rustfs after a successful PUT operation.
    This guarantees the file exists before we trigger the ImageProcessor.
    """
    try:
        # 1. Parse the S3 Event Notification JSON from Rustfs
        payload: dict = await request.json()
        records = payload.get("Records", [])

        for record in records:
            s3_key: str = record["s3"]["object"]["key"]

            # 2. Look up the pending metadata in our DB using the S3 path
            # You might need to add this method to your ImageService
            image_model = await image_svc.get_by_s3_path(s3_key.replace('%2F', '/'))

            if not image_model:
                log.warning(f"Callback received for S3 key {s3_key} but no DB record exists.")
                continue

            # 3. Only now do we publish to Kafka
            event = ImageRawUploadedEvent(
                image_id=image_model.id,
                project_id=image_model.project_id,
                raw_s3_path=image_model.raw_s3_path,
                raw_format=image_model.raw_format,  # Ensure this is in your model
                file_size_bytes=image_model.file_size_bytes,
            )

            await kafka_producer.publish_image_raw_uploaded(event)
            log.info(f"Verified upload and triggered Kafka for image: {image_model.id}")

        return {"status": "success", "message": "Events published to Kafka"}

    except Exception as e:
        log.error(f"Rustfs callback failed: {e}")
        # Return 200 or 202 anyway if you don't want Rustfs to retry
        # infinitely on a logic error, or 500 if you want a retry.
        raise HTTPException(status_code=500, detail="Callback processing failed")
