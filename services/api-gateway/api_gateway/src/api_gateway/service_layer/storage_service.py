import uuid
import boto3
from mypy_boto3_s3 import S3Client

from botocore.config import Config
from api_gateway.config import settings


class StorageService:
    s3_client: S3Client

    def __init__(self):
        # RustFS is S3-compatible; use standard boto3
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",  # Often a dummy value for custom S3
        )

    async def generate_upload_url(self, image_id: uuid.UUID, extension: str = "raw"):
        """
        Generates a PUT presigned URL for the client to upload the raw image.
        The key is the UUID7 to ensure uniqueness and database alignment.
        """
        object_key = f"raw/{image_id}.{extension}"

        url = self.s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": settings.S3_BUCKET_UPLOADS,
                "Key": object_key,
                "ContentType": "image/generic",  # Or specific based on request
            },
            ExpiresIn=3600,  # 1 hour
        )
        return url, object_key
