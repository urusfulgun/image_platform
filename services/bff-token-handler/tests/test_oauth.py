"""Tests for PKCE helpers."""
import pytest
import base64
import hashlib

from bff_token_handler.auth.oauth import generate_pkce_pair, build_auth_url


def test_pkce_pair_challenge_matches_verifier():
    verifier, challenge = generate_pkce_pair()

    # Manually compute expected challenge
    digest = hashlib.sha256(verifier.encode()).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert challenge == expected


def test_pkce_verifier_is_url_safe():
    verifier, _ = generate_pkce_pair()
    assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
               for c in verifier)


def test_build_auth_url_contains_required_params():
    url = build_auth_url(state="mystate", code_challenge="mychallenge")
    assert "response_type=code" in url
    assert "code_challenge=mychallenge" in url
    assert "code_challenge_method=S256" in url
    assert "state=mystate" in url
    assert "openid" in url


def test_pkce_pairs_are_unique():
    _, c1 = generate_pkce_pair()
    _, c2 = generate_pkce_pair()
    assert c1 != c2
