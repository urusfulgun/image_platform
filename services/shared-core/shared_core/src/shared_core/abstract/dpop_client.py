import base64
import hashlib
import time
from typing import Any
import uuid
from pydantic import HttpUrl
from shared_core.abstract.dpop_signer import DPoPSigner
from joserfc import jwt, jws, jwk
from shared_core.schemas.dpop import DPoPProofHeader, DPoPProofPayload
from shared_core.schemas import jwk as jwk_schema
from shared_core.shared_types.http_request import MethodType
from shared_core.helpers.access_token import compute_ath


class DPoPClient(DPoPSigner):
    """Handles the JWT creation for DPoP."""

    _private_key: jwk.ECKey
    _public_key: jwk.ECKey
    _jwk: jwk.ECKey
    _alg: str

    def __init__(self, private_key: jwk.ECKey, public_key: jwk.ECKey, alg="ES256"):
        self.set_proof_key_pair(private_key, public_key, alg)

    @property
    def public_key(self) -> jwk.ECKey:
        return self._public_key

    @property
    def private_key(self) -> jwk.ECKey:
        return self._private_key

    @property
    def jwk(self) -> dict[str, Any]:
        return self._jwk

    @property
    def alg(self) -> str:
        return self._alg

    def set_proof_key_pair(
        self,
        private_key: jwk.ECKey,
        public_key: jwk.ECKey,
        alg="ES256",
    ):
        if not private_key.is_private:
            raise ValueError("Expected private key. Got public.")
        self._private_key = private_key
        if public_key.private_key:
            raise ValueError("Expected public_key. Got private.")
        self._public_key = public_key
        self._jwk = jwk_schema.DPoPClientPublicKey.model_validate(public_key.as_dict())
        self._alg = alg

    def compute_ath(self, access_token: str) -> str:
        return compute_ath(access_token)

    def sign_proof(
        self, method: MethodType, url: HttpUrl, nonce=None, access_token=None
    ) -> str:
        ath: str | None = None
        if access_token:
            ath = self.compute_ath(access_token)

        claims = DPoPProofPayload(
            jti=str(uuid.uuid7()),
            htm=method.upper(),
            htu=str(url).split("?")[0],
            iat=int(time.time()),
            nonce=nonce,
            ath=ath,
        )
        header = DPoPProofHeader(
            typ="dpop+jwt",
            alg=self.alg,
            jwk=self.jwk,
        )
        return jwt.encode(
            header=header.model_dump(mode="json", exclude_none=True),
            claims=claims.model_dump(mode="json", exclude_none=True),
            key=self.private_key,
        )
