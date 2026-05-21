import asyncio
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

import config
from api.main import app
import api.routers.competitors as competitors_router
from research.competitor_public_flow import (
    build_competitor_public_flow_snapshot,
    create_competitor_monitor_jobs,
)


def test_public_flow_snapshot_dedupes_latest_posts_and_calculates_delta():
    snapshot = build_competitor_public_flow_snapshot(
        competitor={"id": 1, "platform": "xhs", "creator_id": "u1"},
        snapshot_date=date(2026, 5, 21),
        latest_limit=2,
        keywords=["K12"],
        previous_snapshots=[
            {
                "evidence": {
                    "public_flow": {
                        "posts_by_id": {
                            "p1": {"like": 100, "comment": 5, "share": 0, "collect": 0, "total_interaction": 105}
                        }
                    }
                }
            }
        ],
        posts=[
            {
                "platform_post_id": "p1",
                "title": "K12 planning",
                "engagement_json": {"liked_count": 130, "comment_count": 10},
            },
            {
                "platform_post_id": "p1",
                "title": "K12 planning duplicated",
                "engagement_json": {"liked_count": 999},
            },
            {
                "platform_post_id": "p2",
                "title": "single mother K12",
                "engagement_json": {"liked_count": 20, "collected_count": 3},
            },
            {
                "platform_post_id": "p3",
                "title": "ignored by latest limit",
                "engagement_json": {"liked_count": 500},
            },
        ],
    )

    public_flow = snapshot["evidence"]["public_flow"]
    assert public_flow["deduped_post_count"] == 2
    assert set(public_flow["posts_by_id"]) == {"p1", "p2"}
    assert public_flow["cumulative"]["total_interaction"] == 163
    assert public_flow["delta_by_post"]["p1"]["total_interaction"] == 35
    assert public_flow["delta"]["total_interaction"] == 58
    assert snapshot["total_flow_count"] == 163


def test_public_flow_snapshot_handles_empty_posts():
    snapshot = build_competitor_public_flow_snapshot(
        competitor={"id": 1, "platform": "xhs", "creator_id": "u1"},
        snapshot_date=date(2026, 5, 21),
        latest_limit=50,
        keywords=["K12"],
        posts=[],
    )

    public_flow = snapshot["evidence"]["public_flow"]
    assert public_flow["deduped_post_count"] == 0
    assert public_flow["cumulative"]["total_interaction"] == 0
    assert public_flow["delta"]["total_interaction"] == 0
    assert snapshot["total_flow_count"] == 0


def test_public_flow_snapshot_evidence_is_json_serializable():
    snapshot = build_competitor_public_flow_snapshot(
        competitor={"id": 1, "platform": "xhs", "creator_id": "u1"},
        snapshot_date=date(2026, 5, 21),
        latest_limit=50,
        keywords=[],
        posts=[
            {
                "platform_post_id": "p1",
                "title": "K12",
                "publish_time": date(2026, 5, 21),
                "engagement_json": {"liked_count": 10},
            }
        ],
    )

    json.dumps(snapshot["evidence"], ensure_ascii=False)


def test_public_flow_detects_interaction_spike_keyword_shift_and_new_hot_post():
    snapshot = build_competitor_public_flow_snapshot(
        competitor={"id": 1, "platform": "xhs", "creator_id": "u1"},
        snapshot_date=date(2026, 5, 21),
        keywords=["K12", "math"],
        previous_snapshots=[
            {
                "keyword_distribution": {"K12": 1, "math": 3},
                "evidence": {
                    "public_flow": {
                        "delta": {"total_interaction": 50},
                        "posts_by_id": {
                            "p1": {"like": 10, "comment": 0, "share": 0, "collect": 0, "total_interaction": 10}
                        },
                    }
                },
            },
            {
                "keyword_distribution": {"K12": 0, "math": 2},
                "evidence": {"public_flow": {"delta": {"total_interaction": 60}}},
            },
        ],
        posts=[
            {
                "platform_post_id": "p1",
                "title": "K12 K12 enrollment",
                "content": "K12 family plan",
                "engagement_json": {"liked_count": 180, "comment_count": 10, "collected_count": 20},
            },
            {
                "platform_post_id": "p2",
                "title": "K12 homework",
                "engagement_json": {"liked_count": 20},
            },
        ],
    )

    anomaly_types = {item["type"] for item in snapshot["evidence"]["anomalies"]}
    assert {"interaction_spike", "keyword_shift", "new_hot_post"}.issubset(anomaly_types)


@pytest.mark.asyncio
async def test_create_competitor_monitor_jobs_creates_and_updates_by_topic():
    class FakeRepository:
        def __init__(self):
            self.created = []
            self.updated = []

        async def list_competitor_accounts(self, enabled_only=False):
            return [
                {"id": 1, "platform": "xhs", "creator_id": "u1", "display_name": "A"},
                {"id": 2, "platform": "dy", "creator_id": "u2", "display_name": "B"},
            ]

        async def list_jobs(self):
            return [{"id": 10, "topic": "competitor_public_flow:1"}]

        async def create_job(self, payload):
            self.created.append(payload)
            return {"id": 20, **payload}

        async def update_job(self, job_id, payload):
            self.updated.append((job_id, payload))
            return {"id": job_id, **payload}

    repository = FakeRepository()
    result = await create_competitor_monitor_jobs(repository, interval_minutes=480, latest_limit=50)

    assert result["created_or_updated"] == 2
    assert repository.updated[0][0] == 10
    assert repository.updated[0][1]["schedule_interval_minutes"] == 480
    assert repository.updated[0][1]["comment_policy"]["max_posts_per_job"] == 50
    assert repository.created[0]["topic"] == "competitor_public_flow:2"
    assert repository.created[0]["creator_ids"] == ["u2"]


def test_competitor_public_flow_rebuild_all_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_competitor_accounts(self, enabled_only=False):
            return [{"id": 1, "platform": "xhs", "creator_id": "u1", "display_name": "A"}]

        async def get_competitor_account(self, competitor_id):
            return {"id": competitor_id, "platform": "xhs", "creator_id": "u1", "display_name": "A"}

        async def list_posts_by_creator(self, *, platform, creator_id, limit=None):
            return [
                {
                    "platform_post_id": "p1",
                    "title": "K12",
                    "engagement_json": {"liked_count": 10},
                }
            ]

        async def list_entity_tags(self, **kwargs):
            return []

        async def list_scene_pack_keywords(self, enabled_only=False):
            return [{"keyword": "K12", "keyword_type": "primary", "platform": "xhs"}]

        async def list_competitor_composition_snapshots(self, **kwargs):
            return []

        async def upsert_competitor_composition_snapshot(self, payload):
            return {"id": 1, **payload}

    monkeypatch.setattr(competitors_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post("/api/competitors/public-flow/rebuild-all", json={"latest_limit": 50})

    assert response.status_code == 200
    body = response.json()
    assert body["rebuilt_count"] == 1
    assert body["snapshots"][0]["evidence"]["public_flow"]["deduped_post_count"] == 1


def test_competitor_recommendations_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_creator_candidates(self, **kwargs):
            return [
                {
                    "platform": "xhs",
                    "creator_id": "u1",
                    "match_score": 88,
                    "matched_tags": [{"tag": "K12"}],
                    "evidence": {"primary_hits": ["K12"], "representative_posts": [{"title": "K12体验课报名"}]},
                }
            ]

        async def get_creator_profile(self, platform, creator_id):
            return {
                "display_name": "K12课程官方",
                "profile_url": "https://example.com/u1",
                "follower_count": 30000,
                "recent_post_count_30d": 12,
            }

        async def list_competitor_accounts(self, enabled_only=False):
            return []

    monkeypatch.setattr(competitors_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/competitors/recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"][0]["creator_id"] == "u1"
    assert body["recommendations"][0]["create_payload"]["platform"] == "xhs"


def test_delete_competitor_soft_disables_account(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def update_competitor_account(self, competitor_id, payload):
            return {"id": competitor_id, "platform": "xhs", "creator_id": "u1", **payload}

    monkeypatch.setattr(competitors_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.delete("/api/competitors/1")

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert response.json()["competitor"]["enabled"] is False


def test_fetch_competitor_now_creates_job_schedules_and_rebuilds_snapshot(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        def __init__(self):
            self.job = None

        async def get_competitor_account(self, competitor_id):
            return {"id": competitor_id, "platform": "xhs", "creator_id": "u1", "display_name": "A"}

        async def create_job(self, payload):
            self.job = {"id": 9, **payload}
            return self.job

        async def get_job(self, job_id):
            return self.job

        async def has_active_crawl_units(self, job_id):
            return False

        async def create_crawl_units(self, units):
            return {"created": len(units), "existing": 0, "units": units}

        async def update_job(self, job_id, payload):
            return {"id": job_id, **payload}

        async def create_event(self, **payload):
            return payload

        async def list_posts_by_creator(self, *, platform, creator_id, limit=None):
            return []

        async def list_entity_tags(self, **kwargs):
            return []

        async def list_scene_pack_keywords(self, enabled_only=False):
            return []

        async def list_competitor_composition_snapshots(self, **kwargs):
            return []

        async def upsert_competitor_composition_snapshot(self, payload):
            return {"id": 1, **payload}

    monkeypatch.setattr(competitors_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post("/api/competitors/1/fetch-now", json={"latest_limit": 50, "days_back": 7, "execute_now": False})

    assert response.status_code == 200
    body = response.json()
    assert body["job"]["collection_mode"] == "creator"
    assert body["job"]["creator_ids"] == ["u1"]
    assert body["job"]["start_date"] < body["job"]["end_date"]
    assert body["schedule"]["created"] == 1
    assert body["worker"] is None
    assert body["snapshot"]["total_flow_count"] == 0


def test_fetch_competitor_now_executes_worker_when_requested(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        def __init__(self):
            self.job = None

        async def get_competitor_account(self, competitor_id):
            return {"id": competitor_id, "platform": "xhs", "creator_id": "u1", "display_name": "A"}

        async def create_job(self, payload):
            self.job = {"id": 9, **payload}
            return self.job

        async def get_job(self, job_id):
            return self.job

        async def has_active_crawl_units(self, job_id):
            return False

        async def create_crawl_units(self, units):
            return {"created": len(units), "existing": 0, "units": units}

        async def update_job(self, job_id, payload):
            return {"id": job_id, **payload}

        async def create_event(self, **payload):
            return payload

        async def list_posts_by_creator(self, *, platform, creator_id, limit=None):
            return []

        async def list_entity_tags(self, **kwargs):
            return []

        async def list_scene_pack_keywords(self, enabled_only=False):
            return []

        async def list_competitor_composition_snapshots(self, **kwargs):
            return []

        async def upsert_competitor_composition_snapshot(self, payload):
            return {"id": 1, **payload}

    async def fake_run_worker_once(*, worker_id, save_option, headless, job_id=None):
        return {"status": "succeeded", "worker_id": worker_id, "headless": headless, "job_id": job_id}

    monkeypatch.setattr(competitors_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(competitors_router, "run_worker_once", fake_run_worker_once)

    result = asyncio.run(
        competitors_router._run_fetch_now_inline(
            1,
            competitors_router.CompetitorFetchNowRequest(latest_limit=50, execute_now=True),
        )
    )

    assert result["worker"]["status"] == "succeeded"
    assert result["worker"]["worker_id"] == "fetch-now-competitor-1"
    assert result["worker"]["job_id"] == 9
    assert result["worker_hint"] is None


def test_fetch_competitor_now_route_returns_progress_task(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    async def fake_run_task(task_id, competitor_id, request):
        competitors_router._finish_fetch_task(task_id, {"snapshot": {"total_flow_count": 0}})

    monkeypatch.setattr(competitors_router, "_run_fetch_now_task", fake_run_task)
    client = TestClient(app)

    response = client.post("/api/competitors/1/fetch-now", json={"latest_limit": 50, "execute_now": True})

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"]
    assert body["status"] == "queued"


def test_get_fetch_now_task_returns_task_status():
    task = competitors_router._create_fetch_now_task(1)
    client = TestClient(app)

    response = client.get(f"/api/competitors/fetch-tasks/{task['task_id']}")

    assert response.status_code == 200
    assert response.json()["task_id"] == task["task_id"]
