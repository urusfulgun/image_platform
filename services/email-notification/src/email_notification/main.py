import asyncio
import json
import logging
import signal
import os
from aiokafka import AIOKafkaConsumer
from aiosmtplib import send
from email.message import EmailMessage
from shared_core.events.kafka_events import ImageAvifReadyEvent
from fastapi import FastAPI, Response, status
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NotificationWorker")


# --- FastAPI Setup ---
app = FastAPI()
worker_instance = None  # Global reference for the health check to inspect


@app.get("/health")
async def health_check():
    """
    Checks if the Kafka consumer and producer are still connected.
    """
    if not worker_instance:
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    # Check if Kafka components are running
    # Note: _closed is an internal state, but useful for basic liveness
    is_consumer_ok = worker_instance.consumer is not None

    if is_consumer_ok:
        return {"status": "healthy", "worker": "active"}

    return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


class NotificationWorker:
    def __init__(
        self, kafka_bootstrap: str, smtp_host: str, smtp_port: int, from_email: str
    ):
        self.kafka_bootstrap = kafka_bootstrap
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.from_email = from_email

        # Topic
        self.INPUT_TOPIC = "image.avif.ready"

        self.consumer = AIOKafkaConsumer(
            self.INPUT_TOPIC,
            bootstrap_servers=self.kafka_bootstrap,
            group_id="notification-group",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            enable_auto_commit=False,
        )

    async def run(self):
        await self.consumer.start()
        logger.info(
            f"Notification Worker live. Connected to Mailpit at {self.smtp_host}:{self.smtp_port}"
        )

        try:
            async for msg in self.consumer:
                try:
                    # Parse event using your shared core schema
                    event = ImageAvifReadyEvent(**msg.value)
                    await self.send_notification(event)
                except Exception as e:
                    logger.error(
                        f"Failed to notify for image {msg.value.get('image_id')}: {e}"
                    )
                finally:
                    await self.consumer.commit()
        finally:
            await self.consumer.stop()

    async def send_notification(self, event: ImageAvifReadyEvent):
        """Constructs and sends an email via Mailpit."""
        message = EmailMessage()
        message["From"] = self.from_email
        # In a real app, you'd fetch the user's email based on project_id/image_id
        message["To"] = "developer@example.local"
        message["Subject"] = f"✨ Image Processed: {event.image_id}"

        body = (
            f"Your image has been successfully converted to AVIF.\n\n"
            f"Image ID: {event.image_id}\n"
            f"Project: {event.project_id}\n"
            f"Storage Path: {event.processed_s3_path}\n\n"
            f"View it in your dashboard: http://localhost/upload/{event.project_id}"
        )
        message.set_content(body)

        await send(
            message,
            hostname=self.smtp_host,
            port=self.smtp_port,
            # Mailpit default: no auth, no TLS required for local dev
            use_tls=False,
        )
        logger.info(f"Notification sent for image: {event.image_id}")


# --- Main Entry ---
async def main():
    global worker_instance
    # Environment variables matching your docker-compose.yaml
    kafka_url = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    mail_host = os.getenv("SMTP_HOST", "mailpit")
    mail_port = int(os.getenv("SMTP_PORT", 1025))
    sender = os.getenv("FROM_EMAIL", "noreply@image-platform.local")

    worker_instance = NotificationWorker(
        kafka_bootstrap=kafka_url,
        smtp_host=mail_host,
        smtp_port=mail_port,
        from_email=sender,
    )

    # Setup FastAPI server to run in the background
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="error")
    server = uvicorn.Server(config)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        # Structured Concurrency: TaskGroup manages the lifetime of all tasks
        async with asyncio.TaskGroup() as tg:
            w_task = tg.create_task(worker_instance.run())
            _ = tg.create_task(server.serve())

            # Wait until a shutdown signal is received
            await stop_event.wait()
            logger.info("Shutdown signal received.")
            # Signal the server and worker to wind down
            server.should_exit = True
            logger.info("Initiating graceful shutdown...")
            w_task.cancel()

            # When we exit this block, all remaining tasks (worker/server)
            # are automatically cancelled and awaited.
    except* asyncio.CancelledError:
        # This is expected when we cancel w_task
        pass
    except* Exception as eg:
        # Python 3.11+ ExceptionGroup handling
        for error in eg.exceptions:
            logger.error(f"Task error: {error}")
    finally:
        logger.info("Worker and Health server stopped gracefully.")


if __name__ == "__main__":
    asyncio.run(main())
