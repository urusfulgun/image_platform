from asset_service.lifespans.kafka import lifespan as kafka_user_events_consumer
from asset_service.lifespans.lifespan_manager import LifespanManager

lifespan_manager = LifespanManager()

lifespan_manager.add_handler("kafka_user", kafka_user_events_consumer)
