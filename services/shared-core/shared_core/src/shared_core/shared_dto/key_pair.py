from typing import NamedTuple
from joserfc import jwk


class ECKeyPair(NamedTuple):
    private_key: jwk.ECKey
    public_key: jwk.ECKey
