from abc import ABC, abstractmethod


class DPoPSigner(ABC):
    @abstractmethod
    def sign_proof(
        self, method: str, url: str, nonce: str = None, access_token: str = None
    ) -> str:
        pass

    @abstractmethod
    def get_jwk(self) -> dict:
        pass
