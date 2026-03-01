import io
import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image
from shared_core.events.kafka_events import ImageRawUploadedEvent
from image_processor.main import (
    KafkaImageWorker,
)  # Change this to your actual module path


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

    # Mock the internal CPU conversion to avoid actual PIL processing
    with (
        patch.object(
            worker, "_to_avif", return_value=(b"avif-data", "path/image.avif")
        ),
        patch.object(worker.session, "client", return_value=mock_s3),
    ):
        mock_s3.__aenter__.return_value = mock_s3

        await worker.handle_processing(raw_event)

        # Assertions
        mock_s3.get_object.assert_called_once_with(
            Bucket="raw-images", Key=raw_event.raw_s3_path
        )
        mock_s3.put_object.assert_called_once_with(
            Bucket="processed-images",
            Key="path/image.avif",
            Body=b"avif-data",
            ContentType="image/avif",
        )
        worker.producer.send_and_wait.assert_called_once()


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


def test_to_avif_conversion_logic_jpeg(worker: KafkaImageWorker):
    """Verifies image transformation and path generation."""
    # Create a small red square
    img = Image.new("RGB", (100, 100), color="red")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")

    with patch.object(worker, "_get_s3_key", return_value="processed/test.avif"):
        avif_bytes, new_path = worker._to_avif(
            img_byte_arr.getvalue(), "raw/test.jpg", "proj-1"
        )

    assert new_path == "processed/test.avif"
    with Image.open(io.BytesIO(avif_bytes)) as result_img:
        assert result_img.format == "AVIF"


def test_to_avif_conversion_logic_png(worker: KafkaImageWorker):
    # 1. Setup: Create a fake RGBA (transparent) PNG image in memory
    # We use RGBA to test if the worker correctly converts it to RGB
    width, height = 100, 100
    original_img = Image.new("RGBA", (width, height), color=(255, 0, 0, 128))
    img_byte_arr = io.BytesIO()
    original_img.save(img_byte_arr, format="PNG")
    raw_data = img_byte_arr.getvalue()

    project_id = "proj-123"
    original_path = "folder/subfolder/photo.png"
    processed_image_path = "proj-123/folder/subfolder/photo.avif"

    # Mock the s3 key helper to return a predictable string
    # worker._get_s3_key = MagicMock(return_value="proj-123/folder/subfolder/photo.avif")

    # 2. Execute
    with patch.object(
        worker, "_get_s3_key", return_value=processed_image_path
    ):
        avif_bytes, new_path = worker._to_avif(
            raw_data,
            original_path,
            project_id,
        )

    # 3. Assertions
    assert new_path == processed_image_path
    assert len(avif_bytes) > 0

    # Verify the output is a valid AVIF image
    with Image.open(io.BytesIO(avif_bytes)) as result_img:
        assert result_img.format == "AVIF"
        # Verify the mode was converted to RGB (since AVIF doesn't always play nice with RGBA in standard saves)
        assert result_img.mode == "RGB"
        assert result_img.size == (width, height)


def test_to_avif_handles_corrupted_data(worker: KafkaImageWorker):
    # Setup: Provide random garbage bytes instead of a real image
    bad_data = b"not_an_image_file_content"

    # Execute & Assert: PIL should raise an UnidentifiedImageError
    with patch.object(worker, "_get_s3_key", return_value="processed/test.avif"):
        # Execute & Assert: PIL should raise an UnidentifiedImageError
        with pytest.raises(Exception):
            _, _ = worker._to_avif(
                bad_data,
                "test.jpg",
                "proj-1",  # Specifically PIL.UnidentifiedImageError
            )
