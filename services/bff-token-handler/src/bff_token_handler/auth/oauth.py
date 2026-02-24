"""OAuth2 Authorization Code + PKCE flow helpers."""

import base64
import hashlib
import logging
import os
import secrets
from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import urlencode
from pydantic import BaseModel, HttpUrl

import httpx

from bff_token_handler.settings import settings, keycloak_config
from bff_token_handler.auth.dpop import create_dpop_proof, KeyPair, generate_dpop_ath
from keycloak import KeycloakOpenID, pkce_utils, keycloak_uma, urls_patterns
from keycloak import exceptions as kc_exc
from shared_core.schemas.security.config import (
    KeyCloakDynamicClientConfig,
    KeyCloakOpenIDConfig,
)
from shared_core.schemas.security.token_set import TokenSet


log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def get_keycloak_openid(keycloak_config: KeyCloakOpenIDConfig) -> KeycloakOpenID:
    return KeycloakOpenID(**keycloak_config.model_dump(mode="json"))


async def get_dynamic_client(keycloak_config: KeyCloakOpenIDConfig) -> KeycloakOpenID:
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


async def get_authorization_code(
    keycloak_client: KeycloakOpenID, code: str, code_verifier: str
) -> TokenSet:
    token = keycloak_client.token(
        grant_type="authorization_code",
        code=code,
        redirect_uri=settings.redirect_uri,
        code_verifier=code_verifier,
    )
    return TokenSet.model_validate(token)


async def exchange_code(
    code: str,
    code_verifier: str,
    key_pair: KeyPair,
) -> TokenSet:
    """Exchange an authorization code for tokens using PKCE + DPoP.

    Args:
        code: Authorization code from KeyCloak callback.
        code_verifier: PKCE verifier matching the challenge sent in auth URL.

    Returns:
        TokenSet with access/refresh/id tokens.
    """
    # Define the Token Endpoint for the DPoP proof
    # Keycloak Token Exchange with DPoP
    # In Docker, this is usually http://keycloak:8080/...
    token_endpoint = settings.token_url

    # Generate a fresh DPoP proof for this specific POST request
    dpop_proof = create_dpop_proof("POST", token_endpoint, key_pair)

    # RE-INITIALIZE the client with the custom DPoP header
    # This ensures the library attaches 'DPoP: <proof>' to the outgoing call
    dynamic_config: KeyCloakDynamicClientConfig = KeyCloakDynamicClientConfig(
        server_url=keycloak_config.server_url,
        client_id=settings.client_id,
        client_secret_key=settings.client_secret,
        realm_name=keycloak_config.realm_name,
        custom_headers={"DPoP": dpop_proof},
    )
    dynamic_client = await get_dynamic_client(keycloak_config=dynamic_config)

    # try:
    token_response: TokenSet = await get_authorization_code(
        dynamic_client, code, code_verifier
    )
    # except (kc_exc.KeycloakConnectionError, kc_exc.KeycloakPostError) as e:
    #     raise e
    return token_response


async def dpop_user_info(client: KeycloakOpenID, token: str) -> dict | bytes:
    """
    Get the user info object. (DPoP)

    The userinfo endpoint returns standard claims about the authenticated user,
    and is protected by a bearer token.

    http://openid.net/specs/openid-connect-core-1_0.html#UserInfo

    :param token: Access token
    :type token: str
    :returns: Userinfo object
    :rtype: dict | bytes
    """
    orig_bearer = (client.connection.headers or {}).get("Authorization")
    client.connection.add_param_headers("Authorization", "DPoP " + token)
    params_path = {"realm-name": client.realm_name}
    data_raw = client.connection.raw_get(
        urls_patterns.URL_USERINFO.format(**params_path)
    )
    (
        client.connection.add_param_headers("Authorization", orig_bearer)
        if orig_bearer is not None
        else client.connection.del_param_headers("Authorization")
    )
    res = kc_exc.raise_error_from_response(data_raw, kc_exc.KeycloakGetError)
    if not isinstance(res, (dict, bytes)):
        msg = (
            "Unexpected response type from userinfo. Expected 'dict | bytes', "
            f"received '{type(res)}', value: '{res}'."
        )
        raise TypeError(msg)

    return res


async def clean_bytes(data) -> dict | list | str:
    if isinstance(data, dict):
        return {k: clean_bytes(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_bytes(i) for i in data]
    elif isinstance(data, bytes):
        return data.decode('utf-8')
    return data


async def introspect_token(
    key_pair: KeyPair,
    access_token: str,
) -> dict | list | str:
    """Call KeyCloak token introspection to get user info claims."""
    ath_claim = generate_dpop_ath(access_token)
    dpop_proof = create_dpop_proof(
        "GET",
        settings.userinfo_url,
        key_pair,
        ath=ath_claim,
    )
    log.info(f"DPoP Proof header ---> {dpop_proof}")
    dynamic_config: KeyCloakDynamicClientConfig = KeyCloakDynamicClientConfig(
        server_url=keycloak_config.server_url,
        client_id=settings.client_id,
        client_secret_key=settings.client_secret,
        realm_name=keycloak_config.realm_name,
        custom_headers={"DPoP": dpop_proof},
    )
    dynamic_client = await get_dynamic_client(keycloak_config=dynamic_config)
    user_info_encoded: bytes = await dpop_user_info(dynamic_client, access_token)
    user_info: dict | list | str = await clean_bytes(user_info_encoded)
    return user_info
