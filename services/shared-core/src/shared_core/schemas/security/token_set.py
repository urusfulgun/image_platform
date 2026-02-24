from typing import Literal
from pydantic import BaseModel


class TokenSet(BaseModel):
    """Container for token introspection result."""

    access_token: str
    refresh_token: str | None
    id_token: str | None
    expires_in: int
    token_type: Literal["DPoP"]
