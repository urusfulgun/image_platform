"""Reverse proxy from BFF to AssetService.

Forwards authenticated requests to the AssetService, injecting a fresh
DPoP proof and the access token retrieved from the session store.
"""
from typing import Optional

import httpx
from fastapi import Request, Response

from bff_token_handler.auth.dpop import create_dpop_proof
from bff_token_handler.session.redis_store import SessionStore
from bff_token_handler.settings import settings


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
        return Response(content='{"detail":"Not authenticated"}', status_code=401,
                        media_type="application/json")

    token_set = await session_store.get(session_id)
    if not token_set:
        return Response(content='{"detail":"Session expired"}', status_code=401,
                        media_type="application/json")

    # --- Build downstream URL ---
    upstream_url = f"{settings.asset_service_url}/{downstream_path.lstrip('/')}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    # --- Fresh DPoP proof for the upstream call ---
    dpop_proof = create_dpop_proof(request.method, upstream_url, key_pair)

    # --- Forward headers (strip hop-by-hop) ---
    HOP_BY_HOP = {"host", "connection", "transfer-encoding", "upgrade",
                  "proxy-connection", "keep-alive"}
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in HOP_BY_HOP
    }
    forward_headers["Authorization"] = f"DPoP {token_set.access_token}"
    forward_headers["DPoP"] = dpop_proof

    # --- Stream body ---
    body = await request.body()

    async with httpx.AsyncClient(timeout=120.0) as client:
        upstream_resp = await client.request(
            method=request.method,
            url=upstream_url,
            headers=forward_headers,
            content=body,
        )

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=dict(upstream_resp.headers),
        media_type=upstream_resp.headers.get("content-type"),
    )
