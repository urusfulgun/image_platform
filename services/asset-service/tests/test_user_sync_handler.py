"""Tests for shadow user sync from Keycloak CDC events."""

import uuid
import pytest
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.sql import Delete

from shared_core.schemas.debezium.events import KeycloakUserEvent
from asset_service.kafka.user_sync_handler import UserEventOrchestrator


def make_event(
    op: str, email: str | None = "alice@example.com", **extra
) -> KeycloakUserEvent:
    return KeycloakUserEvent.model_validate(
        {"id": str(uuid.uuid4()), "email": email, "__op": op, **extra}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("op", ["c", "u", "r"])
async def test_upsert_ops_insert_user(mock_db, op):
    """Create, update and snapshot events should upsert the shadow user."""
    event = make_event(op)

    await UserEventOrchestrator().process(event, event.sub, mock_db)

    mock_db.execute.assert_awaited_once()
    stmt = mock_db.execute.await_args.args[0]
    assert isinstance(stmt, Insert)
    assert stmt.table.name == "users"
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_without_email_is_skipped(mock_db):
    """Partial update events must not overwrite the stored email with null."""
    event = make_event("u", email=None)

    await UserEventOrchestrator().process(event, event.sub, mock_db)

    mock_db.execute.assert_not_awaited()
    mock_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_op_removes_user(mock_db):
    event = make_event("d", email=None)

    await UserEventOrchestrator().process(event, event.sub, mock_db)

    mock_db.execute.assert_awaited_once()
    stmt = mock_db.execute.await_args.args[0]
    assert isinstance(stmt, Delete)
    assert stmt.table.name == "users"
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_deleted_flag_removes_user_even_on_update(mock_db):
    """A record flagged __deleted must be deleted, not upserted."""
    event = make_event("u", __deleted="true")

    await UserEventOrchestrator().process(event, event.sub, mock_db)

    mock_db.execute.assert_awaited_once()
    assert isinstance(mock_db.execute.await_args.args[0], Delete)
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_tombstone_removes_user(mock_db):
    """A Kafka tombstone (null value) deletes by the id from the message key."""
    await UserEventOrchestrator().process(None, str(uuid.uuid4()), mock_db)

    mock_db.execute.assert_awaited_once()
    assert isinstance(mock_db.execute.await_args.args[0], Delete)
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_op_is_ignored(mock_db):
    event = make_event("t")

    await UserEventOrchestrator().process(event, event.sub, mock_db)

    mock_db.execute.assert_not_awaited()
    mock_db.commit.assert_not_awaited()
