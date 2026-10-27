"""Characterization: GET /me returns the profile from Keycloak userinfo."""

import logging
from unittest.mock import AsyncMock

import pytest
from keycloak import KeycloakAuthenticationError

from bff_token_handler.auth import oauth
from bff_token_handler.settings import settings
from tests.api.helpers import PROFILE_CLAIMS, USERINFO_CLAIMS, make_id_token


def test_me_without_cookie_is_401(client, introspect_token):
    resp = client.get("/me")

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Not authenticated"}
    introspect_token.assert_not_awaited()


def test_me_returns_profile_from_userinfo_dict(client, seed_session, introspect_token):
    session = seed_session()

    resp = client.get("/me")

    assert resp.status_code == 200
    # Internal claims (sub, iss) are dropped by UserProfileResponse
    assert resp.json() == {"id_token": PROFILE_CLAIMS}
    args = introspect_token.await_args.args
    assert (
        args[0].public_key.public_numbers()
        == session.key_pair.public_key.public_numbers()
    )
    assert args[1] == session.token_set.access_token


def test_me_decodes_jws_userinfo_without_verifying(
    client, seed_session, introspect_token
):
    seed_session()
    # Signature segment is garbage; the BFF never checks it
    introspect_token.return_value = make_id_token(USERINFO_CLAIMS)

    resp = client.get("/me")

    assert resp.status_code == 200
    assert resp.json() == {"id_token": PROFILE_CLAIMS}


def test_me_passes_through_keycloak_auth_error(client, seed_session, introspect_token):
    seed_session()
    introspect_token.side_effect = KeycloakAuthenticationError(
        error_message="invalid_token", response_code=401
    )

    resp = client.get("/me")

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Not authenticated extra: invalid_token"}


def test_me_with_incomplete_profile_is_500(client, seed_session, introspect_token):
    seed_session()
    introspect_token.return_value = {
        k: v for k, v in USERINFO_CLAIMS.items() if k != "email"
    }

    resp = client.get("/me")

    assert resp.status_code == 500


@pytest.mark.known_bug
def test_me_with_gone_session_is_500(client, introspect_token):
    # CHARACTERIZATION: changes in R8 (expired session returns 401)
    client.cookies.set(settings.session_cookie_name, "no-such-session")

    resp = client.get("/me")

    assert resp.status_code == 500
    introspect_token.assert_not_awaited()


@pytest.mark.known_bug
def test_introspect_token_logs_dpop_proof(client, seed_session, mocker, caplog):
    # CHARACTERIZATION: changes in R3 (stop logging tokens and proofs)
    caplog.set_level(logging.INFO, logger="bff_token_handler.auth.oauth")
    user_info = mocker.patch.object(
        oauth, "dpop_user_info", new=AsyncMock(return_value=dict(USERINFO_CLAIMS))
    )
    seed_session()

    resp = client.get("/me")

    assert resp.status_code == 200
    proof = user_info.await_args.args[0].connection.headers["DPoP"]
    assert f"DPoP Proof header ---> {proof}" in caplog.text
