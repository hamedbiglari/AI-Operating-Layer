"""
Unit tests for the security primitives. No database required.
"""

from datetime import timedelta

import pytest

from app.security.passwords import hash_password, verify_password
from app.security.tokens import TokenError, decode_access_token, create_access_token


def test_password_hash_is_not_plaintext() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"


def test_password_verify_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_password_verify_rejects_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_access_token_roundtrip() -> None:
    token = create_access_token(
        user_id="11111111-1111-1111-1111-111111111111",
        organization_id="22222222-2222-2222-2222-222222222222",
        role="owner",
    )
    payload = decode_access_token(token)
    assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
    assert payload["org"] == "22222222-2222-2222-2222-222222222222"
    assert payload["role"] == "owner"


def test_expired_token_is_rejected() -> None:
    token = create_access_token(
        user_id="u", organization_id="o", role="viewer", expires_delta=timedelta(seconds=-1)
    )
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_garbage_token_is_rejected() -> None:
    with pytest.raises(TokenError):
        decode_access_token("this-is-not-a-jwt")
