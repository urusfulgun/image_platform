import httpx
import pytest


@pytest.mark.asyncio
async def test_dpop_auth_token_refresh_success(auth_instance, mock_signer):
    # 1. First request fails with 401 (Expired Token)
    # 2. Refresh request succeeds with 200 (New Tokens)
    # 3. Final retry of original request succeeds with 200
    
    def handler(request):
        if request.url == "https://api.example.com/resource":
            if "initial_access_token" in request.headers["Authorization"]:
                return httpx.Response(401)
            if "new_access_token" in request.headers["Authorization"]:
                return httpx.Response(200, json={"status": "updated"})
        
        if str(request.url) == "https://auth.server/token":
            return httpx.Response(200, json={
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token"
            })
        
        return httpx.Response(404)

    async with httpx.AsyncClient(auth=auth_instance, transport=httpx.MockTransport(handler)) as client:
        response = await client.get("https://api.example.com/resource")
        
        assert response.status_code == 200
        assert auth_instance.access_token == "new_access_token"
        assert auth_instance.refresh_token == "new_refresh_token"