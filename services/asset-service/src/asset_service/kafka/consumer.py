"""Kafka consumer for AssetService.

Consumes user.registered events from Debezium/KeyCloak CDC
and creates shadow users in the AssetService database.
"""
import asyncio
import json
import logging
import uuid

from aiokafka import AIOKafkaConsumer
from asset_service.kafka.user_sync_handler import UserEventOrchestrator
from shared_core.schemas.debezium.events import KeycloakUserEvent
from sqlalchemy.ext.asyncio import AsyncSession
from asset_service.db.session import AsyncSessionLocal
from asset_service.db.models import UserModel
from asset_service.settings import settings
from shared_core.events.kafka_events import UserRegisteredEvent


log = logging.getLogger(__name__)


async def create_shadow_user(event: UserRegisteredEvent) -> None:
    """Upsert a shadow user from a UserRegisteredEvent."""
    async with AsyncSessionLocal() as session:
        existing = await session.get(UserModel, event.kc_sub)
        if existing:
            log.info("Shadow user already exists for kc_sub=%s", event.kc_sub)
            return
        user = UserModel(
            id=uuid.uuid4(),
            kc_sub=event.kc_sub,
            email=event.email,
        )
        session.add(user)
        await session.commit()
        log.info("Created shadow user for kc_sub=%s email=%s", event.kc_sub, event.email)


async def start_consumer() -> None:
    """Run the Kafka consumer loop for user.registered events."""
    consumer = AIOKafkaConsumer(
        settings.user_registered_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        value_deserializer=lambda m: json.loads(m.decode()),
        auto_offset_reset="earliest",
    )
    await consumer.start()
    log.info("Started Kafka consumer on topic=%s", settings.user_registered_topic)
    try:
        async for msg in consumer:
            try:
                event = UserRegisteredEvent(**msg.value)
                await create_shadow_user(event)
            except Exception as exc:
                log.error("Failed to process user.registered: %s", exc, exc_info=True)
    finally:
        await consumer.stop()


# --- Kafka Logic ---
async def consume_user_events():
    """
    Background worker to consume Keycloak events from Kafka.
    """
    orchestrator = UserEventOrchestrator()
    consumer = AIOKafkaConsumer(
        settings.user_event_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        auto_offset_reset="earliest"
    )
    
    await consumer.start()
    try:
        async for msg in consumer:
            try:
                data = json.loads(msg.value.decode("utf-8"))
                event = KeycloakUserEvent.model_validate(data)
                
                async with AsyncSessionLocal() as session:
                    await orchestrator.process(event, session)
            
            except asyncio.CancelledError as e:
                log.error(f"❌CancelledError processing user event: {e}")
                # This is expected when the task is cancelled during shutdown
                pass    
            except Exception as e:
                log.error(f"❌ Error processing user event: {e}")
    except asyncio.CancelledError:
        pass
    finally:
        await consumer.stop()
