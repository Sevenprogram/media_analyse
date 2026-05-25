from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import config
from config.db_config import sqlite_db_config
from database.db_session import close_engines, create_tables, get_session
from saas_test_utils import authenticate_test_client
from research.models import ResearchJob, ResearchPost
from research.repository import ResearchRepository
from research.crawl_units import build_crawl_units_for_job
from research.enums import CRAWL_UNIT_PENDING, CRAWL_UNIT_RUNNING, CRAWL_UNIT_SUCCEEDED


@pytest_asyncio.fixture
async def collection_client(tmp_path, monkeypatch):
    db_path = tmp_path / "collection-runs-test.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))

    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await authenticate_test_client(
            client,
            email="collection-runs@example.com",
            organization_name="Collection Runs Workspace",
        )
        client.headers.update({"X-Org-Id": str(auth["organization"]["id"])})
        await _seed_tracking_posts(org_id=int(auth["organization"]["id"]))
        yield client

    await close_engines()


async def _seed_tracking_posts(*, org_id: int) -> None:
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        job = ResearchJob(
            org_id=org_id,
            name="collection api seed",
            topic="collection_api_seed",
            platforms=["xhs", "dy"],
            collection_mode="search",
            keywords=["cat food review", "new cat owner"],
            target_ids=[],
            creator_ids=[],
            start_date=date.today() - timedelta(days=7),
            end_date=date.today(),
            status="completed",
            comment_policy={"enable_comments": False, "enable_sub_comments": False},
            raw_record_mode="minimal",
            anonymize_authors=True,
        )
        session.add(job)
        await session.flush()
        session.add_all(
            [
                ResearchPost(
                    org_id=org_id,
                    job_id=job.id,
                    platform="xhs",
                    platform_post_id="collection-seed-1",
                    author_hash="collection-author-1",
                    title="new cat owner cat food review",
                    content="cat food review for new cat owners",
                    url="https://example.com/xhs/seed1",
                    publish_time=now - timedelta(days=1),
                    engagement_json={"like_count": 90, "comment_count": 8},
                ),
                ResearchPost(
                    org_id=org_id,
                    job_id=job.id,
                    platform="dy",
                    platform_post_id="collection-seed-2",
                    author_hash="collection-author-2",
                    title="cat food review avoid mistakes",
                    content="avoid mistakes when picking cat food",
                    url="https://example.com/dy/seed2",
                    publish_time=now - timedelta(days=2),
                    engagement_json={"like_count": 66, "comment_count": 5},
                ),
            ]
        )


async def _wait_for_collection_run(
    client: AsyncClient,
    url: str,
    *,
    attempts: int = 40,
) -> dict:
    for _ in range(attempts):
        response = await client.get(url)
        assert response.status_code == 200
        payload = response.json()
        if payload["run"]["status"] in {"succeeded", "failed"}:
            return payload
        await asyncio.sleep(0.05)
    raise AssertionError("collection run did not finish in time")


@pytest.mark.asyncio
async def test_bulk_crawl_unit_running_status_preserves_scheduled_at(
    collection_client: AsyncClient,
) -> None:
    repository = ResearchRepository(org_id=int(collection_client.headers["X-Org-Id"]))
    job = await repository.create_job(
        {
            "name": "crawl unit scheduled_at regression",
            "topic": "crawl_unit_regression",
            "platforms": ["xhs"],
            "collection_mode": "search",
            "keywords": ["scheduled at keyword"],
            "target_ids": [],
            "creator_ids": [],
            "start_date": date.today() - timedelta(days=7),
            "end_date": date.today(),
            "status": "pending",
            "comment_policy": {"enable_comments": False, "enable_sub_comments": False},
            "raw_record_mode": "minimal",
            "anonymize_authors": True,
        }
    )
    units = build_crawl_units_for_job(job, run_key="regression-run")
    await repository.create_crawl_units(units)

    updated = await repository.bulk_update_crawl_unit_status(
        job_id=job["id"],
        platform="xhs",
        status=CRAWL_UNIT_RUNNING,
        from_statuses=(CRAWL_UNIT_PENDING,),
    )

    assert updated == 1
    crawl_units = await repository.list_crawl_units(job["id"])
    assert crawl_units[0]["status"] == CRAWL_UNIT_RUNNING
    assert crawl_units[0]["scheduled_at"] is not None

    completed = await repository.bulk_update_crawl_unit_status(
        job_id=job["id"],
        platform="xhs",
        status=CRAWL_UNIT_SUCCEEDED,
        from_statuses=(CRAWL_UNIT_RUNNING,),
    )
    assert completed == 1
    crawl_units = await repository.list_crawl_units(job["id"])
    assert crawl_units[0]["status"] == CRAWL_UNIT_SUCCEEDED
    assert crawl_units[0]["scheduled_at"] is not None


@pytest.mark.asyncio
async def test_content_tracker_collect_and_analyze_lifecycle(
    collection_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.routers import content_tracking as content_tracking_router

    async def fake_execute_tracker_collection_job(job_id: int) -> dict:
        now = datetime.now(timezone.utc)
        async with get_session() as session:
            job = await session.get(ResearchJob, job_id)
            assert job is not None
            assert job.keywords == ["editable cat keyword", "cat food review"]
            session.add(
                ResearchPost(
                    org_id=job.org_id,
                    job_id=job_id,
                    platform="xhs",
                    platform_post_id=f"collected-{job_id}",
                    author_hash="collected-author",
                    title="cat food review updated shortlist",
                    content="fresh collected cat food review",
                    url=f"https://example.com/xhs/{job_id}",
                    publish_time=now,
                    engagement_json={"like_count": 120, "comment_count": 12},
                )
            )
        repository = ResearchRepository()
        job = await repository.update_job(job_id, {"status": "completed"})
        return {"execution": {"status": "completed", "job_id": job_id}, "job": job}

    monkeypatch.setattr(
        content_tracking_router,
        "_execute_tracker_collection_job",
        fake_execute_tracker_collection_job,
    )

    create_response = await collection_client.post(
        "/api/content-tracking/trackers",
        json={
            "name": "collection tracker",
            "platforms": ["xhs", "dy"],
            "included_keywords": ["cat food review", "new cat owner"],
            "excluded_keywords": ["giveaway"],
            "enabled": True,
        },
    )
    assert create_response.status_code == 200
    tracker = create_response.json()

    collect_response = await collection_client.post(
        f"/api/content-tracking/trackers/{tracker['id']}/collect-and-analyze",
        json={
            "lookback_days": 7,
            "limit_per_platform": 30,
            "keywords": ["editable cat keyword", "cat food review"],
            "trigger_source": "manual",
        },
    )
    assert collect_response.status_code == 200
    created_run = collect_response.json()["run"]
    run_id = created_run["id"]
    assert created_run["summary"]["latest_log"] == "任务已创建，等待开始采集"

    finished = await _wait_for_collection_run(
        collection_client,
        f"/api/content-tracking/collection-runs/{run_id}",
    )
    assert finished["run"]["status"] == "succeeded"
    assert finished["run"]["mode"] == "collect_and_analyze"
    assert finished["run"]["analysis_run_id"] is not None
    assert finished["run"]["summary"]["collected_post_count"] >= 1
    assert finished["run"]["summary"]["latest_stage"] == "completed"
    assert "分析已更新" in finished["run"]["summary"]["latest_log"]

    latest_analysis = await collection_client.get(
        f"/api/content-tracking/trackers/{tracker['id']}/analysis"
    )
    assert latest_analysis.status_code == 200
    latest_payload = latest_analysis.json()
    assert latest_payload["run"]["id"] == finished["run"]["analysis_run_id"]
    assert latest_payload["tracker"]["latest_analysis_run_id"] == finished["run"]["analysis_run_id"]
    assert (
        latest_payload["tracker"]["latest_analysis_snapshot_id"]
        == latest_payload["snapshot"]["id"]
    )


@pytest.mark.asyncio
async def test_content_tracker_collection_runs_return_latest_first(
    collection_client: AsyncClient,
) -> None:
    repository = ResearchRepository(org_id=int(collection_client.headers["X-Org-Id"]))
    create_response = await collection_client.post(
        "/api/content-tracking/trackers",
        json={
            "name": "collection run history tracker",
            "platforms": ["xhs"],
            "included_keywords": ["cat food review"],
            "enabled": True,
        },
    )
    assert create_response.status_code == 200
    tracker = create_response.json()

    await repository.create_collection_run(
        {
            "run_type": "content_tracker",
            "target_type": "content_tracker",
            "target_id": tracker["id"],
            "mode": "collect_and_analyze",
            "trigger_source": "manual",
            "status": "succeeded",
            "phase": "completed",
            "completed_at": datetime.now(timezone.utc) - timedelta(hours=1),
            "summary": {"latest_log": "older completed run"},
        }
    )
    await repository.create_collection_run(
        {
            "run_type": "content_tracker",
            "target_type": "content_tracker",
            "target_id": tracker["id"],
            "mode": "collect_and_analyze",
            "trigger_source": "manual",
            "status": "running",
            "phase": "collecting",
            "started_at": datetime.now(timezone.utc) - timedelta(minutes=2),
            "summary": {"latest_log": "latest running run"},
        }
    )

    response = await collection_client.get(
        f"/api/content-tracking/trackers/{tracker['id']}/collection-runs?limit=1"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tracker"]["id"] == tracker["id"]
    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["status"] == "running"
    assert payload["runs"][0]["summary"]["latest_log"] == "latest running run"


def test_content_tracker_collection_event_log_formats_heartbeat() -> None:
    from api.routers import content_tracking as content_tracking_router

    message = content_tracking_router._format_collection_event_log(
        {
            "event_type": "crawler_heartbeat",
            "platform": "xhs",
            "message": "xhs still running",
            "stats_json": {
                "elapsed_seconds": 18,
                "latest_log": "page 1 fetched",
                "sample_counts": {
                    "posts": 3,
                    "comments": 0,
                    "raw_records": 5,
                },
            },
        }
    )

    assert message == "正在采集小红书，已运行 18 秒，已入库 3 条内容，最新输出：page 1 fetched"


@pytest.mark.asyncio
async def test_competitor_collect_and_refresh_lifecycle(
    collection_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.routers import competitors as competitors_router

    async def fake_run_fetch_now_inline(
        competitor_id: int,
        request,
        progress=None,
        *,
        refresh_snapshot: bool = True,
    ) -> dict:
        repository = ResearchRepository()
        competitor = await repository.get_competitor_account(competitor_id)
        job = await repository.create_job(
            {
                "name": f"competitor collect - {competitor_id}",
                "topic": f"competitor:{competitor_id}",
                "platforms": [competitor["platform"]],
                "collection_mode": "creator",
                "keywords": [],
                "target_ids": [],
                "creator_ids": [competitor["creator_id"]],
                "start_date": date.today() - timedelta(days=request.days_back - 1),
                "end_date": date.today(),
                "status": "completed",
                "comment_policy": {"enable_comments": False, "enable_sub_comments": False},
                "raw_record_mode": "minimal",
                "anonymize_authors": True,
            }
        )
        snapshot = None
        if refresh_snapshot:
            snapshot = {"id": 99, "competitor_id": competitor_id}
        return {
            "competitor": competitor,
            "job": job,
            "schedule": {"job_id": job["id"], "created": 1},
            "worker": {"status": "succeeded"},
            "snapshot": snapshot,
            "xhs_token_backfill": {
                "platform": "xhs",
                "attempted": 3,
                "updated": 2,
                "failed": 1,
                "skipped": 0,
            },
            "worker_hint": None,
        }

    monkeypatch.setattr(
        competitors_router,
        "_run_fetch_now_inline",
        fake_run_fetch_now_inline,
    )

    create_response = await collection_client.post(
        "/api/competitors",
        json={
            "platform": "xhs",
            "creator_id": "creator-001",
            "display_name": "Competitor One",
            "enabled": True,
        },
    )
    assert create_response.status_code == 200
    competitor = create_response.json()

    collect_response = await collection_client.post(
        f"/api/competitors/{competitor['id']}/collect-and-refresh",
        json={
            "latest_limit": 20,
            "days_back": 7,
            "trigger_source": "manual",
            "execute_now": True,
            "headless": True,
        },
    )
    assert collect_response.status_code == 200
    run_id = collect_response.json()["run"]["id"]

    finished = await _wait_for_collection_run(
        collection_client,
        f"/api/competitors/collection-runs/{run_id}",
    )
    assert finished["run"]["status"] == "succeeded"
    assert finished["run"]["mode"] == "collect_and_refresh"
    assert finished["run"]["summary"]["job_id"] is not None
    assert finished["run"]["summary"]["refreshed_snapshot"] is True
    assert finished["run"]["summary"]["xhs_token_backfill"]["updated"] == 2


@pytest.mark.asyncio
async def test_competitor_monitor_settings_include_last_refresh_time(
    collection_client: AsyncClient,
) -> None:
    repository = ResearchRepository(org_id=int(collection_client.headers["X-Org-Id"]))

    create_response = await collection_client.post(
        "/api/competitors",
        json={
            "platform": "xhs",
            "creator_id": "creator-002",
            "display_name": "Competitor Two",
            "enabled": True,
        },
    )
    assert create_response.status_code == 200
    competitor = create_response.json()

    earlier_completed_at = datetime.now(timezone.utc) - timedelta(hours=3)
    latest_started_at = datetime.now(timezone.utc) - timedelta(minutes=20)

    await repository.create_collection_run(
        {
            "run_type": "competitor_monitor",
            "target_type": "competitor",
            "target_id": competitor["id"],
            "mode": "collect_and_refresh",
            "trigger_source": "manual",
            "status": "succeeded",
            "phase": "completed",
            "completed_at": earlier_completed_at,
        }
    )
    await repository.create_collection_run(
        {
            "run_type": "competitor_monitor",
            "target_type": "competitor",
            "target_id": competitor["id"],
            "mode": "collect_and_refresh",
            "trigger_source": "manual",
            "status": "running",
            "phase": "collecting",
            "started_at": latest_started_at,
        }
    )

    response = await collection_client.get(f"/api/competitors/{competitor['id']}/monitor-settings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["last_refresh_status"] == "running"
    assert payload["last_refresh_at"] is not None
    assert payload["last_refresh_at"].startswith(latest_started_at.strftime("%Y-%m-%dT%H:%M"))
    assert payload["last_refresh_at"].endswith("Z")
