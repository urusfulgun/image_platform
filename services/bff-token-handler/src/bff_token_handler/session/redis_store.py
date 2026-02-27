"""Redis-backed session store for BFF Token Handler.

Stores serialized TokenSet by session ID so the browser
never receives or sees an access token.
"""

from abc import ABC, abstractmethod
import json
import secrets
from string.templatelib import Template, Interpolation

from shared_core.schemas.security.user_session import UserSession


import redis.asyncio as aioredis

from bff_token_handler.settings import settings
from shared_core.dto.key_pair import KeyPair
from shared_core.schemas.security.token_set import TokenSet
from shared_core.schemas.security.session_data import SessionData
from shared_core.utils.key_pair_marshalling import (
    marshalling_key_pair,
    unmarshalling_key_pair_from_model,
)


async def redis_key_tag(it: Template) -> str:
    """Processes the T-string specifically for Redis."""
    result = []
    # Template.args is an iterable of str | Interpolation
    for part in it.args:
        if isinstance(part, str):
            result.append(part)
        elif isinstance(part, Interpolation):
            # We can force the value to be a string or validate it
            val = str(part.value)
            if ":" in val:
                raise ValueError("Key subparts for Redis cannot contain colons!")
            result.append(val)
    return "".join(result)


class RedisSession:
    _redis: aioredis.Redis

    @property
    def redis(self) -> aioredis.Redis:
        return self._redis

    @redis.setter
    def redis(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def connect(self) -> None:
        self._redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.aclose()


class AbstractRedisStore(ABC):
    _redis: aioredis.Redis

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__()
        self._redis = redis

    @abstractmethod
    def _key(self, key: str) -> str:
        raise NotImplementedError


class SessionStore(AbstractRedisStore):
    """Async Redis session store."""

    def _key(self, key: str) -> str:
        """Creates session ID key `session:session_id` for Redis to find a value with it"""
        # return redis_key_tag(t"session:{key}")
        return f"session:{key}"

    async def create(self, token_set: TokenSet, key_pair: KeyPair) -> str:
        """Persist a TokenSet and return a new, random session ID."""
        session_id = secrets.token_urlsafe(32)
        token_data = token_set.model_dump(mode="json")
        key_pair_model = marshalling_key_pair(key_pair)

        data = SessionData(
            token_set=token_data, key_pair=key_pair_model
        ).model_dump_json()

        await self._redis.setex(
            self._key(session_id),
            settings.session_ttl_seconds,
            data,
        )
        return session_id

    async def get(self, session_id: str) -> UserSession | None:
        """Retrieve a TokenSet by session ID. Returns None if not found."""
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            return None
        data = SessionData.model_validate_json(raw)
        key_pair: KeyPair = unmarshalling_key_pair_from_model(data.key_pair)
        user_session = UserSession(token_set=data.token_set, key_pair=key_pair)
        return user_session

    async def delete(self, session_id: str) -> None:
        """Delete a session by ID (logout)."""
        await self._redis.delete(self._key(session_id))


class CodeVerifierStore:
    """Async Redis PKCE code verifier store."""

    _redis: aioredis.Redis

    def __init__(self, redis: aioredis.Redis):
        self._redis = redis

    async def _key(self, key: str) -> str:
        """Creates PKCE state as key `pkce:state` for Redis to find a value with it"""
        # return await redis_key_tag(t"pkce:{key}")
        return f"pkce:{key}"

    async def get_pkce(self, state: str) -> str | None:
        return await self._redis.get(await self._key(state))

    async def create_pkce(self, state: str, ttl: int, code_verifier: str):
        await self._redis.setex(await self._key(state), ttl, code_verifier)

    async def delete_pkce(self, state: str):
        await self._redis.delete(await self._key(state))


# Module-level singleton — shared via FastAPI state


async def get_session_store(redis_client: aioredis.Redis) -> SessionStore:
    return SessionStore(redis_client)


async def get_code_verifier_store(redis_client: aioredis.Redis) -> CodeVerifierStore:
    return CodeVerifierStore(redis_client)


async def get_redis_session() -> RedisSession:
    redis_session = RedisSession()
    return redis_session
