from __future__ import annotations

import sys
from pathlib import Path

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


async def _create_project(client: AsyncClient, name: str) -> int:
    response = await client.post(
        "/api/research/growth-projects",
        json={
            "name": name,
            "primary_goal": "competitor_monitoring",
            "platforms": ["xhs", "dy"],
            "keywords": [name],
            "start_immediately": False,
        },
    )
    assert response.status_code == 200, response.text
    return int(response.json()["project_record_id"])


@pytest.mark.asyncio
async def test_competitor_accounts_can_be_scoped_to_multiple_projects(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "competitor-project-scope.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))

    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await authenticate_test_client(
            client,
            email="competitor-project@example.com",
            organization_name="Competitor Project Workspace",
        )
        project_a_id = await _create_project(client, "Project A")
        project_b_id = await _create_project(client, "Project B")

        create_a = await client.post(
            "/api/competitors",
            json={
                "project_id": project_a_id,
                "platform": "xhs",
                "creator_id": "shared-brand",
                "monitor_type": "competitor",
                "display_name": "Shared Brand",
            },
        )
        assert create_a.status_code == 200, create_a.text
        assert create_a.json()["project_ids"] == [project_a_id]

        list_a = await client.get(f"/api/competitors?project_id={project_a_id}&monitor_type=competitor")
        assert list_a.status_code == 200, list_a.text
        assert [item["creator_id"] for item in list_a.json()["competitors"]] == ["shared-brand"]

        list_b_empty = await client.get(f"/api/competitors?project_id={project_b_id}&monitor_type=competitor")
        assert list_b_empty.status_code == 200, list_b_empty.text
        assert list_b_empty.json()["competitors"] == []

        create_b = await client.post(
            "/api/competitors",
            json={
                "project_id": project_b_id,
                "platform": "xhs",
                "creator_id": "shared-brand",
                "monitor_type": "competitor",
                "display_name": "Shared Brand",
            },
        )
        assert create_b.status_code == 200, create_b.text
        assert create_b.json()["project_ids"] == [project_a_id, project_b_id]

        list_b = await client.get(f"/api/competitors?project_id={project_b_id}&monitor_type=competitor")
        assert list_b.status_code == 200, list_b.text
        assert [item["creator_id"] for item in list_b.json()["competitors"]] == ["shared-brand"]

    await close_engines()
