from typing import Literal


type PyblicKeyType = Literal["RSA", "EC"]
type JSONWebKeySetType = Literal[
    "ES256",
    "ES384",
    "ES512",
    "HS256",
    "HS384",
    "HS512",
    "RS256",
    "RS384",
    "RS512",
]
type IntendedUseType = Literal["sig", "enc"]
type ECJWKSetType = Literal[
    "ES256",
    "ES384",
    "ES512",
]
