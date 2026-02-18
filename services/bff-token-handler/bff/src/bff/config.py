from pydantic import Field, SecretStr, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class BFFSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Keycloak / OIDC Identity Provider
    KEYCLOAK_BASE_URL: HttpUrl = Field(..., alias="KEYCLOAK_URL")
    OIDC_CLIENT_ID: str = "image-platform-bff"
    OIDC_CLIENT_SECRET: SecretStr
    OIDC_REALM: str = "image-platform"

    # Security & Session
    # Used for itsdangerous/fernet encryption of the session cookie
    SESSION_ENCRYPTION_KEY: SecretStr
    COOKIE_SECURE: bool = True
    COOKIE_NAME: str = "__Host-session"

    # DPoP Configuration
    # Private key (EC or RSA) in PEM format for signing DPoP JWTs
    DPOP_PRIVATE_KEY_PEM: SecretStr

    # Downstream API Gateway
    API_GATEWAY_URL: HttpUrl

    REDIS_URL: HttpUrl = "redis://localhost:6379/0"

    # BFF url
    BFF_URL: HttpUrl

    HOME_PAGE: HttpUrl

    @property
    def authorize_url(self) -> str:
        # self.KEYCLOAK_BASE_URL is inside cluster network but localhost outside
        return f"{self.KEYCLOAK_BASE_URL}/oauth2/default/v1/authorize"

    @property
    def redirect_uri(self) -> str:
        # self.BFF_URL is inside cluster network but localhost outside
        return f"{self.BFF_URL}/authorization-code/callback"

    @property
    def oidc_well_known_url(self) -> str:
        return f"{self.KEYCLOAK_BASE_URL}/realms/{self.OIDC_REALM}/.well-known/openid-configuration"
    
    @property
    def token_url(self) -> str:
        return f"{self.KEYCLOAK_BASE_URL}/realms/{self.OIDC_REALM}/protocol/openid-connect/token"


settings = BFFSettings()
