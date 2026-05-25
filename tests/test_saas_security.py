from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from saas.security import (
    create_access_token,
    hash_password,
    parse_access_token,
    verify_password,
)


def test_password_hash_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")

    assert hashed.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_password_hash_uses_unique_salt() -> None:
    first = hash_password("same-password")
    second = hash_password("same-password")

    assert first != second
    assert verify_password("same-password", first) is True
    assert verify_password("same-password", second) is True


def test_access_token_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "unit-test-secret")

    token = create_access_token(
        subject="42",
        expires_delta=timedelta(minutes=5),
        extra_claims={"email": "user@example.com"},
    )
    claims = parse_access_token(token)

    assert claims["sub"] == "42"
    assert claims["email"] == "user@example.com"
    assert claims["typ"] == "access"


def test_access_token_rejects_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "unit-test-secret")

    token = create_access_token(subject="42", expires_delta=timedelta(minutes=5))
    tampered = token[:-2] + "xx"

    with pytest.raises(ValueError, match="Invalid token signature"):
        parse_access_token(tampered)
