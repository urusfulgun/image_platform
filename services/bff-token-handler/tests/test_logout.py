"""Tests for the /logout route."""
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from keycloak import KeycloakPostError
from shared_core.schemas.security.token_set import TokenSet
from shared_core.schemas.security.user_session import UserSession

from bff_token_handler import main
from bff_token_handler.auth.dpop import generate_ec_key_pair
from bff_token_handler.settings import settings

SESSION_ID = "test-session-id"


@pytest.fixture
def user_session():
    token_set = TokenSet(
        access_token="access",
        refresh_token="refresh",
        id_token="id.token.value",
        expires_in=300,
        token_type="DPoP",
    )
    return UserSession(token_set=token_set, key_pair=generate_ec_key_pair())


@pytest.fixture
def session_store():
    store = AsyncMock()
    store.get = AsyncMock(return_value=None)
    store.delete = AsyncMock()
    return store


@pytest.fixture
def revoke(mocker):
    return mocker.patch.object(main, "revoke_token_at_keycloak", new=AsyncMock())


@pytest.fixture
def client(session_store):
    # Not used as a context manager, so the Redis/Keycloak lifespan does not run
    main.app.state.session_store = session_store
    return TestClient(main.app)


def _assert_cookie_cleared(response):
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{settings.session_cookie_name}=")
    assert "Max-Age=0" in set_cookie


def test_logout_without_cookie(client, session_store, revoke):
    response = client.post("/logout")

    assert response.status_code == 200
    assert response.json() == {"detail": "Already logged out"}
    session_store.get.assert_not_awaited()
    revoke.assert_not_awaited()


def test_logout_with_expired_session_clears_cookie(client, session_store, revoke):
    client.cookies.set(settings.session_cookie_name, SESSION_ID)

    response = client.post("/logout")

    assert response.status_code == 200
    assert response.json() == {"detail": "Already logged out"}
    _assert_cookie_cleared(response)
    session_store.delete.assert_not_awaited()
    revoke.assert_not_awaited()


def test_logout_revokes_and_deletes_session(client, session_store, revoke, user_session):
    session_store.get.return_value = user_session
    client.cookies.set(settings.session_cookie_name, SESSION_ID)

    response = client.post("/logout")

    assert response.status_code == 200
    body = response.json()
    assert body["detail"] == "Logged out and revoked"
    revoke.assert_awaited_once_with(
        refresh_token="refresh", dpop_key_pair=user_session.key_pair
    )
    session_store.delete.assert_awaited_once_with(SESSION_ID)
    _assert_cookie_cleared(response)

    url = urlsplit(body["logoutUrl"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == settings.logout_url
    assert parse_qs(url.query) == {
        "id_token_hint": ["id.token.value"],
        "post_logout_redirect_uri": [settings.frontend_url],
    }


def test_logout_skips_revocation_without_refresh_token(
    client, session_store, revoke, user_session
):
    token_set = user_session.token_set.model_copy(update={"refresh_token": None})
    session_store.get.return_value = user_session._replace(token_set=token_set)
    client.cookies.set(settings.session_cookie_name, SESSION_ID)

    response = client.post("/logout")

    assert response.status_code == 200
    assert response.json()["detail"] == "Logged out locally"
    revoke.assert_not_awaited()
    session_store.delete.assert_awaited_once_with(SESSION_ID)
    _assert_cookie_cleared(response)


def test_logout_completes_locally_when_revocation_fails(
    client, session_store, revoke, user_session
):
    session_store.get.return_value = user_session
    revoke.side_effect = KeycloakPostError(error_message="boom", response_code=500)
    client.cookies.set(settings.session_cookie_name, SESSION_ID)

    response = client.post("/logout")

    assert response.status_code == 200
    body = response.json()
    assert body["detail"] == "Logged out locally"
    assert "logoutUrl" in body
    session_store.delete.assert_awaited_once_with(SESSION_ID)
    _assert_cookie_cleared(response)
