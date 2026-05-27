from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import config
from config.db_config import sqlite_db_config
from database.db_session import close_engines, create_tables, get_session
from research.automation_daemon import ResearchAutomationDaemon
from research.models import (
    RawRecord,
    ResearchGrowthProject,
    ResearchGrowthProjectCollectionPlan,
    ResearchGrowthProjectKeyword,
    ResearchJob,
    ResearchPost,
)
from research.repository import ResearchRepository
from research.scheduler import ResearchScheduler
from saas_test_utils import authenticate_test_client

UTC8 = timezone(timedelta(hours=8))


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@pytest_asyncio.fixture
async def growth_project_client(tmp_path, monkeypatch):
    db_path = tmp_path / "growth-project-config-test.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))

    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await authenticate_test_client(
            client,
            email="growth-config@example.com",
            organization_name="Growth Config Workspace",
        )
        yield client

    await close_engines()


async def _create_project(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/research/growth-projects",
        json={
            "name": "Pet Growth",
            "primary_goal": "mixed_research",
            "platforms": ["xhs", "dy", "wb"],
            "keywords": ["cat food", "kitten food"],
            "collection_depth": "standard",
            "refresh_cadence": "off",
            "auto_ai_analysis": False,
            "start_immediately": False,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _seed_legacy_growth_project_with_job() -> dict:
    global_repo = ResearchRepository.global_scope()
    project = await global_repo.create_growth_project(
        {
            "name": "Legacy Pet Growth",
            "primary_goal": "mixed_research",
            "platforms": ["xhs"],
            "collection_status": "scheduled",
            "comment_collection_enabled": True,
            "refresh_cadence": "daily",
            "sample_status": "sample_insufficient",
            "recommended_action": "review_strategy",
            "archived": False,
        }
    )
    keyword = await global_repo.create_growth_project_keyword(
        {
            "project_id": project["id"],
            "keyword": "legacy pet growth",
            "keyword_type": "core",
            "source": "manual",
            "status": "active",
        }
    )
    plan = await global_repo.create_growth_project_collection_plan(
        {
            "project_id": project["id"],
            "platform": "xhs",
            "collection_mode": "search",
            "keyword_scope": "active",
            "enabled": True,
            "schedule_mode": "interval",
            "schedule_interval_minutes": 1440,
        }
    )
    job = await global_repo.create_job(
        {
            "name": "Legacy Pet Growth scheduled refresh",
            "topic": "legacy_pet_growth",
            "platforms": ["xhs"],
            "collection_mode": "search",
            "keywords": ["legacy pet growth"],
            "target_ids": [],
            "creator_ids": [],
            "start_date": date.today() - timedelta(days=29),
            "end_date": date.today(),
            "status": "completed",
            "comment_policy": {"growth_project_key": f"growth_project_record_{project['id']}"},
            "raw_record_mode": "full",
            "anonymize_authors": True,
            "schedule_enabled": True,
            "schedule_interval_minutes": 1440,
            "last_scheduled_at": datetime.now(timezone.utc) - timedelta(hours=1),
        }
    )
    async with get_session() as session:
        post = ResearchPost(
            org_id=None,
            job_id=int(job["id"]),
            platform="xhs",
            platform_post_id="legacy-pet-growth-post-1",
            author_hash="legacy-pet-growth-author-1",
            title="Legacy pet growth title",
            content="legacy pet growth sample",
            url="https://example.com/xhs/legacy-pet-growth-1",
            publish_time=datetime.now(timezone.utc) - timedelta(days=1),
            engagement_json={"like_count": 45, "comment_count": 9, "share_count": 2},
        )
        session.add(post)
        await session.flush()
        post_id = int(post.id)
    return {
        "project_record_id": int(project["id"]),
        "project_slug": "legacy_pet_growth",
        "keyword_id": int(keyword["id"]),
        "plan_id": int(plan["id"]),
        "job_id": int(job["id"]),
        "post_id": post_id,
    }


@pytest.mark.asyncio
async def test_create_growth_project_defaults_to_daily_refresh(
    growth_project_client: AsyncClient,
) -> None:
    response = await growth_project_client.post(
        "/api/research/growth-projects",
        json={
            "name": "Default Daily Project",
            "primary_goal": "mixed_research",
            "platforms": ["xhs"],
            "keywords": ["summer planning"],
            "collection_depth": "standard",
            "auto_ai_analysis": False,
            "start_immediately": False,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    detail_response = await growth_project_client.get(
        f"/api/research/growth-projects/{payload['project_id']}"
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["settings"]["refresh_cadence"] == "daily"
    assert detail["settings"]["daily_collection_limit_per_platform"] == 50
    assert payload["job"]["comment_policy"]["daily_collection_limit_per_platform"] == 50
    assert payload["job"]["comment_policy"]["max_posts_per_job"] == 50

    plans_response = await growth_project_client.get(
        f"/api/research/growth-projects/{payload['project_record_id']}/collection-plans"
    )
    assert plans_response.status_code == 200, plans_response.text
    plans = plans_response.json()["collection_plans"]
    assert plans[0]["schedule_interval_minutes"] == 1440


@pytest.mark.asyncio
async def test_create_growth_project_daily_refresh_time_uses_utc8_wall_clock(
    growth_project_client: AsyncClient,
) -> None:
    response = await growth_project_client.post(
        "/api/research/growth-projects",
        json={
            "name": "Fixed Daily Time Project",
            "primary_goal": "mixed_research",
            "platforms": ["xhs"],
            "keywords": ["fixed daily time"],
            "collection_depth": "standard",
            "refresh_cadence": "daily",
            "refresh_time_utc8": "09:30",
            "auto_ai_analysis": False,
            "start_immediately": False,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["job"]["comment_policy"]["refresh_time_utc8"] == "09:30"
    next_run_at = _parse_datetime(payload["job"]["next_run_at"])
    local_next_run_at = next_run_at.astimezone(UTC8)
    assert next_run_at > datetime.now(timezone.utc)
    assert (local_next_run_at.hour, local_next_run_at.minute, local_next_run_at.second) == (9, 30, 0)

    detail_response = await growth_project_client.get(
        f"/api/research/growth-projects/{payload['project_id']}"
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["settings"]["refresh_cadence"] == "daily"
    assert detail["settings"]["refresh_time_utc8"] == "09:30"


@pytest.mark.asyncio
async def test_scheduled_growth_project_preserves_daily_refresh_time_after_run(
    growth_project_client: AsyncClient,
) -> None:
    response = await growth_project_client.post(
        "/api/research/growth-projects",
        json={
            "name": "Preserve Fixed Daily Time Project",
            "primary_goal": "mixed_research",
            "platforms": ["xhs"],
            "keywords": ["preserve fixed time"],
            "collection_depth": "standard",
            "refresh_cadence": "daily",
            "refresh_time_utc8": "07:45",
            "auto_ai_analysis": False,
            "start_immediately": False,
        },
    )
    assert response.status_code == 200, response.text
    created = response.json()

    repository = ResearchRepository()
    scheduler = ResearchScheduler(repository)
    job_id = int(created["job"]["id"])
    await repository.update_job(
        job_id,
        {
            "status": "completed",
            "next_run_at": datetime.now(timezone.utc) - timedelta(minutes=2),
        },
    )

    await scheduler.schedule_job(job_id)
    job = await repository.get_job(job_id)

    assert job is not None
    assert job["comment_policy"]["refresh_time_utc8"] == "07:45"
    assert job["next_run_at"] is not None
    local_next_run_at = _as_utc(job["next_run_at"]).astimezone(UTC8)
    assert (local_next_run_at.hour, local_next_run_at.minute, local_next_run_at.second) == (7, 45, 0)


@pytest.mark.asyncio
async def test_update_growth_project_configuration_retags_jobs_and_syncs_plans(
    growth_project_client: AsyncClient,
) -> None:
    created = await _create_project(growth_project_client)
    project_id = created["project_id"]
    project_record_id = created["project_record_id"]

    response = await growth_project_client.patch(
        f"/api/research/growth-projects/{project_id}",
        json={
            "name": "Pet Growth Research",
            "primary_goal": "keyword_expansion",
            "platforms": ["xhs"],
            "comment_collection_enabled": False,
            "refresh_cadence": "daily",
            "daily_collection_limit_per_platform": 30,
            "keywords": [
                {
                    "keyword": "cat food review",
                    "keyword_type": "core",
                    "source": "manual",
                    "status": "active",
                },
                {
                    "keyword": "giveaway",
                    "keyword_type": "excluded",
                    "source": "manual",
                    "status": "excluded",
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == "pet_growth_research"
    assert payload["project"]["name"] == "Pet Growth Research"
    assert payload["project"]["primary_goal"] == "keyword_expansion"
    assert payload["project"]["platforms"] == ["xhs"]

    detail_response = await growth_project_client.get(
        "/api/research/growth-projects/pet_growth_research"
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["settings"]["comment_collection_enabled"] is False
    assert detail["settings"]["refresh_cadence"] == "daily"
    assert detail["settings"]["daily_collection_limit_per_platform"] == 30
    assert detail["project"]["job_ids"] == [created["job"]["id"]]
    assert detail["keywords"] == [
        {
            "keyword": "cat food review",
            "type": "core",
            "source": "manual",
            "status": "active",
        },
        {
            "keyword": "giveaway",
            "type": "excluded",
            "source": "manual",
            "status": "excluded",
        },
    ]

    plans_response = await growth_project_client.get(
        f"/api/research/growth-projects/{project_record_id}/collection-plans"
    )
    assert plans_response.status_code == 200, plans_response.text
    plans = {item["platform"]: item for item in plans_response.json()["collection_plans"]}
    assert plans["xhs"]["enabled"] is True
    assert plans["xhs"]["schedule_mode"] == "interval"
    assert plans["xhs"]["schedule_interval_minutes"] == 1440
    assert plans["dy"]["enabled"] is False
    assert plans["wb"]["enabled"] is False


@pytest.mark.asyncio
async def test_update_growth_project_configuration_requires_active_keyword(
    growth_project_client: AsyncClient,
) -> None:
    created = await _create_project(growth_project_client)

    response = await growth_project_client.patch(
        f"/api/research/growth-projects/{created['project_id']}",
        json={
            "keywords": [
                {
                    "keyword": "giveaway",
                    "keyword_type": "excluded",
                    "source": "manual",
                    "status": "excluded",
                }
            ]
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_growth_project_ai_keyword_suggestion_uses_gateway_and_filters_duplicates(
    growth_project_client: AsyncClient,
    monkeypatch,
) -> None:
    created = await _create_project(growth_project_client)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "test-key")
    monkeypatch.setenv("AI_GATEWAY_BASE_URL", "https://gateway.example.com/v1")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "gateway-test-model")
    monkeypatch.setenv("AI_GATEWAY_MAX_TOKENS", "1200")

    async def fake_complete_json(self, *, prompt: str, params: dict | None = None):
        assert "Pet Growth" in prompt
        assert "cat food" in prompt
        assert params is not None
        assert params["max_tokens"] == 1200
        return {
            "suggestions": [
                {
                    "keyword": "cat food",
                    "keyword_type": "core",
                    "reason": "duplicate existing keyword",
                    "confidence": 0.99,
                },
                {
                    "keyword": "kitten snacks",
                    "keyword_type": "primary",
                    "reason": "high-intent related demand",
                    "confidence": 0.88,
                },
                {
                    "keyword": "free giveaway",
                    "keyword_type": "negative",
                    "reason": "promotional noise",
                    "confidence": 0.91,
                },
                {
                    "keyword": "cat feeding schedule",
                    "keyword_type": "secondary",
                    "reason": "long-tail content angle",
                    "confidence": 0.73,
                },
            ]
        }

    monkeypatch.setattr(
        "research.growth_ai.OpenAICompatibleProvider.complete_json",
        fake_complete_json,
    )

    response = await growth_project_client.post(
        f"/api/research/growth-projects/{created['project_id']}/keywords/ai-suggest",
        json={
            "input_text": "Find more pet-food research keywords for Xiaohongshu and Douyin",
            "count": 12,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["provider"] == {
        "name": "AI Gateway",
        "model": "gateway-test-model",
    }
    assert payload["context"]["project_id"] == created["project_id"]
    assert payload["context"]["requested_count"] == 12
    assert payload["context"]["existing_keyword_count"] == 2
    assert payload["suggestions"] == [
        {
            "keyword": "kitten snacks",
            "keyword_type": "core",
            "reason": "high-intent related demand",
            "confidence": 0.88,
            "source": "ai",
            "raw": {
                "keyword": "kitten snacks",
                "keyword_type": "primary",
                "reason": "high-intent related demand",
                "confidence": 0.88,
            },
        },
        {
            "keyword": "free giveaway",
            "keyword_type": "excluded",
            "reason": "promotional noise",
            "confidence": 0.91,
            "source": "ai",
            "raw": {
                "keyword": "free giveaway",
                "keyword_type": "negative",
                "reason": "promotional noise",
                "confidence": 0.91,
            },
        },
        {
            "keyword": "cat feeding schedule",
            "keyword_type": "expanded",
            "reason": "long-tail content angle",
            "confidence": 0.73,
            "source": "ai",
            "raw": {
                "keyword": "cat feeding schedule",
                "keyword_type": "secondary",
                "reason": "long-tail content angle",
                "confidence": 0.73,
            },
        },
    ]

    detail_response = await growth_project_client.get(
        f"/api/research/growth-projects/{created['project_id']}"
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert [item["keyword"] for item in detail["keywords"]] == ["cat food", "kitten food"]


@pytest.mark.asyncio
async def test_new_growth_project_ignores_historical_jobs_with_same_project_slug(
    growth_project_client: AsyncClient,
) -> None:
    legacy_job_response = await growth_project_client.post(
        "/api/research/jobs",
        json={
            "name": "Legacy Pet Growth collection",
            "topic": "pet_growth",
            "platforms": ["xhs"],
            "collection_mode": "search",
            "keywords": ["legacy pet growth"],
            "start_date": "2026-05-01",
            "end_date": "2026-05-24",
            "comment_policy": {
                "enable_comments": True,
                "enable_sub_comments": False,
            },
        },
    )
    assert legacy_job_response.status_code == 200, legacy_job_response.text
    legacy_job = legacy_job_response.json()

    created = await _create_project(growth_project_client)

    detail_response = await growth_project_client.get(
        f"/api/research/growth-projects/{created['project_id']}"
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["project"]["job_ids"] == [created["job"]["id"]]
    assert [item["id"] for item in detail["collection_records"]] == [created["job"]["id"]]
    assert detail["project"]["job_ids"] != [legacy_job["id"], created["job"]["id"]]

    list_response = await growth_project_client.get("/api/research/growth-projects")
    assert list_response.status_code == 200, list_response.text
    project = next(
        item
        for item in list_response.json()["projects"]
        if item["id"] == created["project_id"]
    )
    assert project["metrics"]["jobs"] == 1
    assert project["job_ids"] == [created["job"]["id"]]


@pytest.mark.asyncio
async def test_growth_project_progress_prefers_latest_task_when_idle(
    growth_project_client: AsyncClient,
) -> None:
    first_job_response = await growth_project_client.post(
        "/api/research/jobs",
        json={
            "name": "History Probe - first",
            "topic": "history_probe_project",
            "platforms": ["xhs"],
            "collection_mode": "search",
            "keywords": ["history probe"],
            "start_date": "2026-05-01",
            "end_date": "2026-05-24",
            "comment_policy": {
                "enable_comments": True,
                "enable_sub_comments": False,
            },
        },
    )
    assert first_job_response.status_code == 200, first_job_response.text
    first_job = first_job_response.json()

    second_job_response = await growth_project_client.post(
        "/api/research/jobs",
        json={
            "name": "History Probe - second",
            "topic": "history_probe_project",
            "platforms": ["xhs"],
            "collection_mode": "search",
            "keywords": ["history probe"],
            "start_date": "2026-05-10",
            "end_date": "2026-05-24",
            "comment_policy": {
                "enable_comments": True,
                "enable_sub_comments": False,
            },
        },
    )
    assert second_job_response.status_code == 200, second_job_response.text
    second_job = second_job_response.json()

    progress_response = await growth_project_client.get(
        "/api/research/growth-projects/history_probe_project/collection/progress"
    )
    assert progress_response.status_code == 200, progress_response.text
    payload = progress_response.json()
    assert payload["current_job_id"] == second_job["id"]
    assert payload["current_job_id"] != first_job["id"]


@pytest.mark.asyncio
async def test_growth_project_progress_reports_automation_status(
    growth_project_client: AsyncClient,
) -> None:
    response = await growth_project_client.post(
        "/api/research/growth-projects",
        json={
            "name": "Automation Status Project",
            "primary_goal": "mixed_research",
            "platforms": ["xhs"],
            "keywords": ["automation status"],
            "collection_depth": "standard",
            "auto_ai_analysis": False,
            "start_immediately": False,
        },
    )
    assert response.status_code == 200, response.text
    created = response.json()

    progress_response = await growth_project_client.get(
        f"/api/research/growth-projects/{created['project_id']}/collection/progress"
    )
    assert progress_response.status_code == 200, progress_response.text
    payload = progress_response.json()
    automation = payload["automation"]
    assert automation["enabled"] is True
    assert automation["interval_minutes"] == 1440
    assert automation["job_id"] == created["job"]["id"]
    assert automation["next_run_at"] is not None
    assert "daemon" in automation


@pytest.mark.asyncio
async def test_research_automation_daemon_enqueues_due_scheduled_job(
    growth_project_client: AsyncClient,
) -> None:
    response = await growth_project_client.post(
        "/api/research/growth-projects",
        json={
            "name": "Due Automation Project",
            "primary_goal": "mixed_research",
            "platforms": ["xhs"],
            "keywords": ["due automation"],
            "collection_depth": "standard",
            "auto_ai_analysis": False,
            "start_immediately": False,
        },
    )
    assert response.status_code == 200, response.text
    created = response.json()
    repository = ResearchRepository()
    job_id = int(created["job"]["id"])
    await repository.update_job(
        job_id,
        {
            "status": "completed",
            "next_run_at": datetime.now(timezone.utc) - timedelta(minutes=2),
        },
    )

    enqueued: list[dict[str, int | str | None]] = []

    async def fake_enqueue(scheduled_job_id: int, project_id: str | None, org_id: int | None) -> dict:
        job = await repository.get_job(scheduled_job_id)
        payload = {
            "job_id": scheduled_job_id,
            "project_id": project_id or (job.get("topic") if job else None),
            "org_id": org_id,
            "queue_position": len(enqueued) + 1,
        }
        enqueued.append(payload)
        return payload

    daemon = ResearchAutomationDaemon(
        repository=repository,
        enqueue_job=fake_enqueue,
        interval_seconds=5,
    )
    result = await daemon.run_once()

    assert result["due_job_ids"] == [job_id]
    assert [item["job_id"] for item in result["enqueued"]] == [job_id]
    assert [item["job_id"] for item in daemon.last_enqueued_jobs] == [job_id]
    assert enqueued[0]["org_id"] == int(created["job"]["org_id"])


@pytest.mark.asyncio
async def test_collection_queue_resolves_org_for_scheduled_job_without_request_context(
    growth_project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.routers import research as research_router

    response = await growth_project_client.post(
        "/api/research/growth-projects",
        json={
            "name": "Queued Tenant Project",
            "primary_goal": "mixed_research",
            "platforms": ["xhs"],
            "keywords": ["queued tenant"],
            "collection_depth": "standard",
            "auto_ai_analysis": False,
            "start_immediately": False,
        },
    )
    assert response.status_code == 200, response.text
    created = response.json()
    job_id = int(created["job"]["id"])
    org_id = int(created["job"]["org_id"])

    async def noop_queue_worker() -> None:
        return None

    monkeypatch.setattr(research_router, "_run_research_execution_queue", noop_queue_worker)
    research_router._research_execution_queue.clear()
    research_router._research_queue_worker_task = None

    try:
        queue = await research_router.enqueue_research_collection_job(
            job_id,
            project_id=created["project_id"],
        )
        await asyncio.sleep(0)

        assert queue["org_id"] == org_id
        assert queue["queue"]["queued_jobs"][0]["org_id"] == org_id
        queued_job = await ResearchRepository(org_id=org_id).get_job(job_id)
        assert queued_job is not None
        assert queued_job["status"] == "queued"
    finally:
        research_router._research_execution_queue.clear()
        research_router._research_queue_worker_task = None


@pytest.mark.asyncio
async def test_scheduled_job_schedule_outputs_stay_in_project_org(
    growth_project_client: AsyncClient,
) -> None:
    response = await growth_project_client.post(
        "/api/research/growth-projects",
        json={
            "name": "Scheduled Tenant Project",
            "primary_goal": "mixed_research",
            "platforms": ["xhs"],
            "keywords": ["scheduled tenant"],
            "collection_depth": "standard",
            "auto_ai_analysis": False,
            "start_immediately": False,
        },
    )
    assert response.status_code == 200, response.text
    created = response.json()
    job_id = int(created["job"]["id"])
    org_id = int(created["job"]["org_id"])

    repository = ResearchRepository(org_id=org_id)
    scheduler = ResearchScheduler(repository)
    schedule = await scheduler.schedule_job(job_id, force=True)

    assert schedule["created"] == 1
    units = await repository.list_crawl_units(job_id)
    events = await repository.list_events(job_id)
    assert len(units) == 1
    assert {unit["org_id"] for unit in units} == {org_id}
    scheduled_events = [event for event in events if event["event_type"] == "crawl_units_scheduled"]
    assert scheduled_events
    assert {event["org_id"] for event in scheduled_events} == {org_id}


@pytest.mark.asyncio
async def test_create_raw_record_is_idempotent_for_same_payload(
    growth_project_client: AsyncClient,
) -> None:
    repository = ResearchRepository.global_scope()
    job = await repository.create_job(
        {
            "name": "Raw Record Idempotent Job",
            "topic": "raw_record_idempotent_job",
            "platforms": ["dy"],
            "collection_mode": "search",
            "keywords": ["高考志愿填报"],
            "target_ids": [],
            "creator_ids": [],
            "start_date": date.today() - timedelta(days=1),
            "end_date": date.today(),
            "status": "running",
            "comment_policy": {"enable_comments": True, "enable_sub_comments": False},
            "raw_record_mode": "full",
            "anonymize_authors": True,
        }
    )
    payload = {"aweme_id": "7643426948693518820", "title": "高考十大关键节点早知道"}

    first = await repository.create_raw_record(
        job_id=int(job["id"]),
        platform="dy",
        source_type="post",
        source_id="7643426948693518820",
        source_url=None,
        payload=payload,
    )
    second = await repository.create_raw_record(
        job_id=int(job["id"]),
        platform="dy",
        source_type="post",
        source_id="7643426948693518820",
        source_url=None,
        payload=payload,
    )

    assert first["id"] == second["id"]
    async with get_session() as session:
        count = await session.scalar(
            select(func.count()).select_from(RawRecord).where(RawRecord.job_id == int(job["id"]))
        )
    assert count == 1


@pytest.mark.asyncio
async def test_create_growth_project_claims_legacy_global_project_with_same_name(
    growth_project_client: AsyncClient,
) -> None:
    global_repo = ResearchRepository.global_scope()
    legacy = await global_repo.create_growth_project(
        {
            "name": "2026 Summer 教育项目",
            "primary_goal": "mixed_research",
            "platforms": ["xhs", "dy"],
            "collection_status": "not_started",
            "sample_status": "sample_insufficient",
            "recommended_action": "start_collection",
            "archived": True,
        }
    )
    await global_repo.create_growth_project_keyword(
        {
            "project_id": legacy["id"],
            "keyword": "教育培训",
            "keyword_type": "core",
            "source": "manual",
            "status": "active",
        }
    )
    await global_repo.create_growth_project_collection_plan(
        {
            "project_id": legacy["id"],
            "platform": "xhs",
            "collection_mode": "search",
            "keyword_scope": "active",
            "enabled": True,
            "schedule_mode": "interval",
            "schedule_interval_minutes": 1440,
        }
    )

    create_response = await growth_project_client.post(
        "/api/research/growth-projects",
        json={
            "name": "2026 Summer 教育项目",
            "primary_goal": "mixed_research",
            "platforms": ["xhs", "dy"],
            "keywords": ["教育培训", "升学规划"],
            "collection_depth": "standard",
            "refresh_cadence": "daily",
            "auto_ai_analysis": False,
            "start_immediately": False,
        },
    )
    assert create_response.status_code == 200, create_response.text
    payload = create_response.json()
    assert payload["project_record_id"] == legacy["id"]

    list_response = await growth_project_client.get("/api/research/growth-projects")
    assert list_response.status_code == 200, list_response.text
    assert any(
        project["id"] == payload["project_id"]
        for project in list_response.json()["projects"]
    )

    async with get_session() as session:
        project = (
            await session.execute(
                select(ResearchGrowthProject).where(ResearchGrowthProject.id == legacy["id"])
            )
        ).scalar_one()
        assert project.org_id is not None
        assert bool(project.archived) is False
        keyword_org_ids = (
            await session.execute(
                select(ResearchGrowthProjectKeyword.org_id).where(
                    ResearchGrowthProjectKeyword.project_id == legacy["id"]
                )
            )
        ).scalars().all()
        assert keyword_org_ids
        assert all(org_id == project.org_id for org_id in keyword_org_ids)
        plan_org_ids = (
            await session.execute(
                select(ResearchGrowthProjectCollectionPlan.org_id).where(
                    ResearchGrowthProjectCollectionPlan.project_id == legacy["id"]
                )
            )
        ).scalars().all()
        assert plan_org_ids
        assert all(org_id == project.org_id for org_id in plan_org_ids)


@pytest.mark.asyncio
async def test_archive_aggregated_job_project_hides_it_from_project_list(
    growth_project_client: AsyncClient,
) -> None:
    job_response = await growth_project_client.post(
        "/api/research/jobs",
        json={
            "name": "Historical Backfill K12 Competitors collection",
            "topic": "historical_backfill_k12_competitors",
            "platforms": ["xhs"],
            "collection_mode": "search",
            "keywords": ["K12 competitors"],
            "start_date": "2026-05-01",
            "end_date": "2026-05-24",
            "comment_policy": {
                "enable_comments": True,
                "enable_sub_comments": False,
            },
        },
    )
    assert job_response.status_code == 200, job_response.text

    list_response = await growth_project_client.get("/api/research/growth-projects")
    assert list_response.status_code == 200, list_response.text
    assert any(
        project["id"] == "historical_backfill_k12_competitors"
        for project in list_response.json()["projects"]
    )

    archive_response = await growth_project_client.post(
        "/api/research/growth-projects/historical_backfill_k12_competitors/archive"
    )
    assert archive_response.status_code == 200, archive_response.text
    assert archive_response.json()["status"] == "archived"
    assert archive_response.json()["project"]["archived"] is True

    after_response = await growth_project_client.get("/api/research/growth-projects")
    assert after_response.status_code == 200, after_response.text
    assert all(
        project["id"] != "historical_backfill_k12_competitors"
        for project in after_response.json()["projects"]
    )


@pytest.mark.asyncio
async def test_archive_slugged_aggregated_project_with_non_slug_topic(
    growth_project_client: AsyncClient,
) -> None:
    job_response = await growth_project_client.post(
        "/api/research/jobs",
        json={
            "name": "学而思 - fetch now",
            "topic": "competitor_public_flow_now:1:2026-05-24",
            "platforms": ["xhs"],
            "collection_mode": "search",
            "keywords": ["学而思"],
            "start_date": "2026-05-24",
            "end_date": "2026-05-24",
            "comment_policy": {
                "enable_comments": True,
                "enable_sub_comments": False,
            },
        },
    )
    assert job_response.status_code == 200, job_response.text

    target = "competitor_public_flow_now_1_2026_05_24"

    detail_response = await growth_project_client.get(
        f"/api/research/growth-projects/{target}"
    )
    assert detail_response.status_code == 200, detail_response.text
    assert detail_response.json()["project"]["id"] == target

    archive_response = await growth_project_client.post(
        f"/api/research/growth-projects/{target}/archive"
    )
    assert archive_response.status_code == 200, archive_response.text
    assert archive_response.json()["status"] == "archived"

    after_response = await growth_project_client.get("/api/research/growth-projects")
    assert after_response.status_code == 200, after_response.text
    assert all(
        project["id"] != target for project in after_response.json()["projects"]
    )


@pytest.mark.asyncio
async def test_get_growth_project_claims_legacy_project_into_current_org(
    growth_project_client: AsyncClient,
) -> None:
    legacy = await _seed_legacy_growth_project_with_job()

    detail_response = await growth_project_client.get(
        f"/api/research/growth-projects/{legacy['project_slug']}"
    )

    assert detail_response.status_code == 200, detail_response.text
    payload = detail_response.json()
    assert payload["project"]["name"] == "Legacy Pet Growth"
    assert payload["project"]["job_ids"] == [legacy["job_id"]]

    async with get_session() as session:
        project = await session.get(ResearchGrowthProject, legacy["project_record_id"])
        keyword = await session.get(ResearchGrowthProjectKeyword, legacy["keyword_id"])
        plan = await session.get(ResearchGrowthProjectCollectionPlan, legacy["plan_id"])
        job = await session.get(ResearchJob, legacy["job_id"])
        post = await session.get(ResearchPost, legacy["post_id"])

        assert project is not None
        assert keyword is not None
        assert plan is not None
        assert job is not None
        assert post is not None
        claimed_org_ids = {
            project.org_id,
            keyword.org_id,
            plan.org_id,
            job.org_id,
            post.org_id,
        }
        assert None not in claimed_org_ids
        assert len(claimed_org_ids) == 1
