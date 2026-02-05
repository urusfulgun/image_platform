import httpx
import uuid
import time
from fastapi import Request, HTTPException, Depends
from joserfc import jwt, jwk


class BFFProxyService:
    def __init__(self, settings: Any):
        self.settings = settings
        self.gateway_url = settings.api_gateway_url
        self.dpop_private_key = jwk.import_key(settings.dpop_private_key_pem)

    def _create_request_dpop_proof(self, target_url: str, method: str) -> str:
        """
        Creates a fresh DPoP proof for the specific API Gateway call.
        """
        header = {
            "typ": "dpop+jwt",
            "alg": "ES256",
            "jwk": self.dpop_private_key.as_dict(is_private=False),
        }

        payload = {
            "jti": str(uuid.uuid4()),
            "htm": method,
            "htu": target_url,
            "iat": int(time.time()),
        }

        return jwt.encode(header, payload, self.dpop_private_key)

    async def forward_to_gateway(self, request: Request, path: str):
        """
        Converts a Cookie-based browser request into a DPoP-bound Gateway request.
        """
        # 1. Retrieve the Access Token from the secure Server-Side Session
        # In a real app, 'request.state.session' would be populated from Redis via middleware
        access_token = request.state.session.get("access_token")
        if not access_token:
            raise HTTPException(status_code=401, detail="Session expired")

        # 2. Prepare the target URL
        full_target_url = f"{self.gateway_url}/{path}"
        method = request.method

        # 3. Generate the DPoP Proof SPECIFIC to this request
        dpop_proof = self._create_request_dpop_proof(full_target_url, method)

        # 4. Proxy the request to the API Gateway
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"DPoP {access_token}",
                "DPoP": dpop_proof,
                "Content-Type": "application/json",
            }

            # Read the incoming body if it exists
            body = await request.body()

            response = await client.request(
                method=method,
                url=full_target_url,
                headers=headers,
                content=body,
                params=request.query_params,
            )

            # 5. Return the Gateway's response back to the Frontend
            return response.json(), response.status_code
