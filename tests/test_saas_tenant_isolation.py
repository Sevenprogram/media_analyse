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
from research.repository import ResearchRepository


@pytest.fixture(autouse=True)
def auth_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "tenant-isolation-test-secret")
    monkeypatch.delenv("SAAS_PLATFORM_ADMIN_EMAILS", raising=False)


def _headers(auth: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {auth['access_token']}",
        "X-Org-Id": str(auth["organization"]["id"]),
    }


async def _register(client: AsyncClient, *, email: str, organization: str) -> dict:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "secure-password",
            "organization_name": organization,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_research_data_is_isolated_by_current_account(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "tenant-isolation.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        alice = await _register(
            client,
            email="alice-isolation@example.com",
            organization="Alice Workspace",
        )
        bob = await _register(
            client,
            email="bob-isolation@example.com",
            organization="Bob Workspace",
        )

        alice_headers = _headers(alice)
        bob_headers = _headers(bob)

        project_response = await client.post(
            "/api/research/growth-projects",
            headers=alice_headers,
            json={
                "name": "Alice Pet Growth",
                "primary_goal": "keyword_expansion",
                "platforms": ["xhs"],
                "keywords": ["cat food"],
                "collection_depth": "standard",
                "refresh_cadence": "off",
                "auto_ai_analysis": False,
                "start_immediately": False,
            },
        )
        assert project_response.status_code == 200, project_response.text
        project = project_response.json()

        alice_projects = await client.get("/api/research/growth-projects", headers=alice_headers)
        assert alice_projects.status_code == 200
        assert [item["name"] for item in alice_projects.json()["projects"]] == [
            "Alice Pet Growth"
        ]

        bob_projects = await client.get("/api/research/growth-projects", headers=bob_headers)
        assert bob_projects.status_code == 200
        assert bob_projects.json()["projects"] == []

        bob_project_detail = await client.get(
            f"/api/research/growth-projects/{project['project_record_id']}",
            headers=bob_headers,
        )
        assert bob_project_detail.status_code == 404

        lead_response = await client.post(
            f"/api/research/growth-projects/{project['project_id']}/leads/import",
            headers=alice_headers,
            json={
                "source_system": "manual",
                "items": [
                    {
                        "external_lead_id": "alice-lead-1",
                        "lead_status": "new",
                        "source_platform": "xhs",
                    }
                ],
            },
        )
        assert lead_response.status_code == 200

        bob_leads = await client.get("/api/research/leads?scope=global", headers=bob_headers)
        assert bob_leads.status_code == 200
        assert bob_leads.json()["leads"] == []

        tracker_response = await client.post(
            "/api/content-tracking/trackers",
            headers=alice_headers,
            json={
                "name": "Alice Tracker",
                "platforms": ["xhs"],
                "included_keywords": ["cat food"],
                "excluded_keywords": [],
                "enabled": True,
            },
        )
        assert tracker_response.status_code == 200, tracker_response.text
        tracker = tracker_response.json()

        run = await ResearchRepository(org_id=int(alice["organization"]["id"])).create_content_tracker_analysis_run(
            {
                "tracker_id": tracker["id"],
                "status": "completed",
                "analysis_version": "test",
                "window_days": 7,
            }
        )

        bob_trackers = await client.get("/api/content-tracking/trackers", headers=bob_headers)
        assert bob_trackers.status_code == 200
        assert bob_trackers.json()["trackers"] == []

        bob_tracker_update = await client.patch(
            f"/api/content-tracking/trackers/{tracker['id']}",
            headers=bob_headers,
            json={"enabled": False},
        )
        assert bob_tracker_update.status_code == 404

        bob_analysis_run = await client.get(
            f"/api/content-tracking/analysis-runs/{run['id']}",
            headers=bob_headers,
        )
        assert bob_analysis_run.status_code == 404

        candidate_response = await client.post(
            "/api/creator-search/candidate-pool",
            headers=alice_headers,
            json={
                "platform": "xhs",
                "creator_id": "alice-creator",
                "pool_name": "alice-pool",
                "match_score": 91,
            },
        )
        assert candidate_response.status_code == 200, candidate_response.text

        bob_candidates = await client.get(
            "/api/creator-search/candidate-pool",
            headers=bob_headers,
        )
        assert bob_candidates.status_code == 200
        assert bob_candidates.json()["candidates"] == []

    await close_engines()
