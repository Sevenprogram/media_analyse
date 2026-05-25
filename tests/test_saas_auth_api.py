from __future__ import annotations

from pathlib import Path
import sys

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from config.db_config import sqlite_db_config
from database.db_session import close_engines, create_tables


@pytest.fixture(autouse=True)
def auth_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "api-test-secret")
    monkeypatch.delenv("SAAS_PLATFORM_ADMIN_EMAILS", raising=False)


@pytest.mark.asyncio
async def test_register_login_refresh_logout(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "saas-auth-api.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        register_response = await client.post(
            "/api/auth/register",
            json={
                "email": "owner@example.com",
                "password": "secure-password",
                "organization_name": "Owner Workspace",
            },
        )
        assert register_response.status_code == 200
        registered = register_response.json()
        assert registered["token_type"] == "bearer"
        assert registered["access_token"]
        assert registered["refresh_token"]
        assert registered["user"]["email"] == "owner@example.com"
        assert registered["organization"]["name"] == "Owner Workspace"
        assert registered["membership"]["role"] == "member"
        assert registered["permissions"]["is_platform_admin"] is False

        duplicate_response = await client.post(
            "/api/auth/register",
            json={
                "email": "owner@example.com",
                "password": "secure-password",
                "organization_name": "Duplicate Workspace",
            },
        )
        assert duplicate_response.status_code == 409
        assert duplicate_response.json()["detail"]["code"] == "EMAIL_ALREADY_REGISTERED"

        login_response = await client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "secure-password"},
        )
        assert login_response.status_code == 200
        logged_in = login_response.json()
        assert logged_in["refresh_token"] != registered["refresh_token"]

        refresh_response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": logged_in["refresh_token"]},
        )
        assert refresh_response.status_code == 200
        refreshed = refresh_response.json()
        assert refreshed["refresh_token"] != logged_in["refresh_token"]

        stale_refresh_response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": logged_in["refresh_token"]},
        )
        assert stale_refresh_response.status_code == 401
        assert stale_refresh_response.json()["detail"]["code"] == "INVALID_REFRESH_TOKEN"

        logout_response = await client.post(
            "/api/auth/logout",
            json={"refresh_token": refreshed["refresh_token"]},
        )
        assert logout_response.status_code == 200
        assert logout_response.json()["revoked"] is True

    await close_engines()


@pytest.mark.asyncio
async def test_me_and_current_org_require_bearer_token(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "saas-current-org.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        unauthenticated = await client.get("/api/me")
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["detail"]["code"] == "AUTH_REQUIRED"

        unauthenticated_admin = await client.get("/api/admin/verticals")
        assert unauthenticated_admin.status_code == 401
        assert unauthenticated_admin.json()["detail"]["code"] == "AUTH_REQUIRED"

        register_response = await client.post(
            "/api/auth/register",
            json={
                "email": "owner@example.com",
                "password": "secure-password",
                "organization_name": "Owner Workspace",
            },
        )
        access_token = register_response.json()["access_token"]

        me_response = await client.get(
            "/api/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()["user"]["email"] == "owner@example.com"
        assert "password_hash" not in me_response.json()["user"]
        assert me_response.json()["organization"]["name"] == "Owner Workspace"
        assert me_response.json()["membership"]["role"] == "member"
        assert me_response.json()["permissions"]["is_platform_admin"] is False

        org_response = await client.get(
            "/api/orgs/current",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert org_response.status_code == 200
        assert org_response.json()["organization"]["slug"] == "owner-workspace"

        admin_response = await client.get(
            "/api/admin/verticals",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert admin_response.status_code == 403
        assert admin_response.json()["detail"]["code"] == "ADMIN_FORBIDDEN"

        monkeypatch.setenv("SAAS_PLATFORM_ADMIN_EMAILS", "admin@example.com")
        admin_register_response = await client.post(
            "/api/auth/register",
            json={
                "email": "admin@example.com",
                "password": "secure-password",
                "organization_name": "Admin Workspace",
            },
        )
        assert admin_register_response.status_code == 200
        admin_access_token = admin_register_response.json()["access_token"]
        assert admin_register_response.json()["membership"]["role"] == "member"
        assert admin_register_response.json()["permissions"]["is_platform_admin"] is True

        admin_me_response = await client.get(
            "/api/me",
            headers={"Authorization": f"Bearer {admin_access_token}"},
        )
        assert admin_me_response.status_code == 200
        assert admin_me_response.json()["permissions"]["is_platform_admin"] is True

        admin_response = await client.get(
            "/api/admin/verticals",
            headers={"Authorization": f"Bearer {admin_access_token}"},
        )
        assert admin_response.status_code == 200
        assert "verticals" in admin_response.json()

    await close_engines()


@pytest.mark.asyncio
async def test_research_endpoints_require_login(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "saas-research-protected.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/research/jobs")
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "AUTH_REQUIRED"

    await close_engines()
