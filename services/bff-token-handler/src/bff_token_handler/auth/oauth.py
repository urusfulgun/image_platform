"""OAuth2 Authorization Code + PKCE flow helpers."""

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode
from pydantic import BaseModel, HttpUrl

import httpx

from bff_token_handler.settings import settings
from bff_token_handler.auth.dpop import create_dpop_proof, KeyPair
from keycloak import KeycloakOpenID, pkce_utils, keycloak_uma


class KeyCloakOpenIDConfig(BaseModel):
    server_url: HttpUrl
    client_id: str
    realm_name: str
    client_secret_key: str


async def get_keycloak_openid(keycloak_config: KeyCloakOpenIDConfig) -> KeycloakOpenID:
    return KeycloakOpenID(**keycloak_config.model_dump(mode="json"))


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge pair.

    Returns:
        (code_verifier, code_challenge) both as strings.
    """
    code_challenge_method = settings.pkce_code_challenge_method
    code_verifier = pkce_utils.generate_code_verifier()
    code_challenge, _ = pkce_utils.generate_code_challenge(
        code_verifier, method=code_challenge_method
    )
    return code_verifier, code_challenge, code_challenge_method


def build_auth_url(
    keycloak_openid: KeycloakOpenID,
    state: str,
    code_challenge: str,
    code_challenge_method: str,
) -> str:
    """Build the KeyCloak Authorization URL for PKCE flow."""

    auth_url = keycloak_openid.auth_url(
        redirect_uri=settings.redirect_uri,
        scope="openid",
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )

    return auth_url


@dataclass
class TokenSet:
    """Container for token introspection result."""

    access_token: str
    refresh_token: Optional[str]
    id_token: Optional[str]
    expires_in: int
    token_type: str = "Bearer"


async def exchange_code(code: str, code_verifier: str, key_pair: KeyPair) -> TokenSet:
    """Exchange an authorization code for tokens using PKCE + DPoP.

    Args:
        code: Authorization code from KeyCloak callback.
        code_verifier: PKCE verifier matching the challenge sent in auth URL.

    Returns:
        TokenSet with access/refresh/id tokens.
    """
    token_endpoint = settings.token_url
    dpop_proof = create_dpop_proof("POST", token_endpoint, key_pair)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.client_id,
                "client_secret": settings.client_secret,
                "code": code,
                "redirect_uri": settings.redirect_uri,
                "code_verifier": code_verifier,
            },
            headers={"DPoP": dpop_proof},
        )
        resp.raise_for_status()
        data = resp.json()

    return TokenSet(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        id_token=data.get("id_token"),
        expires_in=data.get("expires_in", 300),
    )


async def introspect_token(access_token: str) -> dict:
    """Call KeyCloak token introspection to get user info claims."""
    userinfo_endpoint = (
        f"{settings.keycloak_url}/realms/{settings.realm}"
        "/protocol/openid-connect/userinfo"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
