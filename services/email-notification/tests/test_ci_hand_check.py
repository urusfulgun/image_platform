"""Scratch test for the F8 fail-fast hand check; reverted in the next commit."""


def test_ci_hand_check_fails_on_purpose() -> None:
    assert 1 == 2
