import base64
from typing import Annotated

from cryptography.hazmat.primitives import serialization
from pydantic import BaseModel, PlainSerializer, SecretStr, field_validator

# This tells Pydantic: "When turning this into JSON, use the raw string value"
SecretStringRaw = Annotated[
    SecretStr, PlainSerializer(lambda v: v.get_secret_value(), return_type=str)
]


class ECKeyPairModel(BaseModel):
    public_key_b64: str
    private_key_b64: SecretStringRaw

    @field_validator("private_key_b64", mode="after")
    @classmethod
    def validate_private_key(cls, v: SecretStr):
        # 1. Extract the raw string from the SecretStr object
        raw_b64 = v.get_secret_value()

        try:
            # 2. Decode the Base64 string into bytes
            pem_bytes = base64.b64decode(raw_b64)

            # 3. Validate the bytes are a proper PEM-formatted EC key
            serialization.load_pem_private_key(pem_bytes, password=None)
            return v
        except Exception as e:
            raise ValueError(f"Invalid Private Key Data: {e!s}")

    @field_validator("public_key_b64")
    @classmethod
    def validate_public_key(cls, v: str):
        try:
            pem_bytes = base64.b64decode(v)
            serialization.load_pem_public_key(pem_bytes)
            return v
        except Exception as e:
            raise ValueError(f"Invalid Public Key Data: {e!s}")
