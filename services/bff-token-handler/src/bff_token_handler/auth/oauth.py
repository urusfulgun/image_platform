"""OAuth2 Authorization Code + PKCE flow helpers."""
import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import httpx

from bff_token_handler.settings import settings
from bff_token_handler.auth.dpop import create_dpop_proof


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge pair.

    Returns:
        (code_verifier, code_challenge) both as strings.
    """
    code_verifier = _b64url(secrets.token_bytes(32))
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = _b64url(digest)
    return code_verifier, code_challenge


def build_auth_url(state: str, code_challenge: str) -> str:
    """Build the KeyCloak Authorization URL for PKCE flow."""
    base = (
        f"{settings.keycloak_url}/realms/{settings.realm}"
        "/protocol/openid-connect/auth"
    )
    params = {
        "client_id": settings.client_id,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": settings.redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{base}?{urlencode(params)}"


@dataclass
class TokenSet:
    """Container for token introspection result."""
    access_token: str
    refresh_token: Optional[str]
    id_token: Optional[str]
    expires_in: int
    token_type: str = "Bearer"


async def exchange_code(code: str, code_verifier: str) -> TokenSet:
    """Exchange an authorization code for tokens using PKCE + DPoP.

    Args:
        code: Authorization code from KeyCloak callback.
        code_verifier: PKCE verifier matching the challenge sent in auth URL.

    Returns:
        TokenSet with access/refresh/id tokens.
    """
    token_endpoint = (
        f"{settings.keycloak_url}/realms/{settings.realm}"
        "/protocol/openid-connect/token"
    )
    dpop_proof = create_dpop_proof("POST", token_endpoint)

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
