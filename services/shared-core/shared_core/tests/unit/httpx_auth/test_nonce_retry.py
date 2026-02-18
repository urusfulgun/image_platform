import httpx
import pytest


@pytest.mark.asyncio
async def test_dpop_auth_nonce_retry(auth_instance, mock_signer):
    # Setup a mock transport to simulate the 401 -> 200 flow
    # 1st call: returns 401 with DPoP-Nonce
    # 2nd call: returns 200
    mock_responses = [
        httpx.Response(401, headers={"DPoP-Nonce": "new_server_nonce"}),
        httpx.Response(200, json={"data": "success"})
    ]
    
    async def handler(request):
        return mock_responses.pop(0)

    async with httpx.AsyncClient(auth=auth_instance, transport=httpx.MockTransport(handler)) as client:
        response = await client.get("https://api.example.com/resource")
        
        assert response.status_code == 200
        assert response.json() == {"data": "success"}
        
        # Verify signer was called twice
        # 1st call with None, 2nd call with 'new_server_nonce'
        assert mock_signer.sign_proof.call_count == 2
        mock_signer.sign_proof.assert_any_call(
            method="GET", 
            url="https://api.example.com/resource", 
            nonce="new_server_nonce", 
            access_token="initial_access_token"
        )