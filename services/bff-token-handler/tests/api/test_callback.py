"""Characterization: GET /authorization-code/callback exchanges the code and opens a session."""

import asyncio
import logging

import pytest
from helpers import make_token_set
from keycloak import KeycloakPostError

from bff_token_handler.settings import settings

CALLBACK = "/authorization-code/callback"
STATE = "known-state"
VERIFIER = "stored-code-verifier"


@pytest.fixture
def pkce(fake_redis):
    fake_redis.data[f"pkce:{STATE}"] = VERIFIER


def _callback(client, code="auth-code", state=STATE):
    return client.get(CALLBACK, params={"code": code, "state": state})


def _sid_from(resp) -> str:
    return resp.cookies[settings.session_cookie_name]


def test_unknown_state_is_400(client, exchange_code, fake_redis):
    resp = _callback(client, state="unknown")

    assert resp.status_code == 400
    assert resp.json() == {"detail": "Invalid or expired state"}
    exchange_code.assert_not_awaited()
    assert fake_redis.keys("session:") == []


@pytest.mark.parametrize("params", [{"state": STATE}, {"code": "auth-code"}, {}])
def test_missing_params_is_422(client, pkce, exchange_code, params):
    resp = client.get(CALLBACK, params=params)

    assert resp.status_code == 422
    exchange_code.assert_not_awaited()


def test_success_exchanges_code_with_stored_verifier(
    client, app_state, pkce, exchange_code
):
    _callback(client, code="the-code")

    exchange_code.assert_awaited_once_with(
        code="the-code", code_verifier=VERIFIER, key_pair=app_state.ec_key_pair
    )


def test_success_redirects_home_with_session_cookie(client, pkce, exchange_code):
    resp = _callback(client)

    assert resp.status_code == 307
    assert resp.headers["location"] == "/"
    set_cookie = resp.headers["set-cookie"]
    attrs = [part.strip() for part in set_cookie.split(";")]
    assert attrs[0] == f"{settings.session_cookie_name}={_sid_from(resp)}"
    assert sorted(attrs[1:]) == sorted(
        ["HttpOnly", "Max-Age=3600", "Path=/", "SameSite=strict"]
    )
    assert "secure" not in set_cookie.lower()


def test_success_stores_session_that_round_trips(
    client, app_state, fake_redis, pkce, exchange_code
):
    token_set = make_token_set(access_token="fresh-access")
    exchange_code.return_value = token_set

    sid = _sid_from(_callback(client))

    key = f"session:{sid}"
    assert fake_redis.keys("session:") == [key]
    assert fake_redis.ttls[key] == settings.session_ttl_seconds == 3600
    stored = asyncio.run(app_state.session_store.get(sid))
    assert stored.token_set == token_set
    assert (
        stored.key_pair.public_key.public_numbers()
        == app_state.ec_key_pair.public_key.public_numbers()
    )


def test_every_session_shares_the_process_key_pair(
    client, app_state, fake_redis, exchange_code
):
    fake_redis.data["pkce:a"] = "verifier-a"
    fake_redis.data["pkce:b"] = "verifier-b"

    sid_a = _sid_from(_callback(client, state="a"))
    sid_b = _sid_from(_callback(client, state="b"))

    a = asyncio.run(app_state.session_store.get(sid_a))
    b = asyncio.run(app_state.session_store.get(sid_b))
    assert sid_a != sid_b
    assert (
        a.key_pair.public_key.public_numbers() == b.key_pair.public_key.public_numbers()
    )


def test_keycloak_error_during_exchange_is_500(client, pkce, exchange_code, fake_redis):
    exchange_code.side_effect = KeycloakPostError(
        error_message="invalid_grant", response_code=400
    )

    resp = _callback(client)

    assert resp.status_code == 500
    assert "set-cookie" not in resp.headers
    assert fake_redis.keys("session:") == []


@pytest.mark.known_bug
def test_pkce_state_is_reusable(client, pkce, exchange_code, fake_redis):
    # CHARACTERIZATION: changes in R8 (PKCE state becomes single-use)
    first = _callback(client)
    second = _callback(client)

    assert first.status_code == second.status_code == 307
    assert fake_redis.data[f"pkce:{STATE}"] == VERIFIER
    assert len(fake_redis.keys("session:")) == 2


@pytest.mark.known_bug
def test_callback_logs_code_and_verifier(client, pkce, exchange_code, caplog):
    # CHARACTERIZATION: changes in R3 (stop logging PKCE values)
    caplog.set_level(logging.INFO, logger="bff_token_handler.main")

    _callback(client, code="secret-code")

    assert "secret-code" in caplog.text
    assert VERIFIER in caplog.text


@pytest.mark.known_bug
def test_callback_logs_code_before_state_check(client, exchange_code, caplog):
    # CHARACTERIZATION: changes in R3 (stop logging PKCE values)
    caplog.set_level(logging.INFO, logger="bff_token_handler.main")

    resp = _callback(client, code="secret-code", state="unknown")

    assert resp.status_code == 400
    assert "secret-code" in caplog.text
