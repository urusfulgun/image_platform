"""Tests for Kafka consumer shadow user creation."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from shared_core.events.kafka_events import UserRegisteredEvent
from asset_service.kafka.consumer import create_shadow_user


@pytest.mark.asyncio
async def test_create_shadow_user_new():
    """New shadow user should be added and committed."""
    event = UserRegisteredEvent(
        kc_sub=uuid.uuid4(),
        email="alice@example.com",
    )

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)  # user doesn't exist yet
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("asset_service.kafka.consumer.AsyncSessionLocal", return_value=mock_session):
        await create_shadow_user(event)

    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_shadow_user_already_exists():
    """Existing shadow user should not be added again."""
    event = UserRegisteredEvent(
        kc_sub=uuid.uuid4(),
        email="bob@example.com",
    )

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=MagicMock())  # already exists
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("asset_service.kafka.consumer.AsyncSessionLocal", return_value=mock_session):
        await create_shadow_user(event)

    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_awaited()
