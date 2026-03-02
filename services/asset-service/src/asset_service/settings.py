"""AssetService settings."""
from pydantic import Field
from shared_core.settings import BaseAppSettings


class AssetSettings(BaseAppSettings):
    """Configuration for the AssetService."""

    # Database
    database_url: str = (
        "postgresql+asyncpg://asset_admin:dev-asset-password"
        "@postgres-asset-metadata:5432/asset_metadata"
    )

    # Kafka
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_consumer_group: str = "asset-service-group"
    user_event_topic: str = "keycloak-users"
    image_raw_uploaded_topic: str = "image.raw.uploaded"
    image_raw_presign_link_generated_topic: str = "image.raw.uploading_link_generated"

    # S3 / RustFS
    s3_endpoint_url: str = "http://rustfs:9000"
    s3_access_key: str = "OAhzGogEY7X61ZwjnSmH"
    s3_secret_key: str = "5XItB3Pon6syp7e1cxNvJOTfWlzigEZQkK2FM8Vh"
    s3_region: str = "us-east-1"
    raw_bucket: str = "raw-images"
    processed_bucket: str = "processed-images"

    # KeyCloak (for token validation)
    keycloak_url: str = "http://keycloak:8080"
    realm: str = "image-platform"


settings = AssetSettings()
