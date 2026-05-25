from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from config.db_config import sqlite_db_config
from database.db_session import close_engines, create_tables
from saas.service import AuthError, AuthService


@pytest.mark.asyncio
async def test_register_creates_user_org_membership_and_tokens(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "service-test-secret")
    monkeypatch.delenv("SAAS_PLATFORM_ADMIN_EMAILS", raising=False)
    db_path = tmp_path / "saas-service.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    result = await AuthService().register(
        email="Owner@Example.COM ",
        password="secure-password",
        organization_name="Owner Workspace",
    )

    assert result["user"]["email"] == "owner@example.com"
    assert result["organization"]["name"] == "Owner Workspace"
    assert result["membership"]["role"] == "member"
    assert result["permissions"]["is_platform_admin"] is False
    assert result["access_token"]
    assert result["refresh_token"]

    await close_engines()


@pytest.mark.asyncio
async def test_configured_platform_admin_email_gets_admin_permission(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "service-test-secret")
    monkeypatch.delenv("SAAS_PLATFORM_ADMIN_EMAILS", raising=False)
    monkeypatch.setenv("SAAS_PLATFORM_ADMIN_EMAILS", "admin@example.com")
    db_path = tmp_path / "saas-platform-admin.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    result = await AuthService().register(
        email="Admin@Example.COM",
        password="secure-password",
        organization_name="Admin Workspace",
    )

    assert result["membership"]["role"] == "member"
    assert result["permissions"]["is_platform_admin"] is True

    await close_engines()


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "service-test-secret")
    monkeypatch.delenv("SAAS_PLATFORM_ADMIN_EMAILS", raising=False)
    db_path = tmp_path / "saas-duplicate.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    service = AuthService()
    await service.register(
        email="owner@example.com",
        password="secure-password",
        organization_name="Owner Workspace",
    )

    with pytest.raises(AuthError) as exc_info:
        await service.register(
            email="OWNER@example.com",
            password="secure-password",
            organization_name="Second Workspace",
        )

    assert exc_info.value.code == "EMAIL_ALREADY_REGISTERED"
    await close_engines()


@pytest.mark.asyncio
async def test_login_and_refresh_token_rotation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "service-test-secret")
    monkeypatch.delenv("SAAS_PLATFORM_ADMIN_EMAILS", raising=False)
    db_path = tmp_path / "saas-login.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    service = AuthService()
    await service.register(
        email="owner@example.com",
        password="secure-password",
        organization_name="Owner Workspace",
    )

    login = await service.login(email="owner@example.com", password="secure-password")
    refreshed = await service.refresh(login["refresh_token"])

    assert refreshed["access_token"]
    assert refreshed["refresh_token"] != login["refresh_token"]

    with pytest.raises(AuthError) as exc_info:
        await service.refresh(login["refresh_token"])

    assert exc_info.value.code == "INVALID_REFRESH_TOKEN"
    await close_engines()
