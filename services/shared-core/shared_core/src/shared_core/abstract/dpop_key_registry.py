from shared_core.abstract.dpop_signer import DPoPSigner
from shared_core.abstract.signer_factory import DPoPSignerFactory


class DPoPKeyRegistry:
    """Utility to reconstitute Signer objects from persistent storage."""

    def __init__(self):
        self._instances: dict[str, DPoPSigner] = {}

    def get_signer(self, kid: str) -> DPoPSigner:
        if kid not in self._instances:
            # Trigger the Factory if the key is unknown
            new_signer = DPoPSignerFactory.create_es256_signer(kid)
            self.register_signer(kid, new_signer)

        return self._instances[kid]

    def register_signer(self, kid: str, signer: DPoPSigner) -> None:
        self._instances[kid] = signer

    @staticmethod
    def reconstitute_signer(kid: str, private_key_pem: str) -> DPoPSigner:
        """
        Takes a PEM string retrieved from Redis and turns it into a 
        DPoPSigner object ready for signing.
        """
        # 1. Load the private key from PEM bytes
        signer = DPoPSignerFactory.reconstitute_es256_signer(kid, private_key_pem)
        
        # 2. Return the Signer instance (Ensure kid is attached for DPoP headers)
        return signer
