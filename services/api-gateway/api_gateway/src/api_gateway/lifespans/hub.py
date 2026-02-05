from contextlib import AsyncExitStack, asynccontextmanager
from api_gateway.lifespans.kafka import (
    kafka_producer_lifespan,
    user_synchronization_consumer_lifespan,
)
from api_gateway.lifespans.s3 import s3_lifespan_processed, s3_lifespan_raw
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        # Register both lifespans
        await stack.enter_async_context(s3_lifespan_raw(app))
        await stack.enter_async_context(s3_lifespan_processed(app))
        await stack.enter_async_context(kafka_producer_lifespan(app))
        await stack.enter_async_context(user_synchronization_consumer_lifespan(app))

        # The app runs while inside this yield
        yield
