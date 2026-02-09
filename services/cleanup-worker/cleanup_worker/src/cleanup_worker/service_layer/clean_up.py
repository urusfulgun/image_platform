import asyncio
import json
from aiokafka import AIOKafkaConsumer
from mypy_boto3_s3 import S3Client


async def consume_cleanup_events(s3_client: S3Client, settings):
    """
    Listens for DELETED events and purges files from RustFS buckets.
    """
    consumer = AIOKafkaConsumer(
        "image.lifecycle",
        bootstrap_servers=settings.KAFKA_URL,
        group_id="storage-cleanup-group",
        auto_offset_reset="earliest",
    )

    await consumer.start()
    try:
        async for msg in consumer:
            event_data = json.loads(msg.value)

            # Filter for DELETED events only
            if event_data.get("status") != "DELETED":
                continue

            image_id = event_data["image_id"]
            storage_key = event_data["storage_key"]  # e.g., "raw/uuid.raw"

            # 1. Delete the Raw File
            await delete_from_s3(s3_client, settings.RUSTFS_RAW_BUCKET, storage_key)

            # 2. Delete Processed Variants
            # Since the processor creates 'normal', 'preview', and 'thumbnail'
            # we must purge those specific keys from the processed bucket
            for folder in ["normal", "preview", "thumbnail"]:
                processed_key = f"{folder}/{image_id}.avif"
                await delete_from_s3(
                    s3_client, settings.RUSTFS_PROCESSED_BUCKET, processed_key
                )

    finally:
        await consumer.stop()


async def delete_from_s3(s3_client: S3Client, bucket: str, key: str):
    """Helper to perform the physical deletion."""
    try:
        # Note: Boto3/Aiobotocore delete_object is idempotent.
        # If the file is already gone, it won't throw an error.
        await s3_client.delete_object(Bucket=bucket, Key=key)
        print(f"STORAGE_CLEANUP: Deleted {key} from {bucket}")
    except Exception as e:
        print(f"STORAGE_CLEANUP_ERROR: Failed to delete {key}: {e}")
