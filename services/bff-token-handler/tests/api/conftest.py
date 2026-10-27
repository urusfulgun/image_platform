"""Fixtures for BFF API characterization tests.

The real app and Redis-backed stores run against an in-memory Redis fake. Keycloak
calls and the upstream AssetService are faked; the lifespan never runs.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from keycloak import KeycloakOpenID

from bff_token_handler import main
from bff_token_handler.auth.dpop import generate_ec_key_pair
from bff_token_handler.proxy import reverse_proxy
from bff_token_handler.session.redis_store import CodeVerifierStore, SessionStore
from bff_token_handler.settings import settings
from tests.api.helpers import AUTH_ENDPOINT, USERINFO_CLAIMS, FakeRedis, make_token_set

_MISSING = object()


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def app_state(fake_redis, mocker):
    keycloak_openid = KeycloakOpenID(
        server_url=settings.keycloak_url,
        realm_name=settings.realm,
        client_id=settings.client_id,
        client_secret_key=settings.client_secret,
    )
    # auth_url() fetches the well-known config; stub it to stay offline
    mocker.patch.object(
        keycloak_openid,
        "well_known",
        return_value={"authorization_endpoint": AUTH_ENDPOINT},
    )
    state = {
        "session_store": SessionStore(fake_redis),
        "verifier_store": CodeVerifierStore(fake_redis),
        "ec_key_pair": generate_ec_key_pair(),
        "keycloak_openid": keycloak_openid,
    }
    saved = {name: getattr(main.app.state, name, _MISSING) for name in state}
    for name, value in state.items():
        setattr(main.app.state, name, value)
    yield SimpleNamespace(**state)
    for name, value in saved.items():
        if value is _MISSING:
            delattr(main.app.state, name)
        else:
            setattr(main.app.state, name, value)


@pytest.fixture
def client(app_state):
    # Not used as a context manager, so the Redis/Keycloak lifespan does not run
    return TestClient(main.app, raise_server_exceptions=False, follow_redirects=False)


@pytest.fixture
def seed_session(app_state, client):
    """Store a session through the real SessionStore; put its sid in the cookie jar."""

    def seed(token_set=None, key_pair=None, *, set_cookie=True):
        token_set = token_set or make_token_set()
        key_pair = key_pair or generate_ec_key_pair()
        sid = asyncio.run(app_state.session_store.create(token_set, key_pair))
        if set_cookie:
            client.cookies.set(settings.session_cookie_name, sid)
        return SimpleNamespace(sid=sid, token_set=token_set, key_pair=key_pair)

    return seed


class FakeUpstream:
    """Records requests the proxy sends to AssetService and answers them."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.reply = lambda request: httpx.Response(200, json={"ok": True})

    def handler(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        return self.reply(request)

    @property
    def last(self) -> httpx.Request:
        assert len(self.requests) == 1, (
            f"expected one upstream call, got {len(self.requests)}"
        )
        return self.requests[0]


@pytest.fixture
def upstream(mocker):
    fake = FakeUpstream()
    real_async_client = httpx.AsyncClient
    mocker.patch.object(
        reverse_proxy.httpx,
        "AsyncClient",
        side_effect=lambda **kw: real_async_client(
            transport=httpx.MockTransport(fake.handler), **kw
        ),
    )
    return fake


@pytest.fixture
def exchange_code(mocker):
    return mocker.patch.object(
        main, "exchange_code", new=AsyncMock(return_value=make_token_set())
    )


@pytest.fixture
def introspect_token(mocker):
    return mocker.patch.object(
        main, "introspect_token", new=AsyncMock(return_value=dict(USERINFO_CLAIMS))
    )
