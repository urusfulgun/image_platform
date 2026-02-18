from joserfc import jwk
from shared_core.shared_dto.key_pair import ECKeyPair


def get_ec_keys() -> ECKeyPair:
    ec_key = jwk.generate_key("EC", "P-256")
    private_key: jwk.ECKey = jwk.ECKey.import_key(ec_key.private_key)
    public_key: jwk.ECKey = jwk.ECKey.import_key(ec_key.public_key)
    return ECKeyPair(private_key, public_key)
