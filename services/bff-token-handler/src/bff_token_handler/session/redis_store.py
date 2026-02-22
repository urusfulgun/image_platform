"""Redis-backed session store for BFF Token Handler.

Stores serialized TokenSet by session ID so the browser
never receives or sees an access token.
"""
import json
import secrets
from typing import Optional

import redis.asyncio as aioredis

from bff_token_handler.auth.oauth import TokenSet
from bff_token_handler.settings import settings


class SessionStore:
    """Async Redis session store."""

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        self._redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.aclose()

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    async def create(self, token_set: TokenSet) -> str:
        """Persist a TokenSet and return a new, random session ID."""
        session_id = secrets.token_urlsafe(32)
        data = {
            "access_token": token_set.access_token,
            "refresh_token": token_set.refresh_token,
            "id_token": token_set.id_token,
            "expires_in": token_set.expires_in,
            "token_type": token_set.token_type,
        }
        await self._redis.setex(
            self._key(session_id),
            settings.session_ttl_seconds,
            json.dumps(data),
        )
        return session_id

    async def get(self, session_id: str) -> Optional[TokenSet]:
        """Retrieve a TokenSet by session ID. Returns None if not found."""
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            return None
        data = json.loads(raw)
        return TokenSet(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            id_token=data.get("id_token"),
            expires_in=data.get("expires_in", 300),
            token_type=data.get("token_type", "Bearer"),
        )

    async def delete(self, session_id: str) -> None:
        """Delete a session by ID (logout)."""
        await self._redis.delete(self._key(session_id))


# Module-level singleton — shared via FastAPI state
session_store = SessionStore()
