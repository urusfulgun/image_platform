from pydantic import BaseModel

from shared_core.schemas.security.key_pair import ECKeyPairModel
from shared_core.schemas.security.token_set import TokenSet


class SessionData(BaseModel):
    token_set: TokenSet
    key_pair: ECKeyPairModel
