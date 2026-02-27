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
    user_registered_topic: str = "user.registered"
    user_event_topic: str = "keycloak_events.public.user_entity"
    image_raw_uploaded_topic: str = "image.raw.uploaded"

    # S3 / RustFS
    s3_endpoint_url: str = "http://rustfs-s3:9000"
    s3_access_key: str = "rustfsadmin"
    s3_secret_key: str = "rustfspassword"
    s3_region: str = "us-east-1"
    raw_bucket: str = "raw-images"
    processed_bucket: str = "processed-images"

    # KeyCloak (for token validation)
    keycloak_url: str = "http://keycloak:8080"
    realm: str = "image-platform"


settings = AssetSettings()
