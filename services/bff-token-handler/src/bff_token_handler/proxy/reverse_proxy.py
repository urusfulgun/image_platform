"""Reverse proxy from BFF to AssetService.

Forwards authenticated requests to the AssetService, injecting a fresh
DPoP proof and the access token retrieved from the session store.
"""

import logging
from typing import Optional

import httpx
from fastapi import Request, Response

from bff_token_handler.auth.dpop import (
    create_dpop_proof,
    decode_jwt_token,
    generate_dpop_ath,
)
from bff_token_handler.session.redis_store import SessionStore
from bff_token_handler.settings import settings

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def proxy_request(request: Request, downstream_path: str) -> Response:
    """Forward an incoming request to AssetService as an authenticated proxy.

    Args:
        request: The incoming FastAPI Request.
        downstream_path: The path to forward to (e.g. "/projects").

    Returns:
        FastAPI Response mirroring the upstream reply.
    """
    session_store: SessionStore = request.app.state.session_store
    # --- Resolve session ---
    session_id: Optional[str] = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        return Response(
            content='{"detail":"Not authenticated"}',
            status_code=401,
            media_type="application/json",
        )

    token_set, key_pair = await session_store.get(session_id)
    if not token_set:
        return Response(
            content='{"detail":"Session expired"}',
            status_code=401,
            media_type="application/json",
        )

    # --- Build downstream URL ---
    upstream_url = f"{settings.asset_service_url}/{downstream_path.lstrip('/')}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    # --- Fresh DPoP proof for the upstream call ---
    ath_claim = generate_dpop_ath(token_set.access_token)
    dpop_proof = create_dpop_proof(
        request.method, upstream_url, key_pair, ath=ath_claim
    )

    # --- Forward headers (strip hop-by-hop) ---
    HOP_BY_HOP = {
        "host",
        "connection",
        "transfer-encoding",
        "upgrade",
        "authorization",
        "proxy-connection",
        "keep-alive",
    }
    forward_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP
    }
    _, info_claims, _ = decode_jwt_token(token_set.id_token)
    forward_headers["Authorization"] = f"DPoP {token_set.access_token}"
    forward_headers["DPoP"] = dpop_proof
    forward_headers["X-User-Sub"] = info_claims["sub"]

    # --- Stream body ---
    body = await request.body()

    log.info(f"SID ---> {str(session_id)}")
    log.info(f"Forward headers: {forward_headers}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        upstream_resp = await client.request(
            method=request.method,
            url=upstream_url,
            headers=forward_headers,
            content=body,
        )

    log.info(f"PROXY RESPONSE ---> {str(upstream_resp)}")

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=dict(upstream_resp.headers),
        media_type=upstream_resp.headers.get("content-type"),
    )
