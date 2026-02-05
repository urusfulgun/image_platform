from pydantic import Field, SecretStr, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database: Shadow Users & Project Metadata
    POSTGRES_USER: SecretStr
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_HOST: SecretStr = Field(..., description="PostgreSQL DSN (asyncpg)")
    POSTGRES_DB: SecretStr

    # S3 / RustFS Configuration
    S3_ENDPOINT_URL: HttpUrl
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: SecretStr
    S3_BUCKET_UPLOADS: str = "raw-uploads"
    S3_BUCKET_PROCESSED: str = "processed-images"
    S3_REGION: str = "us-east-1"

    # Message Broker
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_TOPIC_USER_REGISTRATION: str = "identity.user.registered"
    KAFKA_TOPIC_BATCH_PROCESS: str = "image.batch.created"

    # Security Validation
    # Public Key from Keycloak to verify JWS signatures on tokens
    OIDC_JWKS_URL: HttpUrl
    # Audience validation for tokens
    EXPECTED_AUDIENCE: str = "account"


settings = GatewaySettings()
