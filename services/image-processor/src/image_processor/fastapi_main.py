import asyncio
import io
import uuid
import aioboto3
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from PIL import Image
import pillow_avif  # Ensure this is installed: pip install pillow-avif-plugin
from aiobotocore.config import AioConfig
from fastapi import FastAPI, BackgroundTasks
from shared_core.utils.s3_object_key import get_s3_object_key
# --- Models ---


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ImageRawUploadedEvent(BaseModel):
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    image_id: uuid.UUID
    project_id: uuid.UUID
    raw_s3_path: str
    raw_format: str
    file_size_bytes: Optional[int] = None
    occurred_at: datetime = Field(default_factory=get_utc_now)


class ImageAvifReadyEvent(BaseModel):
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    image_id: uuid.UUID
    project_id: uuid.UUID
    processed_s3_path: str
    occurred_at: datetime = Field(default_factory=get_utc_now)


# --- Processor Logic ---


class ImageProcessor:
    def __init__(self, raw_bucket_name: str, processed_bucket_name: str, endpoint_url: str):
        self.raw_bucket_name = raw_bucket_name
        self.processed_bucket_name = processed_bucket_name
        self.session = aioboto3.Session()
        # self.s3_config = dict(
        #     endpoint_url=endpoint_url,
        #     aws_access_key_id="sNR4h81kmySrWCDFTjbt",
        #     aws_secret_access_key="OhXaPbwdscmL1q8eWvun52yBUkElxDAfRMJHFY3Q",
        #     config=AioConfig(signature_version="s3v4"),
        #     region_name="us-east-1",
        # )
        self.s3_config = dict(
            endpoint_url=endpoint_url,
            aws_access_key_id="OAhzGogEY7X61ZwjnSmH",
            aws_secret_access_key="5XItB3Pon6syp7e1cxNvJOTfWlzigEZQkK2FM8Vh",
            config=AioConfig(signature_version="s3v4"),
            region_name="us-east-1",
        )

    async def process_event(self, event: ImageRawUploadedEvent) -> ImageAvifReadyEvent:
        async with self.session.client("s3", **self.s3_config) as s3:
            # 1. Download raw image
            response = await s3.get_object(
                Bucket=self.raw_bucket_name,
                Key=event.raw_s3_path,
            )
            raw_data = await response["Body"].read()

            # 2. Convert to AVIF (CPU Intensive - run in thread pool)
            loop = asyncio.get_running_loop()
            avif_data, avif_path = await loop.run_in_executor(
                None, self._convert_to_avif, raw_data, event.raw_s3_path
            )

            event.project_id
            event

            # 3. Upload AVIF
            await s3.put_object(
                Bucket=self.processed_bucket_name,
                Key=avif_path,
                Body=avif_data,
                ContentType="application/octet-stream",
            )

            return ImageAvifReadyEvent(
                image_id=event.image_id,
                project_id=event.project_id,
                processed_s3_path=avif_path,
            )

    def _convert_to_avif(
        self, raw_data: bytes, original_path: str
    ) -> tuple[bytes, str]:
        with Image.open(io.BytesIO(raw_data)) as img:
            out_io = io.BytesIO()
            # Optimization: Ensure image is in RGB if converting from RGBA/JPEG
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            img.save(out_io, format="AVIF", quality=60, speed=6)

            # Generate new path (e.g., swapping extension)
            new_path = original_path.rsplit(".", 1)[0] + ".avif"
            return out_io.getvalue(), new_path


# --- Integration Example (FastAPI) ---

app = FastAPI()
processor = ImageProcessor(
    raw_bucket_name="raw-images",
    processed_bucket_name="processed-images",
    endpoint_url="http://rustfs:9000",
)


@app.post("/process-raw")
async def handle_raw_upload(
    event: ImageRawUploadedEvent, background_tasks: BackgroundTasks
):
    # We process it as a background task to return 202 Accepted immediately
    background_tasks.add_task(run_pipeline, event)
    return {"status": "processing"}


async def run_pipeline(event: ImageRawUploadedEvent):
    result_event = await processor.process_event(event)
    # Here you would publish result_event to your message broker (Kafka/RabbitMQ)
    print(f"Published: {result_event.model_dump_json()}")
