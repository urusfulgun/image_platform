"""BFF Token Handler settings."""
from pydantic import Field
from shared_core.settings import BaseAppSettings


class BffSettings(BaseAppSettings):
    """Configuration for the BFF Token Handler service."""

    # KeyCloak
    keycloak_url: str = "http://keycloak:8080"
    realm: str = "image-platform"
    client_id: str = "bff-client"
    client_secret: str = "dev-bff-client-secret"
    redirect_uri: str = "http://localhost/api/callback"

    # Redis session store
    redis_url: str = "redis://redis-session:6379/0"
    session_cookie_name: str = "sid"
    session_ttl_seconds: int = 3600

    # Upstream AssetService
    asset_service_url: str = "http://asset-service:8000"

    # App
    debug: bool = False


settings = BffSettings()
