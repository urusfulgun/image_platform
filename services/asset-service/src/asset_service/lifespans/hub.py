from asset_service.lifespans.kafka import (
    kafka_events_consumer_lifespan as kafka_user_events_consumer,
    kafka_events_producer_lifespan,
)
from asset_service.lifespans.lifespan_manager import LifespanManager
from asset_service.lifespans.s3 import s3_client_lifespan
from asset_service.lifespans.image_status import lifespan as image_update_lifespan


lifespan_manager = LifespanManager()

lifespan_manager.add_handler("kafka_user", kafka_user_events_consumer)
lifespan_manager.add_handler("kafka_producer", kafka_events_producer_lifespan)
lifespan_manager.add_handler("s3_client", s3_client_lifespan)
lifespan_manager.add_handler("kafka_image_status_update", image_update_lifespan)
