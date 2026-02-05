import ssl

from aiokafka import AIOKafkaConsumer
from api_gateway.config import settings, GatewaySettings


def create_consumer(
    settings: GatewaySettings,
    topic: str,
) -> AIOKafkaConsumer:
    context = ssl.create_default_context(
        purpose=ssl.Purpose.SERVER_AUTH,
        cafile=settings.KAFKA_CA_CERTIFICATE_PATH,
    )
    context.load_cert_chain(
        certfile=settings.KAFKA_CERTIFICATE,
        keyfile=settings.KAFKA_KEYFILE,
    )
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED

    # Added request_timeout_ms to give metadata time to update
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        security_protocol="SSL",
        ssl_context=context,
        request_timeout_ms=10000,
        session_timeout_ms=30000,  # Increase to 30s
        heartbeat_interval_ms=10000,  # Heartbeat every 10s
        retry_backoff_ms=100,
        group_id="gateway-sync-group",
        enable_auto_commit=False,
    )
    return consumer


def create_consumer_user_registration(settings: GatewaySettings) -> AIOKafkaConsumer:
    return create_consumer(settings, settings.KAFKA_TOPIC_USER_REGISTRATION)
