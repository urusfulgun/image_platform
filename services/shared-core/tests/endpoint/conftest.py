"""Fixtures for the rs_dpop characterization tests.

`validate_dpop` runs for real, mounted on a tiny app. Only the two Keycloak HTTP
calls it makes (`public_key()` and, inside `decode_token`, `certs()`) are replaced
by a test realm key, so python-keycloak/jwcrypto still verify the signature and
`exp`.
"""

from dataclasses import dataclass, field
from typing import Annotated

import httpx
import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI

from shared_core.utils.endpoint import rs_dpop
from tests.endpoint.helpers import BASE_URL, RealmKey, new_dpop_key, new_realm_key

Claims = Annotated[dict, Depends(rs_dpop.validate_dpop)]


@pytest.fixture(scope="session")
def realm() -> RealmKey:
    return new_realm_key()


@pytest.fixture
def dpop_key():
    return new_dpop_key()


@dataclass
class FakeKeycloak:
    realm: RealmKey
    calls: dict[str, int] = field(default_factory=lambda: {"public_key": 0, "certs": 0})
    raise_on: set[str] = field(default_factory=set)

    def _call(self, name: str) -> None:
        self.calls[name] += 1
        if name in self.raise_on:
            raise ConnectionError(f"keycloak {name} unreachable")

    def public_key(self) -> str:
        self._call("public_key")
        return self.realm.public_key_b64

    def certs(self) -> dict:
        self._call("certs")
        return {"keys": [self.realm.jwk]}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail the test if anything reaches Keycloak's real HTTP connection.

    validate_dpop swallows every exception into a 401, so the attempt is also
    recorded and asserted on teardown.
    """
    attempts = []

    def refuse(*args, **kwargs):
        attempts.append(args)
        raise AssertionError("rs_dpop tried to reach Keycloak over the network")

    conn = rs_dpop.keycloak_openid.connection
    for name in ("raw_get", "raw_post", "raw_put", "raw_delete"):
        monkeypatch.setattr(conn, name, refuse)
    yield
    assert not attempts, f"real Keycloak calls attempted: {attempts}"


@pytest.fixture
def keycloak(monkeypatch, realm) -> FakeKeycloak:
    fake = FakeKeycloak(realm)
    monkeypatch.setattr(rs_dpop.keycloak_openid, "public_key", fake.public_key)
    monkeypatch.setattr(rs_dpop.keycloak_openid, "certs", fake.certs)
    return fake


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/echo")
    @app.post("/echo")
    async def echo(claims: Claims):
        return claims

    @app.get("/items/{item_id}")
    async def item(item_id: str, claims: Claims):
        return claims

    return app


@pytest_asyncio.fixture
async def client(app, keycloak):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as c:
        yield c
