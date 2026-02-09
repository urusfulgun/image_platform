from api_gateway.lifespans.kafka import (
    kafka_producer_lifespan,
    user_synchronization_consumer_lifespan,
)
from api_gateway.lifespans.s3 import s3_lifespan_processed, s3_lifespan_raw
from api_gateway.lifespans.redis import redis_lifespan
from api_gateway.lifespans.lifespan_manager import LifespanManager


lifespan_manager = LifespanManager()

lifespan_manager.add_handler("raw", s3_lifespan_raw)
lifespan_manager.add_handler("processed", s3_lifespan_processed)
lifespan_manager.add_handler("kafka_producer", kafka_producer_lifespan)
lifespan_manager.add_handler("user_sync", user_synchronization_consumer_lifespan)
lifespan_manager.add_handler("redis", redis_lifespan)
