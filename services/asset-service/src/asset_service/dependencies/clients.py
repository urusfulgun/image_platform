from asset_service.kafka.producer import AssetKafkaProducer
from fastapi import Request


def get_kafka_producer(request: Request) -> AssetKafkaProducer:
    # Accessing the producer from app.state (set during startup)
    return request.app.state.kafka_producer
