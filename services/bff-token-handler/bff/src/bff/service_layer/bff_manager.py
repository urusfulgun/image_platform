import asyncio
import logging
from typing import Literal, Self
import httpx
from pydantic import HttpUrl
import redis.asyncio as redis
import json
from cryptography.hazmat.primitives import serialization
from shared_core.abstract.dpop_key_registry import DPoPKeyRegistry
from shared_core.services.dpop_session import DPoPAuth
from shared_core.abstract.cache import AsyncLRUCache
from bff.service_layer.redis_schemas import RedisSessionPayload
from bff.domain.models import UserSession
from joserfc import jwk
from bff.config import BFFSettings


logger = logging.getLogger(__name__)


class RedisBFFManager:
    registry: DPoPKeyRegistry
    ttl: int
    _local_cache: AsyncLRUCache

    @classmethod
    async def create(
        cls,
        registry: DPoPKeyRegistry,
    ) -> Self:
        instance = cls()
        instance.registry = registry
        instance._local_cache = AsyncLRUCache(maxsize=500)
        instance.ttl = 3600  # 1 hour session
        return instance

    async def create_session(
        self,
        session_id: str,
        tokens: dict[Literal["access_token", "refresh_token"], str],
        kid: str,
        private_key: jwk.ECKey,
        redis_client: redis.Redis,
    ):
        record_key = f"session:{session_id}"
        # 1. Serialize the private key to PEM format

        pem_key: str = private_key.as_pem(private=True).decode("utf-8")

        # 2. Store everything in a Redis Hash
        session_payload: RedisSessionPayload = RedisSessionPayload(
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            kid=kid,
            private_key=pem_key,
            last_nonce=None,
        )
        await redis_client.setex(
            name=record_key,
            time=self.ttl,
            value=session_payload.model_dump_json(exclude_unset=True),
        )

    async def update_redis_nonce(
        self,
        session_id: str,
        client: httpx.AsyncClient,
        redis_client: redis.Redis,
    ) -> None:
        """Background task to sync the latest DPoP-Nonce to Redis."""
        record_key: str = f"session:{session_id}"
        raw: str | None = await redis_client.get(record_key)
        if raw is None:
            raise ValueError("session_id is not in registry (Redis)")
        session_data: RedisSessionPayload = RedisSessionPayload.model_validate_json(raw)
        dpop_auth: DPoPAuth = client.auth
        last_nonce: str | None = dpop_auth.server_nonce
        updated_session_data = RedisSessionPayload(
            access_token=session_data.access_token,
            refresh_token=session_data.refresh_token,
            private_key=session_data.private_key,
            kid=session_data.kid,
            last_nonce=last_nonce,
        )
        await redis_client.setex(
            name=record_key,
            time=self.ttl,
            value=updated_session_data.model_dump_json(exclude_unset=True),
        )

    async def get_client(
        self,
        session_id: str,
        redis_client: redis.Redis,
        settings: BFFSettings,
    ) -> httpx.AsyncClient | None:

        # LAYER 1: Memory (Fastest - preserves DPoP Nonces)
        cached_client = self._local_cache.get(session_id)
        if cached_client:
            return cached_client

        # LAYER 2: Redis (Source of Truth)
        raw_data = await redis_client.get(f"session:{session_id}")
        if not raw_data:
            return None

        session_data = RedisSessionPayload.model_validate_json(raw_data)
        signer = self.registry.reconstitute_signer(
            session_data.kid, session_data.private_key
        )  # Reconstitution logic here

        # Initialize the custom Auth flow
        auth = await self.create_dpop_auth(
            signer=signer,
            access_token=session_data.access_token,
            refresh_token=session_data.refresh_token,
            refresh_url=settings.token_url
        )

        # Optional: Restore the last known nonce to avoid a 401 on first hit
        if session_data.last_nonce:
            auth.server_nonce = session_data.last_nonce

        # a client with the auth pre-configured
        client = httpx.AsyncClient(auth=auth, timeout=10.0)

        # Update the LRU cache for subsequent requests
        self._local_cache.put(session_id, client)

        return client
    
    async def create_dpop_auth(
            signer,
            access_token: str,
            refresh_token: str,
            refresh_url: HttpUrl,
    ) -> DPoPAuth:
        """
        Initialization of the custom Auth flow
        
        :param signer: Description
        :param access_token: Description
        :type access_token: str
        :param refresh_token: Description
        :type refresh_token: str
        :param refresh_url: Description
        :type refresh_url: HttpUrl
        :return: Description
        :rtype: DPoPAuth
        """
        return DPoPAuth(
            signer=signer,
            access_token=access_token,
            refresh_token=refresh_token,
            refresh_url=refresh_url,
        )
    
    async def update_session_data(
        self,
        session_id: str,
        access_token: str,
        refresh_token: str,
        last_nonce: str | None,
        redis_client: redis.Redis,
    ) -> None:
        """
        Updates the existing session in Redis with new tokens or nonces.
        This is typically called by a background task after a DPoPAuth flow.
        """
        record_key = f"session:{session_id}"
        
        # 1. Fetch current data to preserve the private_key and kid
        raw_data = await redis_client.get(record_key)
        if not raw_data:
            logger.warning(f"Attempted to update non-existent session: {session_id}")
            return

        # 2. Parse and update
        try:
            current_payload = RedisSessionPayload.model_validate_json(raw_data)
            
            # Update mutable fields
            updated_payload = current_payload.model_copy(update={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "last_nonce": last_nonce
            })

            # 3. Persist back to Redis with the original TTL
            # We use setex to ensure the session doesn't become immortal
            await redis_client.setex(
                name=record_key,
                time=self.ttl,
                value=updated_payload.model_dump_json(exclude_unset=True)
            )
            
            logger.debug(f"Successfully synced DPoP state to Redis for session {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to update Redis session data: {e}")

    async def shutdown(self):
        """Call this during the FastAPI/Starlette shutdown event."""
        logger.info("Closing all cached DPoP clients...")
        # Get all clients currently in the LRU
        clients: list[httpx.AsyncClient] = list(self._local_cache.cache.values())
        self._local_cache.cache.clear()

        # Close them all concurrently
        await asyncio.gather(
            *[c.aclose() for c in clients if hasattr(c, "aclose")],
            return_exceptions=True,
        )
