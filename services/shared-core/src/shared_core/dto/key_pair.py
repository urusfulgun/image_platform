from typing import NamedTuple
from cryptography.hazmat.primitives.asymmetric import ec


class KeyPair(NamedTuple):
    private_key: ec.EllipticCurvePrivateKey
    public_key: ec.EllipticCurvePublicKey
