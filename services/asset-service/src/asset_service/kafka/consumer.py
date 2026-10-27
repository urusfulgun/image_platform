"""Kafka consumer for AssetService.

Consumes user.registered events from Debezium/KeyCloak CDC
and creates shadow users in the AssetService database.
"""

import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer
from pydantic import ValidationError

from asset_service.db.session import AsyncSessionLocal
from asset_service.kafka.user_sync_handler import UserEventOrchestrator
from asset_service.settings import settings
from shared_core.schemas.debezium.events import KeycloakUserEvent

log = logging.getLogger(__name__)


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
        auto_offset_reset="earliest",
    )

    await consumer.start()
    try:
        async for msg in consumer:
            # Create a unique ID for this message's lifecycle to trace logs
            correlation_id = f"{msg.topic}-{msg.partition}-{msg.offset}"
            try:
                raw_data = msg.value.decode("utf-8")
                data = json.loads(raw_data)
                event = KeycloakUserEvent.model_validate(data)

                if event.email is None and event.op != "d":
                    log.info(
                        f"✅ Pass event {correlation_id} for user {event.sub}, because email is None in event."
                    )
                    continue

                async with AsyncSessionLocal() as session:
                    await orchestrator.process(event, event.sub, session)
                    log.info(
                        f"✅ Processed event {correlation_id} for user {event.sub}"
                    )

            except json.JSONDecodeError:
                log.error(
                    f"❌ Malformed JSON at {correlation_id}. Raw data: {raw_data}"
                )
            except ValidationError as ve:
                log.error(
                    f"❌ Schema validation failed at {correlation_id}: {ve.json()}"
                )
            except Exception:
                # exc_info=True includes the stack trace automatically
                log.error(
                    f"❌ Unexpected error processing event {correlation_id}",
                    exc_info=True,
                    extra={"raw_payload": raw_data},  # If using structured logging
                )
    except asyncio.CancelledError:
        log.info("Shutting down Kafka consumer gracefully...")
    finally:
        await consumer.stop()
