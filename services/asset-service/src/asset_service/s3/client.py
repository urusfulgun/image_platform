"""S3 client wrapper for RustFS (S3-compatible)."""

import logging

import boto3
from botocore.config import Config

from asset_service.settings import settings

log = logging.getLogger(__name__)

_s3_client = None


def get_s3_client_():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4"),
        )
    return _s3_client


def get_s3_client():
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
        region_name=settings.s3_region,
    )
    return s3


def ensure_buckets() -> None:
    """Create required buckets if they don't exist."""
    client = get_s3_client()
    for bucket in [settings.raw_bucket, settings.processed_bucket]:
        try:
            client.head_bucket(Bucket=bucket)
        except Exception:
            client.create_bucket(Bucket=bucket)
            log.info("Created bucket: %s", bucket)


def generate_upload_presigned_url(
    key: str,
    expiry: int = 3600,
    content_type: str = "application/octet-stream",
) -> str:
    """Generate a pre-signed URL for direct browser-to-S3 upload.

    Args:
        key: The S3 object key (path within the raw bucket).
        expiry: URL validity in seconds.
        content_type: Expected Content-Type header for the upload.

    Returns:
        Pre-signed PUT URL string.
    """
    client = get_s3_client()
    return client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.raw_bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expiry,
    )


def generate_download_presigned_url(
    key: str, bucket: str | None = None, expiry: int = 3600
) -> str:
    """Generate a pre-signed URL for downloading a processed image."""
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket or settings.processed_bucket, "Key": key},
        ExpiresIn=expiry,
    )
