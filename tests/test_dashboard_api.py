from fastapi.testclient import TestClient
import asyncio

import config
from api.main import app


def test_dashboard_summary_api_returns_payload(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_jobs(self):
            return [{"id": 1, "status": "running", "collection_mode": "search"}]

        async def list_creator_candidates(self, vertical_id=None, platform=None, pool_name=None):
            return [
                {
                    "platform": "xhs",
                    "creator_id": "a1",
                    "display_name": "K12妈妈号",
                    "match_score": 90,
                    "evidence": [{"text": "命中"}],
                }
            ]

        async def list_keyword_heat_snapshots(
            self,
            vertical_id=None,
            scene_pack_id=None,
            platform=None,
            limit=None,
        ):
            return [
                {
                    "keyword": "K12教育",
                    "platform": "xhs",
                    "heat_score": 85,
                    "growth_score": 20,
                    "platform_signal": "boosting",
                    "evidence": {"items": ["增长"]},
                }
            ]

        async def list_competitor_composition_snapshots(
            self,
            competitor_id=None,
            platform=None,
            limit=None,
        ):
            return [
                {
                    "competitor_id": 1,
                    "platform": "xhs",
                    "total_flow_count": 3000,
                    "hot_post_rate": 0.2,
                    "evidence": {"top_posts": [{"title": "爆款"}]},
                }
            ]

        async def list_content_tracking_snapshots(
            self,
            tracker_id=None,
            platform=None,
            limit=None,
        ):
            return [
                {
                    "tracker_id": 1,
                    "platform": "xhs",
                    "total_content_count": 12,
                    "hot_post_rate": 0.1,
                    "evidence": {"top_posts": [{"title": "同类"}]},
                }
            ]

        async def list_monitor_pools(self, enabled_only=False):
            return [{"id": 1, "name": "K12池"}]

    import api.routers.reports as reports_router

    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/reports/dashboard-summary?platform=xhs")

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["sample_status"] == "enough"
    assert body["monitoring"]["running_jobs"] == 1
    assert body["opportunities"][0]["reason"]


def test_dashboard_summary_degrades_when_repository_call_times_out(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_jobs(self):
            return [{"id": 1, "status": "running", "collection_mode": "search"}]

        async def list_creator_candidates(self, vertical_id=None, platform=None, pool_name=None):
            await asyncio.sleep(0.05)
            return [{"creator_id": "too-slow"}]

        async def list_keyword_heat_snapshots(
            self,
            vertical_id=None,
            scene_pack_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_competitor_composition_snapshots(
            self,
            competitor_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_content_tracking_snapshots(
            self,
            tracker_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_monitor_pools(self, enabled_only=False):
            return []

    import api.routers.reports as reports_router

    original_maybe_call = reports_router._maybe_call

    async def fast_timeout_call(repository, method_name, *args, default=None, **kwargs):
        return await original_maybe_call(
            repository,
            method_name,
            *args,
            default=default,
            timeout_seconds=0.001,
            **kwargs,
        )

    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(reports_router, "_maybe_call", fast_timeout_call)
    client = TestClient(app)

    response = client.get("/api/reports/dashboard-summary?platform=xhs")

    assert response.status_code == 200
    body = response.json()
    assert body["monitoring"]["running_jobs"] == 1
    assert body["decision"]["sample_status"] == "insufficient"


def test_dashboard_summary_falls_back_to_job_posts_when_snapshots_missing(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_jobs(self):
            return [
                {
                    "id": 9,
                    "status": "completed",
                    "collection_mode": "search",
                    "platforms": ["xhs"],
                }
            ]

        async def list_creator_candidates(self, vertical_id=None, platform=None, pool_name=None):
            return []

        async def list_keyword_heat_snapshots(
            self,
            vertical_id=None,
            scene_pack_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_competitor_composition_snapshots(
            self,
            competitor_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_content_tracking_snapshots(
            self,
            tracker_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_monitor_pools(self, enabled_only=False):
            return []

        async def list_posts(self, job_id, limit=None):
            return [
                {
                    "job_id": job_id,
                    "platform": "xhs",
                    "platform_post_id": "p1",
                    "title": "K12教育规划",
                    "publish_time": None,
                    "engagement_json": {"source_keyword": "K12教育", "like_count": 220, "comment_count": 18},
                },
                {
                    "job_id": job_id,
                    "platform": "xhs",
                    "platform_post_id": "p2",
                    "title": "单亲妈妈陪读",
                    "publish_time": None,
                    "engagement_json": {"source_keyword": "单亲妈妈", "like_count": 180, "comment_count": 12},
                },
            ]

        async def list_comments(self, job_id, limit=None):
            return []

    import api.routers.reports as reports_router

    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/reports/dashboard-summary?platform=xhs")

    assert response.status_code == 200
    body = response.json()
    assert body["monitoring"]["today_collected"] == 2
    assert body["decision"]["sample_status"] in {"limited", "enough"}
    assert body["opportunities"]
    assert any(item["type"] == "keyword" for item in body["opportunities"])


def test_dashboard_summary_fallback_skips_newer_empty_queued_jobs(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_jobs(self):
            return [
                {"id": 10, "status": "queued", "collection_mode": "creator", "platforms": ["xhs"]},
                {"id": 9, "status": "queued", "collection_mode": "creator", "platforms": ["xhs"]},
                {"id": 1, "status": "completed", "collection_mode": "search", "platforms": ["xhs"]},
            ]

        async def list_creator_candidates(self, vertical_id=None, platform=None, pool_name=None):
            return []

        async def list_keyword_heat_snapshots(
            self,
            vertical_id=None,
            scene_pack_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_competitor_composition_snapshots(
            self,
            competitor_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_content_tracking_snapshots(
            self,
            tracker_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_monitor_pools(self, enabled_only=False):
            return []

        async def list_opportunity_feedback(self, limit=500):
            return []

        async def list_posts(self, job_id, limit=None):
            if job_id != 1:
                return []
            return [
                {
                    "job_id": job_id,
                    "platform": "xhs",
                    "platform_post_id": "p1",
                    "title": "K12教育规划",
                    "engagement_json": {"source_keyword": "K12教育", "like_count": 120},
                }
            ]

        async def list_comments(self, job_id, limit=None):
            return []

    import api.routers.reports as reports_router

    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/reports/dashboard-summary?platform=xhs")

    assert response.status_code == 200
    body = response.json()
    assert any(item["type"] == "keyword" for item in body["opportunities"])
    assert any(item["type"] == "content" for item in body["watchlist"])


def test_dashboard_summary_adds_competitor_account_fallback(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_jobs(self):
            return []

        async def list_creator_candidates(self, vertical_id=None, platform=None, pool_name=None):
            return []

        async def list_keyword_heat_snapshots(
            self,
            vertical_id=None,
            scene_pack_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_competitor_composition_snapshots(
            self,
            competitor_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_competitor_accounts(self, enabled_only=False):
            return [
                {
                    "id": 7,
                    "platform": "xhs",
                    "creator_id": "competitor-7",
                    "display_name": "竞品账号",
                    "profile_url": "https://www.xiaohongshu.com/user/profile/competitor-7",
                    "enabled": True,
                }
            ]

        async def list_content_tracking_snapshots(
            self,
            tracker_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_monitor_pools(self, enabled_only=False):
            return []

        async def list_opportunity_feedback(self, limit=500):
            return []

    import api.routers.reports as reports_router

    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/reports/dashboard-summary?platform=xhs")

    assert response.status_code == 200
    body = response.json()
    assert any(item["type"] == "competitor" for item in body["watchlist"])
    assert body["type_decisions"]["competitor"]["sample_status"] == "limited"
    assert body["type_diagnostics"]["competitor"]


def test_dashboard_summary_includes_top_opportunities_watchlist_and_profile(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_jobs(self):
            return []

        async def list_creator_candidates(self, vertical_id=None, platform=None, pool_name=None):
            return []

        async def list_keyword_heat_snapshots(
            self,
            vertical_id=None,
            scene_pack_id=None,
            platform=None,
            limit=None,
        ):
            return [
                {
                    "keyword": "K12教育",
                    "platform": "xhs",
                    "heat_score": 85,
                    "growth_score": 20,
                    "sample_count": 100,
                    "evidence": {"items": ["增长"]},
                }
            ]

        async def list_competitor_composition_snapshots(
            self,
            competitor_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_content_tracking_snapshots(
            self,
            tracker_id=None,
            platform=None,
            limit=None,
        ):
            return []

        async def list_monitor_pools(self, enabled_only=False):
            return []

        async def list_opportunity_feedback(self, limit=500):
            return []

    import api.routers.reports as reports_router

    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/reports/dashboard-summary?platform=xhs")

    assert response.status_code == 200
    body = response.json()
    assert body["top_opportunities"]
    assert "watchlist" in body
    assert body["scoring_profile"]["window"] == "7d_plus_24h"


def test_opportunity_feedback_api_records_feedback(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def create_opportunity_feedback(self, payload):
            return {"id": 1, **payload, "created_at": "2026-05-21T00:00:00Z"}

    import api.routers.reports as reports_router

    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/reports/opportunity-feedback",
        json={
            "opportunity_id": "keyword:xhs:K12教育",
            "feedback": "watch",
            "note": "needs more samples",
        },
    )

    assert response.status_code == 200
    assert response.json()["feedback"]["feedback"] == "watch"
