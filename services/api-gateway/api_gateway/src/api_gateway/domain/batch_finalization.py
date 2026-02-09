import uuid
from api_gateway.domain.models import ImageMetadata
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload


# Internal imports
from api_gateway.domain.models import Batch, ImageMetadata
from api_gateway.service_layer.kafka_producer import global_producer  # Your AIOKafkaProducer instance
from shared_core.events.batch_process import BatchProcessEvent, ImageTask  # From your shared lib


async def trigger_batch_processing_event(batch_id: uuid.UUID, session: AsyncSession):
    """
    Constructs the final processing manifest and ships it to Kafka.
    """
    # 1. Fetch the complete Aggregate (Batch -> Project -> Images)
    # We use selectinload to ensure all relationships are available without extra hits
    stmt = (
        select(Batch)
        .where(Batch.batch_id == batch_id)
        .options(
            selectinload(Batch.project),
            selectinload(Batch.images)
        )
    )
    
    result = await session.exec(stmt)
    batch = result.scalar_one_or_none()

    if not batch:
        print(f"Critical: Attempted to trigger processing for missing batch {batch_id}")
        return

    # 2. Build the Image Task list
    # Only include images that are actually in UPLOADED status
    tasks = [
        ImageTask(
            image_id=img.image_id,
            storage_key=img.storage_key,
            display_name=img.display_name
        )
        for img in batch.images if img.status == "UPLOADED"
    ]

    if not tasks:
        print(f"Batch {batch_id} has no valid uploaded images. Skipping.")
        return

    # 3. Assemble the Event
    # We pull target_resolutions from the Project Aggregate Root
    event = BatchProcessEvent(
        project_id=batch.project_id,
        batch_id=batch.batch_id,
        owner_id=batch.project.owner_id,
        target_resolutions=batch.project.target_resolutions,
        images=tasks
    )

    # 4. Produce to Kafka
    # Using 'batch.created' as the topic for the image-processor to consume
    try:
        payload = event.model_dump_json().encode("utf-8")
        await global_producer.send_and_wait("batch.created", payload)
        
        # 5. Update Batch state to PROCESSING
        batch.status = "PROCESSING"
        session.add(batch)
        # No need to commit here if called within the process_s3_record transaction
        
        print(f"Successfully triggered processing for Batch: {batch_id}")
        
    except Exception as e:
        # If Kafka fails, the transaction in process_s3_record will roll back,
        # ensuring the batch doesn't get 'stuck' in PROCESSING without an event sent.
        print(f"Failed to produce Kafka event for batch {batch_id}: {e}")
        raise e


async def finalize_batch_if_ready(batch_id: uuid.UUID, session: AsyncSession):
    # Count total images vs uploaded images in this batch
    stmt = select(
        func.count(ImageMetadata.image_id).label("total"),
        func.count(ImageMetadata.image_id).filter(ImageMetadata.status == "UPLOADED").label("uploaded")
    ).where(ImageMetadata.batch_id == batch_id)
    
    result = await session.exec(stmt)
    counts = result.one()

    if counts.total == counts.uploaded:
        # All images are in! Trigger the Image Processor Kafka event.
        await trigger_batch_processing_event(batch_id, session)

