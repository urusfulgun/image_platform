from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI


class LifespanManager:
    def __init__(self):
        self._handlers: dict[str, Callable[[FastAPI], Awaitable[None]]] = {}

    def add_handler(self, name: str, handler: Callable[[FastAPI], Awaitable[None]]):
        self._handlers[name] = handler
        return handler

    @asynccontextmanager
    async def __call__(self, app: FastAPI):
        async with AsyncExitStack() as stack:
            for handler in self._handlers.values():
                await stack.enter_async_context(handler(app))
            yield
