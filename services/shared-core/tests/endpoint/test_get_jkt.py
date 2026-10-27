"""Characterization: get_jkt, the RFC 7638 thumbprint used for `cnf.jkt` binding."""

import pytest

from shared_core.utils.endpoint.rs_dpop import get_jkt
from tests.endpoint.helpers import new_dpop_key, public_jwk, rfc7638_thumbprint


def test_matches_rfc7638_thumbprint():
    key = new_dpop_key()

    assert get_jkt(public_jwk(key)) == rfc7638_thumbprint(key)


def test_extra_members_do_not_change_thumbprint():
    key = new_dpop_key()
    jwk = {
        **public_jwk(key),
        "alg": "ES256",
        "use": "sig",
        "kid": "k1",
        "d": "private-part",
    }

    assert get_jkt(jwk) == rfc7638_thumbprint(key)


def test_different_keys_give_different_thumbprints():
    assert get_jkt(public_jwk(new_dpop_key())) != get_jkt(public_jwk(new_dpop_key()))


@pytest.mark.parametrize("member", ["crv", "kty", "x", "y"])
def test_missing_required_member_raises_key_error(member):
    jwk = public_jwk(new_dpop_key())
    del jwk[member]

    with pytest.raises(KeyError):
        get_jkt(jwk)
