from __future__ import annotations

from pathlib import Path
import sys

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import config
from config.db_config import sqlite_db_config
from database.db_session import close_engines, create_tables
from saas_test_utils import authenticate_test_client


@pytest.fixture(autouse=True)
def auth_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "side-nav-config-test-secret")


@pytest.mark.asyncio
async def test_admin_can_update_global_side_nav_config_for_all_users(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "side-nav-config.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    monkeypatch.setenv("SAAS_PLATFORM_ADMIN_EMAILS", "admin@example.com")
    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await authenticate_test_client(
            client,
            email="admin@example.com",
            organization_name="Admin Workspace",
        )

        default_response = await client.get("/api/admin/ui/side-nav-config")
        assert default_response.status_code == 200, default_response.text
        default_items = default_response.json()["value"]["items"]
        assert default_items[0]["tab"] == "today"
        assert "admin" not in {item["tab"] for item in default_items}
        assert all(item["visible"] for item in default_items)

        update_response = await client.put(
            "/api/admin/ui/side-nav-config",
            json={
                "items": [
                    {"tab": "projects", "visible": True, "sort_order": 0},
                    {"tab": "today", "visible": False, "sort_order": 10},
                    {"tab": "lead_attribution", "visible": False, "sort_order": 20},
                ]
            },
        )
        assert update_response.status_code == 200, update_response.text
        saved_items = update_response.json()["value"]["items"]
        assert saved_items[0]["tab"] == "projects"
        assert next(item for item in saved_items if item["tab"] == "today")["visible"] is False
        assert next(item for item in saved_items if item["tab"] == "lead_attribution")["visible"] is False

        await authenticate_test_client(
            client,
            email="member@example.com",
            organization_name="Member Workspace",
        )
        read_response = await client.get("/api/research/ui/side-nav-config")
        assert read_response.status_code == 200, read_response.text
        member_items = read_response.json()["value"]["items"]
        assert member_items[0]["tab"] == "projects"
        assert next(item for item in member_items if item["tab"] == "today")["visible"] is False

    await close_engines()


@pytest.mark.asyncio
async def test_side_nav_config_rejects_duplicate_or_fully_hidden_tabs(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "side-nav-config-validation.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    monkeypatch.setenv("SAAS_PLATFORM_ADMIN_EMAILS", "admin@example.com")
    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await authenticate_test_client(
            client,
            email="admin@example.com",
            organization_name="Admin Workspace",
        )

        duplicate_response = await client.put(
            "/api/admin/ui/side-nav-config",
            json={
                "items": [
                    {"tab": "today", "visible": True, "sort_order": 0},
                    {"tab": "today", "visible": True, "sort_order": 10},
                ]
            },
        )
        assert duplicate_response.status_code == 422

        hidden_response = await client.put(
            "/api/admin/ui/side-nav-config",
            json={"items": [{"tab": "today", "visible": False, "sort_order": 0}]},
        )
        assert hidden_response.status_code == 422

    await close_engines()
