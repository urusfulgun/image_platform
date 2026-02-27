"""BFF Token Handler settings."""
from pydantic import Field
from shared_core.schemas.security.config import KeyCloakOpenIDConfig
from shared_core.settings import BaseAppSettings


class BffSettings(BaseAppSettings):
    """Configuration for the BFF Token Handler service."""

    # KeyCloak
    keycloak_url: str = "http://keycloak:8080"
    realm: str = "image-platform"
    client_id: str = "bff-client"
    # public_client_id: str = "bff-client"
    public_client_id: str = "frontend-client"
    client_secret: str = "dev-bff-client-secret"
    redirect_uri: str = "http://localhost:80/api/authorization-code/callback"

    # Redis session store
    redis_url: str = "redis://redis-session:6379/0"
    session_cookie_name: str = "sid"
    session_ttl_seconds: int = 3600

    # Upstream AssetService
    asset_service_url: str = "http://asset-service:8001"
    pkce_code_challenge_method: str = 'S256'

    # App
    debug: bool = True

    @property
    def authorize_url(self) -> str:
        # self.KEYCLOAK_BASE_URL is inside cluster network but localhost outside
        return f"{self.keycloak_url}/oauth2/default/v1/authorize"

    @property
    def oidc_well_known_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.realm}/.well-known/openid-configuration"
    
    @property
    def token_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"
    
    @property
    def userinfo_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/userinfo"

    @property
    def logout_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/logout"


settings = BffSettings()

keycloak_config = KeyCloakOpenIDConfig(
        server_url=settings.keycloak_url,
        client_id=settings.client_id,
        realm_name=settings.realm,
        client_secret_key=settings.client_secret,
    )
