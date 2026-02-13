import base64
import hashlib
import time
import uuid
from pydantic import HttpUrl
from shared_core.abstract.dpop_signer import DPoPSigner
from joserfc import jwt, jws, jwk
from shared_core.schemas.dpop import DPoPHeader, DPoPProofPayload
from shared_core.schemas import jwk as jwk_schema
from shared_core.shared_types.http_request import MethodType
from shared_core.helpers.access_token import compute_ath


class DPoPClient(DPoPSigner):
    """Handles the JWT creation for DPoP."""

    private_key: jwk.ECKey
    jwk: jwk.ECKey

    def __init__(self, private_key: jwk.ECKey, public_jwk: jwk.ECKey, alg="ES256"):
        self.private_key = private_key
        if not private_key.is_private:
            raise ValueError("Expected private key. Got public.")
        self.jwk = public_jwk
        if public_jwk.private_key:
            raise ValueError("Expected public_key. Got private.")
        self.alg = alg

    def get_jwk(self) -> dict:
        return jwk_schema.ECJWK(**self.jwk.as_dict(private=False)).model_dump()

    def compute_ath(self, access_token: str) -> str:
        return compute_ath(access_token)

    def sign_proof(
        self, method: MethodType, url: HttpUrl, nonce=None, access_token=None
    ):
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
        header = DPoPHeader(
            typ="dpop+jwt",
            alg=self.alg,
            jwk=jwk_schema.ECJWK(**self.get_jwk()),
        )
        return jwt.encode(
            header=header,
            claims=claims,
            key=self.private_key,
            algorithms=[self.alg],
        )
