from pydantic import BaseModel


class RedisSessionPayload(BaseModel):
    access_token: str
    refresh_token: str
    private_key: str
    last_nonce: str | None
    kid: str
