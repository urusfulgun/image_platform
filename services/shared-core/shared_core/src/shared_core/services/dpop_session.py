import httpx
from typing import Generator

from pydantic import HttpUrl
from shared_core.abstract.dpop_signer import DPoPSigner
from shared_core.schemas.dpop import RefreshAccessTokenRequestData


class DPoPAuth(httpx.Auth):
    requires_response_body = True
    signer: DPoPSigner
    access_token: str
    refresh_token: str
    refresh_url: HttpUrl
    server_nonce: str | None

    def __init__(
        self,
        signer: DPoPSigner,
        access_token: str,
        refresh_token: str,
        refresh_url: HttpUrl,
    ):
        self.signer = signer
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.refresh_url = refresh_url
        self.server_nonce = None

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        # 1. Attach the DPoP Proof and Authorization header
        # Initial Attempt
        self._apply_dpop(request)

        response = yield request

        # 2. Handle DPoP Nonce Refresh (RFC 9449)
        # Check for Nonce Update (Server says: "I need a fresh nonce")
        if self._is_nonce_error(response):
            new_nonce = response.headers.get("DPoP-Nonce")
            self.server_nonce = new_nonce
            self._apply_dpop(request)  # Re-sign with new nonce
            response = yield request

        # 3. Handle Token Refresh
        # Check for Token Expiry (Server says: "Token is dead")
        if response.status_code == 401:
            refresh_response = yield self.build_refresh_request()
            # Refresh the token
            refresh_success = yield from self._do_token_refresh()
            if refresh_success:
                # Retry original request with NEW token and NEW proof
                self._apply_dpop(request)
                response = yield request
                
                # Final check: Did the retry of the original request 
                # also need a new nonce? (Rare but possible)
                if self._is_nonce_error(response):
                    self.server_nonce = response.headers.get("DPoP-Nonce")
                    self._apply_dpop(request)
                    yield request

    def _apply_dpop(self, request: httpx.Request):
        """Generates a fresh DPoP JWT and updates headers."""
        proof = self.signer.sign_proof(
            method=request.method,
            url=str(request.url),
            nonce=self.server_nonce,
            access_token=self.access_token,
        )
        request.headers["DPoP"] = proof
        request.headers["Authorization"] = f"DPoP {self.access_token}"

    def _is_nonce_error(self, response: httpx.Response) -> bool:
        """Determines if the error is specifically a DPoP nonce challenge."""
        # RFC 9449: error="use_dpop_nonce" is usually in WWW-Authenticate
        return response.headers.get(
            "DPoP-Nonce"
        ) is not None and response.status_code in (400, 401)

    def _do_token_refresh(self) -> Generator[httpx.Request, httpx.Response, bool]:
        """Handles the refresh flow, including potential nonce challenges."""
        refresh_req = self.build_refresh_request()
        refresh_res = yield refresh_req

        # Handle nonce challenge during the refresh call itself!
        if self._is_nonce_error(refresh_res):
            self.server_nonce = refresh_res.headers.get("DPoP-Nonce")
            refresh_req = self.build_refresh_request()
            refresh_res = yield refresh_req

        if refresh_res.status_code == 200:
            self.update_tokens(refresh_res)
            return True
        return False

    def build_refresh_request(self) -> httpx.Request:
        # Note: The refresh request itself MUST be DPoP signed
        # using the same key bound to the refresh_token
        refresh_data: RefreshAccessTokenRequestData = RefreshAccessTokenRequestData(
            grant_type="refresh_token",
            refresh_token=self.refresh_token,
        )

        # We create a temporary internal request to sign it
        req = httpx.Request("POST", self.refresh_url, data=refresh_data.model_dump())
        proof = self.signer.sign_proof("POST", self.refresh_url, self.server_nonce)
        req.headers["DPoP"] = proof
        return req

    def update_tokens(self, response: httpx.Response):
        data: dict = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
