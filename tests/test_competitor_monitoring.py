from datetime import date, datetime, timedelta

import pytest

from research.competitors import CompetitorService


class FakeRepository:
    def __init__(self, capability=None):
        self.capability = capability
        self.snapshot = None

    async def get_platform_capability(self, platform):
        return self.capability

    async def upsert_competitor_account(self, payload):
        return {"id": 1, **payload}

    async def upsert_creator_daily_snapshot(self, payload):
        self.snapshot = payload
        return {"id": 1, **payload}


@pytest.mark.asyncio
async def test_competitor_service_rejects_disabled_monitoring():
    repository = FakeRepository({"enabled": True, "daily_monitor_enabled": False})

    with pytest.raises(ValueError, match="daily monitoring"):
        await CompetitorService(repository).create_competitor(
            {"platform": "xhs", "creator_id": "u1"}
        )


@pytest.mark.asyncio
async def test_competitor_snapshot_aggregates_posts_and_tags():
    repository = FakeRepository()
    result = await CompetitorService(repository).build_daily_snapshot(
        platform="xhs",
        creator_id="u1",
        snapshot_date=date(2026, 5, 20),
        posts=[
            {"platform_post_id": "p1", "title": "A", "engagement_json": {"liked_count": 100, "comment_count": 2}},
            {"platform_post_id": "p2", "title": "B", "engagement_json": {"liked_count": 10, "share_count": 1}},
        ],
        entity_tags=[{"tag_id": 1}, {"tag_id": 1}, {"tag_id": 2}],
        follower_count=1000,
    )

    assert result["new_post_count"] == 2
    assert result["total_like_count"] == 110
    assert result["tag_distribution_json"] == {"1": 2, "2": 1}


def test_competitor_from_url_parses_xhs_profile():
    from api.routers.competitors import _creator_id_from_profile_url

    assert (
        _creator_id_from_profile_url("xhs", "https://www.xiaohongshu.com/user/profile/abc123?x=1")
        == "abc123"
    )


def test_competitor_from_url_uses_existing_profile_display_name(monkeypatch):
    from fastapi.testclient import TestClient

    import config
    from api.main import app
    import api.routers.competitors as competitors_router

    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def get_platform_capability(self, platform):
            return {"enabled": True, "daily_monitor_enabled": True}

        async def get_creator_profile(self, platform, creator_id):
            assert creator_id == "abc123"
            return {"display_name": "K12官方号"}

        async def upsert_competitor_account(self, payload):
            return {"id": 1, **payload}

    monkeypatch.setattr(competitors_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/competitors/from-url",
        json={"platform": "xhs", "profile_url": "https://www.xiaohongshu.com/user/profile/abc123"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "K12官方号"


def test_list_competitors_backfills_missing_display_name(monkeypatch):
    from fastapi.testclient import TestClient

    import config
    from api.main import app
    import api.routers.competitors as competitors_router

    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_competitor_accounts(self, enabled_only=False):
            return [{"id": 1, "platform": "xhs", "creator_id": "abc123", "display_name": None}]

        async def get_creator_profile(self, platform, creator_id):
            return {"display_name": "K12官方号"}

        async def update_competitor_account(self, competitor_id, payload):
            return {"id": competitor_id, "platform": "xhs", "creator_id": "abc123", **payload}

    monkeypatch.setattr(competitors_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/competitors?enabled_only=true")

    assert response.status_code == 200
    assert response.json()["competitors"][0]["display_name"] == "K12官方号"


def test_refresh_competitor_profile_reports_missing_name(monkeypatch):
    from fastapi.testclient import TestClient

    import config
    from api.main import app
    import api.routers.competitors as competitors_router

    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setattr(config, "TIKHUB_API_KEY", "", raising=False)
    monkeypatch.setattr(config, "ENABLE_TIKHUB", False, raising=False)

    class FakeRepository:
        async def get_competitor_account(self, competitor_id):
            return {"id": competitor_id, "platform": "xhs", "creator_id": "abc123", "display_name": None}

        async def get_creator_profile(self, platform, creator_id):
            return None

        async def list_creator_candidates(self, platform=None):
            return []

        async def list_account_profiles(self, platform=None):
            return []

    monkeypatch.setattr(competitors_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post("/api/competitors/1/refresh-profile")

    assert response.status_code == 200
    assert response.json()["updated"] is False
    assert "TIKHUB_API_KEY" in response.json()["message"]


def test_fetch_task_route_is_not_shadowed_by_competitor_dynamic_route():
    from fastapi.testclient import TestClient

    from api.main import app
    import api.routers.competitors as competitors_router

    competitors_router._fetch_now_tasks.clear()
    competitors_router._fetch_now_tasks["task-1"] = {
        "task_id": "task-1",
        "competitor_id": 1,
        "status": "running",
        "stage": "crawling",
        "progress": 40,
        "message": "正在采集",
        "logs": [],
        "result": None,
        "error": None,
    }

    client = TestClient(app)
    response = client.get("/api/competitors/fetch-tasks/task-1")

    assert response.status_code == 200
    assert response.json()["task_id"] == "task-1"


def test_fetch_now_rejects_idle_worker_result():
    import api.routers.competitors as competitors_router

    with pytest.raises(RuntimeError, match="没有领取到采集单元"):
        competitors_router._raise_if_worker_did_not_collect({"status": "idle"})


def test_filter_posts_by_days_keeps_only_requested_window():
    import api.routers.competitors as competitors_router

    posts = [
        {"platform_post_id": "new", "publish_time": datetime.now() - timedelta(days=1)},
        {"platform_post_id": "old", "publish_time": datetime.now() - timedelta(days=10)},
        {"platform_post_id": "unknown", "publish_time": None},
    ]

    result = competitors_router._filter_posts_by_days(posts, 7)

    assert [item["platform_post_id"] for item in result] == ["new", "unknown"]


@pytest.mark.asyncio
async def test_content_tracking_snapshot_accepts_datetime_evidence(monkeypatch):
    from research.repository import ResearchRepository
    import research.repository as repository_module

    class FakeItem:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeSession:
        def __init__(self):
            self.item = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def add(self, item):
            self.item = item

        async def flush(self):
            import json

            json.dumps(self.item.evidence_json)

        async def refresh(self, item):
            item.id = 1
            item.created_at = datetime.now()

    fake_session = FakeSession()
    monkeypatch.setattr(repository_module, "get_session", lambda: fake_session)
    monkeypatch.setattr(repository_module, "ResearchContentTrackingSnapshot", FakeItem)

    result = await ResearchRepository().create_content_tracking_snapshot(
        {
            "tracker_id": 1,
            "snapshot_date": date.today(),
            "platform": "xhs",
            "total_content_count": 1,
            "evidence": {"hot_content": [{"publish_time": datetime.now()}]},
        }
    )

    assert result["evidence"]["hot_content"][0]["publish_time"]


@pytest.mark.asyncio
async def test_crawl_event_accepts_datetime_stats(monkeypatch):
    from research.repository import ResearchRepository
    import research.repository as repository_module

    class FakeItem:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeSession:
        def __init__(self):
            self.item = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def add(self, item):
            self.item = item

        async def flush(self):
            import json

            json.dumps(self.item.stats_json)

        async def refresh(self, item):
            item.id = 1
            item.created_at = datetime.now()

    monkeypatch.setattr(repository_module, "get_session", lambda: FakeSession())
    monkeypatch.setattr(repository_module, "CrawlEvent", FakeItem)

    result = await ResearchRepository().create_event(
        job_id=1,
        platform="xhs",
        event_type="crawl_unit_postprocess_completed",
        message="done",
        stats={"finished_at": datetime.now(), "snapshot_date": date.today()},
    )

    assert result["stats_json"]["finished_at"]
