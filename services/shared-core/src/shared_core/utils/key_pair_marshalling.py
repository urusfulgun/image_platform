import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from shared_core.dto.key_pair import KeyPair
from shared_core.schemas.security.key_pair import ECKeyPairModel


def marshalling_key_pair(key_pair: KeyPair) -> ECKeyPairModel:
    private_key: ec.EllipticCurvePrivateKey = key_pair.private_key

    # 1. Export Public Key to PEM bytes -> Base64 string
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pub_b64 = base64.b64encode(pub_bytes).decode("utf-8")

    # 2. Export Private Key to PEM bytes -> Base64 string
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    priv_b64 = base64.b64encode(priv_bytes).decode("utf-8")

    # 3. Create Model using the B64 strings
    model = ECKeyPairModel(public_key_b64=pub_b64, private_key_b64=priv_b64)
    return model


def unmarshalling_key_pair_from_model(key_pair_model: ECKeyPairModel) -> KeyPair:
    # 1. Extract and Decode Private Key
    priv_pem_bytes = base64.b64decode(key_pair_model.private_key_b64.get_secret_value())

    # 2. Reconstruct the object
    private_key = serialization.load_pem_private_key(priv_pem_bytes, password=None)

    return KeyPair(private_key=private_key, public_key=private_key.public_key())
