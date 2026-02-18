from unittest.mock import AsyncMock, MagicMock
from bff.dependencies.session import get_bff_client
from fastapi import Depends, FastAPI
import httpx
import pytest
from bff.service_layer.bff_manager import RedisBFFManager



@pytest.mark.asyncio
async def test_get_session_dependency(mock_signer):
    # Setup App
    app = FastAPI()
    # Mock Redis and BFF Manager
    app.state.redis_pool = AsyncMock()  # Mock redis.Redis
    app.state.bff = MagicMock(spec=RedisBFFManager)

    # Mock the return of a configured httpx client
    mock_client = httpx.AsyncClient()
    app.state.bff.get_client = AsyncMock(return_value=mock_client)

    @app.get("/test-session")
    async def endpoint(client: httpx.AsyncClient = Depends(get_bff_client)):
        return {"id": id(client)}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # 1. Call without cookie -> 401
        res_fail = await ac.get("/test-session")
        assert res_fail.status_code == 401

        # 2. Call with cookie
        ac.cookies.set("__Host-session", "valid-uuid")
        res_success = await ac.get("/test-session")
        assert res_success.status_code == 200
