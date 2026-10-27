import logging
from abc import ABC, abstractmethod

# from sqlalchemy import insert
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from asset_service.db import models
from shared_core.schemas.debezium.events import KeycloakUserEvent

log = logging.getLogger(__name__)


class UserSyncHandler(ABC):
    @abstractmethod
    async def handle(self, event: KeycloakUserEvent, db_session):
        pass


class UpsertUserHandler(UserSyncHandler):
    """Handles 'r' (read/snapshot), 'c' (create), and 'u' (update)"""

    async def handle(self, event: KeycloakUserEvent, session: AsyncSession) -> bool:
        # 1. Include 'r' for the initial sync snapshot
        if event.op not in {"c", "u", "r"}:
            return False

        # 2. Safety Check: If Keycloak sends a partial record (common on 'c'),
        # you might want to skip or handle it so you don't nullify existing data.
        if event.email is None and event.op == "u":
            log.debug(
                f"⏭️ Skipping update for {event.sub} - No email provided (partial event)"
            )
            return True

        log.info(f"📥🔄 Syncing user: {event.sub} (Op: {event.op})")

        stmt = insert(models.UserModel).values(
            kc_sub=event.sub,
            email=event.email,
            # username=event.username,  # Added based on your event logs
            # is_enabled=event.enabled,  # Added based on your event logs
        )

        # 3. UPSERT logic: update values ONLY if they changed or aren't null
        #    in the event
        stmt = stmt.on_conflict_do_update(
            index_elements=["kc_sub"],
            set_={
                "email": stmt.excluded.email,
                # "is_enabled": stmt.excluded.is_enabled,
            },
        )

        await session.execute(stmt)
        await session.commit()
        return True


class DeleteUserHandler(UserSyncHandler):
    async def handle(self, event: KeycloakUserEvent, db_session: AsyncSession):
        # Handle the explicit delete operation
        if event.op == "d" or event.deleted:
            log.info(f"🗑️ Deleting user: {event.sub}")
            await db_session.execute(
                delete(models.UserModel).where(models.UserModel.kc_sub == event.sub)
            )
            await db_session.commit()
            return True
        return False


class UserEventOrchestrator:
    handlers: list[UserSyncHandler]

    def __init__(self):
        # Delete runs first so a record flagged __deleted is never upserted
        self.handlers = [
            DeleteUserHandler(),
            UpsertUserHandler(),
        ]

    async def process(
        self,
        event: KeycloakUserEvent | None,
        user_id_from_key: str,
        db_session: AsyncSession,
    ):
        # Handle Kafka Tombstone (Value is null, but Key contains the ID)
        if event is None:
            log.info(f"🪦 Received tombstone for user: {user_id_from_key}")
            await db_session.execute(
                delete(models.UserModel).where(
                    models.UserModel.kc_sub == user_id_from_key
                )
            )
            await db_session.commit()
            return

        for handler in self.handlers:
            if await handler.handle(event, db_session):
                return

        log.info(f"⚠️ No handler found for operation: {event.op}")
