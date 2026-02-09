import asyncio
import ssl
from aiokafka import AIOKafkaProducer
from api_gateway.config import settings


async def test_kafka_ssl():
    # Use the service name defined in docker-compose
    bootstrap_servers = settings.KAFKA_BOOTSTRAP_SERVERS
    topic = "ssl-test-topic"

    ca_file = settings.KAFKA_CA_CERTIFICATE_PATH

    print(f"--- Starting SSL Connection Test to {bootstrap_servers} ---")

    context = ssl.create_default_context(
        purpose=ssl.Purpose.SERVER_AUTH,
        cafile=ca_file,
    )
    context.load_cert_chain(
        certfile=settings.KAFKA_CERTIFICATE, keyfile=settings.KAFKA_KEYFILE
    )
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED

    # Added request_timeout_ms to give metadata time to update
    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        security_protocol="SSL",
        ssl_context=context,
        request_timeout_ms=10000,
        retry_backoff_ms=500,
    )

    try:
        print("Connecting to Broker and fetching metadata...")
        await producer.start()

        # This will fail if the topic doesn't exist and auto-create is off
        print("✅ Handshake successful! Attempting to send message...")
        await producer.send_and_wait(topic, b"Hello SSL Kafka!")
        print(f"✅ Message sent successfully to topic '{topic}'")

    except Exception as e:
        # If you see UnknownTopicOrPartitionError here, it PROVES SSL is working.
        print(f"❌ Kafka Error: {e}")
        if "UnknownTopicOrPartitionError" in str(e):
            print(
                "💡 TIP: The SSL connection worked! You just need to create the topic."
            )
    finally:
        await producer.stop()
        print("--- Test Finished ---")


if __name__ == "__main__":
    asyncio.run(test_kafka_ssl())
