import json
import uuid
from api_gateway.db import async_session_factory
from api_gateway.domain.models import ImageMetadata
from api_gateway.domain.batch_finalization import finalize_batch_if_ready


async def process_s3_record(raw_payload: bytes):
    """
    Parses S3 event from Kafka, updates image status,
    and triggers batch finalization.
    """
    try:
        data: dict = json.loads(raw_payload)
        # S3 Events can contain multiple records in one message
        records: list[dict[str, dict[str, dict[str, str]]]] = data.get("Records", [])

        for record in records:
            s3_key = record.get("s3", {}).get("object", {}).get("key")
            if not s3_key:
                continue

            # Path format: "raw/{uuid}.raw" -> extract "{uuid}"
            try:
                # We split by "/" and then split the filename from its extension
                filename = s3_key.split("/")[-1]
                image_uuid_str = filename.split(".")[0]
                image_id = uuid.UUID(image_uuid_str)
            except (ValueError, IndexError):
                print(f"Skipping malformed S3 key: {s3_key}")
                continue

            # Use the session factory for a fresh scoped session
            async with async_session_factory() as session:
                async with session.begin():  # Start transaction
                    # 1. Update Image Status
                    image = await session.get(ImageMetadata, image_id)
                    if not image:
                        print(f"Image {image_id} not found in DB. Event ignored.")
                        continue

                    if image.status != "UPLOADED":
                        image.status = "UPLOADED"
                        session.add(image)
                        # We flush here so the count in 'finalize_batch_if_ready'
                        # sees the updated status
                        await session.flush()

                    # 2. Check if the parent batch is now complete
                    # This logic was defined in the previous step
                    await finalize_batch_if_ready(image.batch_id, session)

                # Transaction commits here automatically on exit of 'async with'

    except json.JSONDecodeError:
        print("Failed to decode Kafka message as JSON.")
    except Exception as e:
        print(f"Unexpected error in process_s3_record: {e}")
