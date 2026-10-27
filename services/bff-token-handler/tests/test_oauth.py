"""Tests for PKCE helpers."""

import base64
import hashlib

import pytest
from keycloak import KeycloakOpenID

from bff_token_handler.auth.oauth import build_auth_url, clean_bytes, generate_pkce_pair


def test_pkce_pair_challenge_matches_verifier():
    verifier, challenge, _challenge_method = generate_pkce_pair()

    # Manually compute expected challenge
    digest = hashlib.sha256(verifier.encode()).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert challenge == expected


def test_pkce_verifier_is_url_safe():
    verifier, _, _ = generate_pkce_pair()
    assert all(
        c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        for c in verifier
    )


def test_build_auth_url_contains_required_params(mocker):
    keycloak_openid = KeycloakOpenID(
        server_url="http://keycloak.test", realm_name="test", client_id="bff"
    )
    # auth_url() fetches the well-known config; stub it to stay offline
    mocker.patch.object(
        keycloak_openid,
        "well_known",
        return_value={
            "authorization_endpoint": "http://keycloak.test/realms/test/protocol/openid-connect/auth"
        },
    )

    url = build_auth_url(
        keycloak_openid,
        state="mystate",
        code_challenge="mychallenge",
        code_challenge_method="S256",
    )
    assert "response_type=code" in url
    assert "code_challenge=mychallenge" in url
    assert "code_challenge_method=S256" in url
    assert "state=mystate" in url
    assert "openid" in url


def test_pkce_pairs_are_unique():
    _, c1, _ = generate_pkce_pair()
    _, c2, _ = generate_pkce_pair()
    assert c1 != c2


def test_clean_bytes_decodes_nested_bytes():
    data = {"sub": b"abc", "groups": [b"admin", "user"], "profile": {"name": b"Jane"}}
    assert clean_bytes(data) == {
        "sub": "abc",
        "groups": ["admin", "user"],
        "profile": {"name": "Jane"},
    }


def test_clean_bytes_passes_through_json_scalars():
    data = {
        "email": "j@example.com",
        "email_verified": True,
        "exp": 1700000000,
        "score": 0.5,
        "nickname": None,
    }
    assert clean_bytes(data) == data


def test_clean_bytes_rejects_non_json_values():
    with pytest.raises(TypeError):
        clean_bytes({"bad": object()})
