from abc import ABC, abstractmethod
import logging

from shared_core.schemas.debezium.events import KeycloakUserEvent
from asset_service.db import models

# from sqlalchemy import insert
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


class UserSyncHandler(ABC):
    @abstractmethod
    async def handle(self, event: KeycloakUserEvent, db_session):
        pass


class UpsertUserHandler(UserSyncHandler):
    """Handles both 'c' (create) and 'u' (update) using PostgreSQL UPSERT"""

    async def handle(self, event: KeycloakUserEvent, session: AsyncSession) -> bool:
        if event.op not in {"c", "u"}:
            return False
        log.info(f"📥🔄 Upserting shadow user: {event.sub}")

        # SQL Alchemy Core / ORM Upsert logic
        # Assuming you have a User model defined in your project
        stmt = insert(models.UserModel).values(
            kc_sub=event.sub,
            email=event.email,
        )

        # If the 'sub' already exists, update the other fields
        stmt = stmt.on_conflict_do_update(
            index_elements=["kc_sub"],
            set_={
                "email": event.email,
            },
        )

        await session.execute(stmt)
        await session.commit()
        return True


# class CreateUserHandler(UserSyncHandler):
#     async def handle(self, event: KeycloakUserEvent, db_session):
#         if event.op == "c":
#             log.info(f"📥 Creating shadow user: {event.username} ({event.sub})")
#             # SQL: INSERT INTO users (sub, username, email) VALUES (...)
#             # ON CONFLICT (sub) DO NOTHING (or Update)
#             return True
#         return False


# class UpdateUserHandler(UserSyncHandler):
#     async def handle(self, event: KeycloakUserEvent, db_session):
#         if event.op == "u":
#             log.info(f"🔄 Updating shadow user: {event.sub}")
#             # SQL: UPDATE users SET username = ..., email = ... WHERE sub = ...
#             return True
#         return False


class DeleteUserHandler(UserSyncHandler):
    async def handle(self, event: KeycloakUserEvent, db_session: AsyncSession):
        if event.op == "d":
            log.info(f"🗑️ Deleting shadow user: {event.sub}")
            # SQL: DELETE FROM users WHERE sub = ...
            await db_session.execute(
                delete(models.UserModel).where(models.UserModel.kc_sub == event.sub)
            )
            await db_session.commit()
            return True
        return False


class UserEventOrchestrator:
    def __init__(self):
        self.handlers: list[UserSyncHandler] = [
            UpsertUserHandler(),
            DeleteUserHandler(),
        ]

    async def process(self, event: KeycloakUserEvent, db_session):
        for handler in self.handlers:
            if await handler.handle(event, db_session):
                return  # Event handled successfully
        log.info(f"⚠️ No handler found for operation: {event.op}")
