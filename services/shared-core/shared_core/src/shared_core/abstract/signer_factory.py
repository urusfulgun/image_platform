from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.primitives import serialization
from shared_core.abstract.dpop_client import DPoPClient
from joserfc import jwk


class DPoPSignerFactory:
    @staticmethod
    def create_rs256_signer(kid: str) -> DPoPClient:
        raise NotImplementedError
        """Generates a new RSA key pair and returns a configured DPoPClient."""
        # 1. Generate Private Key
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        # 2. Extract Public Key for JWK (Simplified for example)
        # Note: In production, use a library like 'authlib' to get full JWK 'n' and 'e'
        public_jwk = {"kty": "RSA", "alg": "RS256", "use": "sig", "kid": kid}

        print(f"[Factory] Generated new RS256 keys for KID: {kid}")
        return DPoPClient(private_key, public_jwk)

    @staticmethod
    def create_es256_signer(kid: str) -> DPoPClient:
        """Generates a new RSA key pair and returns a configured DPoPClient."""
        # 1. Generate Private Key
        private_key: jwk.ECKey = jwk.generate_key("EC", "P-256")

        # 2. Extract Public Key for JWK (Simplified for example)
        # Note: In production, use a library like 'authlib' to get full JWK 'n' and 'e'
        # public_jwk = {"kty": "EC", "alg": "ES256", "use": "sig", "kid": kid}

        public_jwk: jwk.ECKey = jwk.ECKey.import_key(private_key.public_key)

        print(f"[Factory] Generated new ES256 keys for KID: {kid}")
        return DPoPClient(private_key, public_jwk)

    @staticmethod
    def reconstitute_es256_signer(kid: str, private_key_pem: str) -> DPoPClient:
        """
        Takes a PEM string retrieved from Redis and turns it into a
        DPoPSigner object ready for signing.
        """
        # 1. Load the private key from PEM bytes
        private_key: jwk.ECKey = jwk.ECKey.import_key(private_key_pem.encode("utf-8"))
        public_jwk: jwk.ECKey = jwk.ECKey.import_key(private_key.public_key)

        if public_jwk.kid != kid:
            raise ValueError(
                f"Expected equal kid to {kid}. Got in jwk {public_jwk.kid}"
            )

        signer = DPoPClient(
            private_key=private_key,
            public_jwk=public_jwk,
            alg="ES256",
        )

        # 2. Return the Signer instance (Ensure kid is attached for DPoP headers)
        return signer
