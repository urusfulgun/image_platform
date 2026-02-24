from typing import NamedTuple
from cryptography.hazmat.primitives.asymmetric import ec


class KeyPair(NamedTuple):
    private_key: ec.EllipticCurvePublicKey
    public_key: ec.EllipticCurvePublicKey
