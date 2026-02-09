from typing import Any
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

    async def _refresh_access_token(self, session_data: dict) -> str:
        """
        Swaps the Refresh Token for a new DPoP-bound Access Token.
        """
        refresh_token = session_data.get("refresh_token")
        token_url = f"{self.settings.keycloak_url}/realms/{self.settings.realm}/protocol/openid-connect/token"

        # 1. DPoP Proof for the Token Endpoint
        dpop_proof = self._create_request_dpop_proof(token_url, "POST")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
        }

        headers = {"DPoP": dpop_proof}

        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=data, headers=headers)

            if response.status_code != 200:
                # Refresh token is likely expired or revoked; force re-login
                raise HTTPException(
                    status_code=401, detail="Session expired, please log in again."
                )

            new_tokens = response.json()

            # 2. Update the Server-Side Session (Redis)
            # This logic depends on your session management implementation
            await self.session_manager.update_session(
                session_data["session_id"],
                {
                    "access_token": new_tokens["access_token"],
                    "refresh_token": new_tokens.get("refresh_token", refresh_token),
                },
            )

            return new_tokens["access_token"]

    async def forward_to_gateway(self, request: Request, path: str):
        access_token = request.state.session.get("access_token")
        full_target_url = f"{self.gateway_url}/{path}"

        # Attempt the request
        response = await self._send_to_gateway(
            access_token, full_target_url, request.method, await request.body()
        )

        # 3. Automatic Retry Logic on 401
        if response.status_code == 401:
            # Try to refresh
            new_access_token = await self._refresh_access_token(request.state.session)

            # Retry the original request with the NEW token
            response = await self._send_to_gateway(
                new_access_token, full_target_url, request.method, await request.body()
            )

        return response.json(), response.status_code

    async def _send_to_gateway(self, token: str, url: str, method: str, body: bytes):
        """Helper to sign and send request to Gateway"""
        dpop_proof = self._create_request_dpop_proof(url, method)
        async with httpx.AsyncClient() as client:
            return await client.request(
                method=method,
                url=url,
                headers={"Authorization": f"DPoP {token}", "DPoP": dpop_proof},
                content=body,
            )
