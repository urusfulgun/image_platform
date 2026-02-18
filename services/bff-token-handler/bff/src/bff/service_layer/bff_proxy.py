from typing import Any, Literal
import httpx
import uuid
import time
from fastapi import Request, HTTPException, Depends
from joserfc import jwt, jwk
from pydantic import HttpUrl
from shared_core.schemas.dpop import DPoPProofHeader, DPoPProofPayload
from shared_core.shared_types.http_request import MethodType
from bff.config import BFFSettings
from shared_core.schemas import jwk as jwk_schema


class BFFProxyService:
    settings: BFFSettings
    gateway_url: HttpUrl
    token_url: HttpUrl

    def __init__(self, settings: BFFSettings):
        self.settings = settings
        self.gateway_url = HttpUrl(settings.API_GATEWAY_URL)
        self.token_url = HttpUrl(self.settings.token_url)
        self.dpop_private_key = jwk.import_key(settings.DPOP_PRIVATE_KEY_PEM)

    def _produce_dpop_header(
        self, typ: Literal["dpop+jwt"], alg: Literal["ES256"]
    ) -> DPoPProofHeader:
        return DPoPProofHeader(
            typ=typ,
            alg=alg,
            jwk=jwk_schema.DPoPClientPublicKey.model_validate(
                self.dpop_private_key.as_dict(is_private=False)
            ),
        )

    def _produce_payload(
        self,
        jti: int,
        htm: MethodType,
        htu: HttpUrl,
        iat: int,
    ) -> DPoPProofPayload:
        return DPoPProofPayload(
            jti=jti,
            htm=htm,
            htu=htu,
            iat=iat,
        )

    def _create_request_dpop_proof(
        self, target_url: HttpUrl, method: MethodType
    ) -> str:
        """
        Creates a fresh DPoP proof for the specific API Gateway call.
        """
        header = self._produce_dpop_header(typ="dpop+jwt", alg="ES256")
        created_at = int(time.time())
        jti = str(uuid.uuid7())
        claims = self._produce_payload(
            jti=jti,
            htm=method,
            htu=target_url,
            iat=created_at,
        )
        return jwt.encode(
            header.model_dump(),
            claims.model_dump(),
            self.dpop_private_key,
        )

    async def _refresh_access_token(self, session_data: dict) -> str:
        """
        Swaps the Refresh Token for a new DPoP-bound Access Token.
        """
        refresh_token = session_data.get("refresh_token")

        # 1. DPoP Proof for the Token Endpoint
        dpop_proof = self._create_request_dpop_proof(self.token_url, "POST")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
        }

        headers = {"DPoP": dpop_proof}

        async with httpx.AsyncClient() as client:
            response = await client.post(self.token_url, data=data, headers=headers)

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
