"""BFF Token Handler settings."""

from pathlib import Path

from pydantic_settings import SettingsConfigDict

from shared_core.schemas.security.config import KeyCloakOpenIDConfig
from shared_core.settings import BaseAppSettings

# Docker secrets mount; one file per field (e.g. /run/secrets/client_secret).
SECRETS_DIR = Path("/run/secrets")


class BffSettings(BaseAppSettings):
    """Configuration for the BFF Token Handler service."""

    # Merged with BaseAppSettings.model_config by pydantic.
    model_config = SettingsConfigDict(
        # Only when mounted, so local runs and tests don't warn about a missing dir.
        secrets_dir=SECRETS_DIR if SECRETS_DIR.is_dir() else None,
    )

    base_url: str = "http://image-platform"

    # KeyCloak
    keycloak_url: str = "http://keycloak:8080"
    realm: str = "image-platform"
    client_id: str = "bff-client"
    # public_client_id: str = "bff-client"
    public_client_id: str = "frontend-client"
    # Required: env CLIENT_SECRET or the secrets file /run/secrets/client_secret.
    client_secret: str
    redirect_uri: str = "http://image-platform/api/authorization-code/callback"

    # Redis session store
    redis_url: str = "redis://redis-session:6379/0"
    session_cookie_name: str = "sid"
    session_cookie_secure: bool = False  # Set True in production with HTTPS
    session_ttl_seconds: int = 3600

    # Upstream AssetService
    asset_service_url: str = "http://asset-service:8000"
    pkce_code_challenge_method: str = "S256"

    # App
    debug: bool = True

    @property
    def frontend_url(self) -> str:
        return self.base_url

    @property
    def authorize_url(self) -> str:
        # self.KEYCLOAK_BASE_URL is inside cluster network but localhost outside
        return f"{self.keycloak_url}/oauth2/default/v1/authorize"

    @property
    def oidc_well_known_url(self) -> str:
        return (
            f"{self.keycloak_url}/realms/{self.realm}/.well-known/openid-configuration"
        )

    @property
    def token_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"

    @property
    def userinfo_url(self) -> str:
        return (
            f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/userinfo"
        )

    @property
    def logout_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/logout"

    @property
    def keycloak_revocation_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/revoke"


settings = BffSettings()

keycloak_config = KeyCloakOpenIDConfig(
    server_url=settings.keycloak_url,
    client_id=settings.client_id,
    realm_name=settings.realm,
    client_secret_key=settings.client_secret,
)
