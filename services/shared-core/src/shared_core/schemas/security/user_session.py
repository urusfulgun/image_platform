from typing import NamedTuple

from shared_core.dto.key_pair import KeyPair
from shared_core.schemas.security.token_set import TokenSet


class UserSession(NamedTuple):
    token_set: TokenSet
    key_pair: KeyPair
