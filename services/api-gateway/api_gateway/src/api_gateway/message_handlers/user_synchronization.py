import asyncio
import uuid
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
import json

from sqlalchemy import select

from api_gateway.domain.models import ShadowUser
from api_gateway.config import settings

# from image_converter_api_gateway.logger import logger
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
import logging

from api_gateway.utils.kafka_consumer import (
    create_consumer_user_registration,
)
from api_gateway.utils.kafka_producer import create_producer


# Configure logging to track failures
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway-sync")


async def consume_user_events(db_factory: async_sessionmaker):
    consumer: AIOKafkaConsumer = create_consumer_user_registration(settings)

    # We need a producer to send failed messages to the DLQ
    # dlq_producer = AIOKafkaProducer(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
    dlq_producer: AIOKafkaProducer = create_producer(settings)

    await consumer.start()
    await dlq_producer.start()

    try:
        async for msg in consumer:
            try:
                # 1. Parsing Check (Poison Pill Protection)
                raw_data = msg.value.decode("utf-8")
                event = json.loads(raw_data)
                logger.info(f"sync_event {event}")

                # 2. Process the message
                async with db_factory() as db:
                    await sync_user_to_gateway(db, event["data"]["user_uuid"])

                # 3. Commit offset only after successful processing
                await consumer.commit()

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.error(f"Malformed message at offset {msg.offset}: {e}")
                await move_to_dlq(dlq_producer, msg, str(e))
                await consumer.commit()  # Skip this message and move on

            except Exception as e:
                logger.error(f"Database/Unexpected error: {e}")
                # We DON'T commit here if the DB is down; we want to retry
                # when the DB is back. Use a small sleep to avoid tight loops.
                await asyncio.sleep(5)

    finally:
        await consumer.stop()
        await dlq_producer.stop()


async def sync_user_to_gateway(db: AsyncSession, user_uuid: uuid.UUID):
    # Idempotency check: ensures we don't crash on duplicate messages
    stmt = select(ShadowUser).where(ShadowUser.user_id == user_uuid)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        new_user = ShadowUser(user_id=user_uuid)
        db.add(new_user)
        await db.commit()


async def move_to_dlq(producer: AIOKafkaProducer, original_msg, reason):
    """Sends the failed message payload to the Dead Letter Queue."""
    dlq_payload = {
        "original_payload": original_msg.value.decode("utf-8"),
        "reason": reason,
        "offset": original_msg.offset,
        "partition": original_msg.partition,
    }
    await producer.send_and_wait(
        settings.KAFKA_TOPIC_BATCH_PROCESS_DLQ, json.dumps(dlq_payload).encode("utf-8")
    )
    logger.warning(f"Message moved to {settings.KAFKA_TOPIC_BATCH_PROCESS_DLQ}")
