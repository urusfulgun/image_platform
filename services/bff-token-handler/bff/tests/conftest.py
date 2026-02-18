import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from shared_core.abstract.dpop_signer import DPoPSigner

@pytest.fixture
def mock_signer():
    signer = MagicMock(spec=DPoPSigner)
    # Simulate a valid DPoP JWT return
    signer.sign_proof.return_value = "mock_dpop_jwt_string"
    return signer

@pytest.fixture
def auth_instance(mock_signer):
    from shared_core.services.dpop_session import DPoPAuth
    return DPoPAuth(
        signer=mock_signer,
        access_token="initial_access_token",
        refresh_token="initial_refresh_token",
        refresh_url="https://auth.server/token"
    )
