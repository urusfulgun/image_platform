from joserfc import jwk
from shared_core.schemas.jwk import DPoPClientPublicKey


def convert_to_joserfc_key(model: DPoPClientPublicKey) -> jwk.ECKey | jwk.RSAKey:
    """
    Converts a DPoPClientPublicKey Pydantic model into a joserfc JWK object.
    """
    # 1. Dump to dict, excluding None values so we don't mix RSA/EC fields
    key_dict = model.model_dump(exclude_none=True)

    # 2. Import into joserfc
    # joserfc handles the validation of the parameters (x, y, crv, etc.)
    return jwk.import_key(key_dict)
