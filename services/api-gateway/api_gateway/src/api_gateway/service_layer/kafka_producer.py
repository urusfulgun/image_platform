from collections.abc import Callable
import logging
from aiokafka import AIOKafkaProducer
from api_gateway.config import GatewaySettings, settings
from api_gateway.utils.kafka_producer import create_producer

logger = logging.getLogger("granian.error")


class KafkaProducerWrapper:
    _producer: AIOKafkaProducer
    _factory: Callable[[GatewaySettings], AIOKafkaProducer]

    def __init__(
        self,
        producer: AIOKafkaProducer | None = None,
        factory: Callable[[GatewaySettings], AIOKafkaProducer] = create_producer,
    ):
        self._producer = producer
        self._factory = factory

    async def start(self):
        """Initialize the producer with DPoP/Auth aware settings if needed."""
        if self._producer is None:
            self._producer = self._factory(settings)
            await self._producer.start()
            logger.info("KAFKA: Global Producer started successfully.")

    async def stop(self):
        """Graceful shutdown to flush pending messages."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("KAFKA: Global Producer stopped.")

    async def send_and_wait(self, topic: str, value: bytes):
        """Wraps the internal send_and_wait for external use."""
        if self._producer is None:
            raise RuntimeError("Kafka Producer is not started. Check lifespan.")
        return await self._producer.send_and_wait(topic, value)


# The singleton instance
global_producer = KafkaProducerWrapper()
