import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image, UnidentifiedImageError

from image_processor.main import (
    KafkaImageWorker,
)  # Change this to your actual module path
from shared_core.events.kafka_events import ImageRawUploadedEvent

# --- Fixtures ---


@pytest.fixture
def s3_config():
    return {
        "endpoint_url": "http://mock-rustfs:9000",
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
    }


@pytest.fixture
def worker(s3_config):
    """
    Instantiate worker with mocked Kafka clients to avoid
    loop initialization errors and network calls.
    """
    with (
        patch("image_processor.main.AIOKafkaConsumer", autospec=True),
        patch("image_processor.main.AIOKafkaProducer", autospec=True),
    ):
        worker_instance = KafkaImageWorker(
            kafka_bootstrap="localhost:9092",
            s3_config=s3_config,
            raw_bucket="raw-images",
            processed_bucket="processed-images",
        )
        # Manually set mocks for the instance to use in assertions
        worker_instance.producer = AsyncMock()
        worker_instance.consumer = AsyncMock()
        return worker_instance


@pytest.fixture
def raw_event():
    return ImageRawUploadedEvent(
        image_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        raw_s3_path="projects/1/images/test.jpg",
        raw_format="jpg",
    )


# --- Async Flow Tests ---


@pytest.mark.asyncio
async def test_handle_processing_success(worker, raw_event):
    """Tests the full pipeline from S3 download to Kafka produce."""
    mock_s3 = AsyncMock()

    # Mock S3 Download
    img_data = b"fake-image-bytes"
    mock_s3.get_object.return_value = {
        "Body": AsyncMock(read=AsyncMock(return_value=img_data))
    }

    main_img = {"bytes": b"avif-data", "path": "proj/1/optimized.avif"}
    preview_img = {"bytes": b"preview-data", "path": "proj/2/preview_tile.avif"}

    # Mock the internal CPU conversion to avoid actual PIL processing
    with (
        patch.object(
            worker, "_process_image_variants", return_value=(main_img, preview_img)
        ) as mock_process,
        patch.object(worker.session, "client", return_value=mock_s3),
    ):
        mock_s3.__aenter__.return_value = mock_s3

        await worker.handle_processing(raw_event)

        # Assertions
        mock_s3.get_object.assert_called_once_with(
            Bucket="raw-images", Key=raw_event.raw_s3_path
        )
        mock_process.assert_called_once_with(img_data, raw_event.project_id)
        assert mock_s3.put_object.call_count == 2
        mock_s3.put_object.assert_any_call(
            Bucket="processed-images",
            Key=main_img["path"],
            Body=main_img["bytes"],
            ContentType="image/avif",
        )
        mock_s3.put_object.assert_any_call(
            Bucket="processed-images",
            Key=preview_img["path"],
            Body=preview_img["bytes"],
            ContentType="image/avif",
        )

        worker.producer.send_and_wait.assert_called_once()
        topic, ready_payload = worker.producer.send_and_wait.call_args.args
        assert topic == "image.avif.ready"
        assert ready_payload["image_id"] == str(raw_event.image_id)
        assert ready_payload["processed_s3_path"] == main_img["path"]
        assert ready_payload["preview_s3_path"] == preview_img["path"]
        assert ready_payload["processed_format"] == "avif"


@pytest.mark.asyncio
async def test_send_to_dlq(worker, raw_event):
    """Verifies that the DLQ payload is correctly formatted and sent."""
    error_msg = "Corrupted image"
    payload = raw_event.model_dump(mode="json")

    await worker.send_to_dlq(payload, error_msg)

    worker.producer.send_and_wait.assert_called_once()
    topic, dlq_call_data = worker.producer.send_and_wait.call_args.args
    assert topic == "image.raw.failed"
    assert dlq_call_data["error"] == error_msg
    assert dlq_call_data["original_event"]["image_id"] == str(raw_event.image_id)


@pytest.mark.asyncio
async def test_run_loop_and_commit(worker: KafkaImageWorker):
    """Ensures that the consumer commits even if an error occurs."""
    mock_msg = MagicMock()
    mock_msg.value = {"invalid": "payload"}  # This will cause a Pydantic error

    # Mock consumer to yield one message then stop
    worker.consumer.__aiter__.return_value = [mock_msg]

    await worker.run()

    # Worker should have committed the offset regardless of the error
    # (to prevent infinite loops on bad data)
    worker.consumer.commit.assert_called_once()
    # Should have sent to DLQ because of the invalid payload
    worker.producer.send_and_wait.assert_called()


# --- Logic Tests (CPU Bound) ---


def _encode(img: Image.Image, fmt: str) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_process_image_variants_jpeg(worker: KafkaImageWorker):
    """Produces a full-size AVIF and a preview tile under the project prefix."""
    data = _encode(Image.new("RGB", (100, 100), color="red"), "JPEG")

    main_img, preview_img = worker._process_image_variants(data, "proj-1")

    assert main_img["path"].startswith("proj-1/")
    assert main_img["path"].endswith("/optimized.avif")
    assert preview_img["path"].startswith("proj-1/")
    assert preview_img["path"].endswith("/preview_tile.avif")
    for variant in (main_img, preview_img):
        with Image.open(io.BytesIO(variant["bytes"])) as result_img:
            assert result_img.format == "AVIF"


def test_process_image_variants_png_rgba(worker: KafkaImageWorker):
    """RGBA input is converted to RGB; main keeps its size, preview is scaled down."""
    width, height = 600, 400
    data = _encode(Image.new("RGBA", (width, height), color=(255, 0, 0, 128)), "PNG")

    main_img, preview_img = worker._process_image_variants(data, "proj-123")

    with Image.open(io.BytesIO(main_img["bytes"])) as result_img:
        assert result_img.format == "AVIF"
        assert result_img.mode == "RGB"
        assert result_img.size == (width, height)

    # thumbnail() keeps aspect ratio within PREVIEW_SIZE (300x300)
    with Image.open(io.BytesIO(preview_img["bytes"])) as result_img:
        assert result_img.format == "AVIF"
        assert result_img.size == (300, 200)


def test_process_image_variants_handles_corrupted_data(worker: KafkaImageWorker):
    with pytest.raises(UnidentifiedImageError):
        worker._process_image_variants(b"not_an_image_file_content", "proj-1")
