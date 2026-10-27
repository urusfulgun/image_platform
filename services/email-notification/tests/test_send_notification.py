"""Characterization tests for NotificationWorker.send_notification."""

import pytest
import pytest_asyncio
from shared_core.events.kafka_events import ImageAvifReadyEvent


@pytest.fixture
def event(avif_ready_payload):
    return ImageAvifReadyEvent(**avif_ready_payload())


@pytest_asyncio.fixture
async def sent(worker, smtp_send, event):
    """Send one notification and return (message, call kwargs)."""
    await worker.send_notification(event)
    smtp_send.assert_awaited_once()
    return smtp_send.await_args.args[0], smtp_send.await_args.kwargs


@pytest.mark.asyncio
async def test_from_is_configured_sender(sent):
    message, _ = sent
    assert message["From"] == "sender@test.local"


@pytest.mark.asyncio
async def test_subject_names_image(sent, event):
    message, _ = sent
    assert message["Subject"] == f"✨ Image Processed: {event.image_id}"


@pytest.mark.asyncio
async def test_body_contains_ids_path_and_dashboard_link(sent, event):
    message, _ = sent
    body = message.get_content()
    assert str(event.image_id) in body
    assert str(event.project_id) in body
    assert event.processed_s3_path in body
    assert f"http://localhost/upload/{event.project_id}" in body


@pytest.mark.asyncio
async def test_smtp_call_uses_configured_host_and_port_without_tls(sent):
    _, kwargs = sent
    assert kwargs == {"hostname": "smtp-test", "port": 2525, "use_tls": False}


@pytest.mark.known_bug
@pytest.mark.asyncio
async def test_recipient_is_hardcoded(sent):
    # CHARACTERIZATION: changes in N4 (email the image owner, looked up by user ID)
    message, _ = sent
    assert message["To"] == "developer@example.local"
