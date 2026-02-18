import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from joserfc import jwk
from unittest.mock import AsyncMock, MagicMock
from shared_core.abstract.dpop_signer import DPoPSigner
from shared_core.services.dpop_session import DPoPAuth
from shared_core.schemas.dpop import DPoPAccessTokenPayload
from shared_core.middlewares.dpop import DPoPMiddleware
from utils.helpers import get_ec_keys

@pytest.fixture(scope="session")
def test_keys() -> tuple[jwk.ECKey, jwk.ECKey]:
    """Generates an ephemeral EC key pair for signing test tokens."""
    return get_ec_keys()


@pytest.fixture
def mock_redis():
    """
    A stateful Redis mock that behaves like a real dictionary.
    Supports set, exists, and delete with correct return types.
    """
    storage = {}

    mock = AsyncMock()

    async def side_effect_set(key, value, ex=None, nx=False, **kwargs):
        # nx=True simulates 'Set if Not Exists'
        if nx and key in storage:
            return None  # Redis returns None/Null if NX fails
        storage[key] = value
        return True

    async def side_effect_exists(key):
        return key in storage

    async def side_effect_delete(key):
        if key in storage:
            del storage[key]
            return 1  # Returns integer count of deleted keys
        return 0

    mock.set.side_effect = side_effect_set
    mock.exists.side_effect = side_effect_exists
    mock.delete.side_effect = side_effect_delete

    # Allow resetting the storage between tests if needed
    mock.flushall = AsyncMock(side_effect=lambda: storage.clear())

    return mock


@pytest_asyncio.fixture
def app(mock_redis):
    """Creates a FastAPI app instance and injects mock redis into state."""
    fastapi_app = FastAPI()
    fastapi_app.state.redis = mock_redis

    @fastapi_app.get("/protected")
    async def protected_route(request: Request):
        return {"sub": request.state.user_sub}

    return fastapi_app


@pytest.fixture
def middleware_instance(app, test_keys: tuple[jwk.ECKey,  jwk.ECKey]):
    """Initializes the middleware with session-based test keys."""

    _, public_key = test_keys

    # We pass the public key for verification
    return DPoPMiddleware(
        app=app,
        authz_public_key=public_key.as_pem().decode(),
        allowed_issuer="https://auth.example.com",
        leeway_seconds=30,
    )


@pytest.fixture
def mock_signer():
    signer = MagicMock(spec=DPoPSigner)
    # Simulate a valid DPoP JWT return
    signer.sign_proof.return_value = "mock_dpop_jwt_string"
    return signer


@pytest.fixture
def auth_instance(mock_signer):
    return DPoPAuth(
        signer=mock_signer,
        access_token="initial_access_token",
        refresh_token="initial_refresh_token",
        refresh_url="https://auth.server/token",
    )
