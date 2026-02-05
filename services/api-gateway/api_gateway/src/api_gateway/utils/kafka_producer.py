import ssl

from aiokafka import AIOKafkaProducer
from api_gateway.config import GatewaySettings


def create_producer(
    settings: GatewaySettings,
) -> AIOKafkaProducer:
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
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        security_protocol="SSL",
        ssl_context=context,
        request_timeout_ms=10000,
        retry_backoff_ms=500,
        # max_batch_size=16384,
    )
    return producer

