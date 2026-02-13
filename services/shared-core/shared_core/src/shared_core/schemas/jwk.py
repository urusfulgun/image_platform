from typing import Literal
from pydantic import BaseModel, Field
from shared_core.shared_types import jwk as jwk_types


class JSONWebKey(BaseModel):
    kid: str
    kty: jwk_types.PyblicKeyType
    alg: jwk_types.JSONWebKeySetType
    use: jwk_types.IntendedUseType


class ECJWK(JSONWebKey):
    kty: Literal["EC"]
    x: str
    y: str
    alg: jwk_types.ECJWKSetType
