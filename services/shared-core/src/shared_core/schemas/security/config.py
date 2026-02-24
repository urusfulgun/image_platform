from typing import Literal

from pydantic import BaseModel, HttpUrl


class KeyCloakCommonConfig(BaseModel):
    server_url: HttpUrl
    client_id: str
    realm_name: str


class KeyCloakOpenIDConfig(KeyCloakCommonConfig):
    client_secret_key: str


class KeyCloakDynamicClientConfig(KeyCloakCommonConfig):
    custom_headers: dict[Literal["DPoP"], str]
    client_secret_key: str
