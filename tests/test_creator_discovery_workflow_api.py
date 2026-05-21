from fastapi.testclient import TestClient

import config
from api.main import app


def test_admin_bootstrap_defaults_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def upsert_platform_capability(self, payload):
            return {"id": 1, **payload}

        async def upsert_vertical_by_code(self, payload):
            return {"id": 10, **payload}

        async def upsert_tag_group_by_name(self, payload):
            return {"id": 20, **payload}

        async def upsert_tag_definition_by_name(self, payload):
            return {"id": 30, **payload}

    import api.routers.admin as admin_router

    monkeypatch.setattr(admin_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post("/api/admin/bootstrap/defaults")

    assert response.status_code == 200
    assert response.json()["capabilities"]
    assert response.json()["verticals"]
    assert response.json()["tag_definitions"]


def test_admin_tag_definition_import_and_export(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_verticals(self):
            return [{"id": 1, "code": "education", "name": "教育"}]

        async def list_tag_groups(self):
            return [{"id": 2, "vertical_id": 1, "name": "人群"}]

        async def list_tag_definitions(self, vertical_id=None, enabled_only=False):
            return [
                {
                    "id": 3,
                    "vertical_id": 1,
                    "group_id": 2,
                    "tag_name": "单亲妈妈",
                    "keywords": ["单亲妈妈"],
                    "synonyms": [],
                    "negative_keywords": [],
                    "ai_prompt_hint": None,
                    "weight": 10,
                    "enabled": True,
                }
            ]

        async def upsert_tag_group_by_name(self, payload):
            return {"id": 2, **payload}

        async def upsert_tag_definition_by_name(self, payload):
            return {"id": 3, **payload}

    import api.routers.admin as admin_router

    monkeypatch.setattr(admin_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/admin/tag-definitions/import",
        json={
            "items": [
                {
                    "vertical_code": "education",
                    "group_name": "人群",
                    "tag_name": "单亲妈妈",
                    "keywords": ["单亲妈妈"],
                    "weight": 10,
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["count"] == 1

    response = client.get("/api/admin/tag-definitions/export")
    assert response.status_code == 200
    assert response.json()["items"][0]["vertical_code"] == "education"


def test_creator_candidate_pool_and_export(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def upsert_creator_candidate(self, payload):
            return {"id": 1, **payload}

        async def list_creator_candidates(self, pool_name=None, platform=None, vertical_id=None):
            return [
                {
                    "platform": "xhs",
                    "creator_id": "creator-1",
                    "pool_name": pool_name or "default",
                    "vertical_id": vertical_id,
                    "match_score": 88.5,
                    "notes": "test",
                }
            ]

        async def get_creator_profile(self, platform, creator_id):
            if platform == "xhs" and creator_id == "creator-1":
                return {
                    "platform": "xhs",
                    "creator_id": "creator-1",
                    "display_name": "Teacher A",
                    "profile_url": "https://www.xiaohongshu.com/user/profile/creator-1",
                }
            return None

        async def list_creator_profiles(self, platforms=None, limit=None):
            return [
                {
                    "platform": "dy",
                    "creator_id": "creator-2",
                    "display_name": "Teacher B",
                    "profile_url": "https://www.douyin.com/user/creator-2",
                }
            ]

    import api.routers.creator_search as creator_search_router

    monkeypatch.setattr(creator_search_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/creator-search/candidate-pool",
        json={"platform": "xhs", "creator_id": "creator-1", "match_score": 88.5},
    )

    assert response.status_code == 200
    assert response.json()["creator_id"] == "creator-1"

    response = client.get("/api/creator-search/candidate-pool")
    assert response.status_code == 200
    assert response.json()["candidates"][0]["platform"] == "xhs"
    assert response.json()["candidates"][0]["display_name"] == "Teacher A"
    assert response.json()["candidates"][0]["profile_url"].endswith("/creator-1")

    response = client.get("/api/creator-search/candidate-pool?include_profile_candidates=true")
    assert response.status_code == 200
    assert {item["platform"] for item in response.json()["candidates"]} == {"xhs", "dy"}
    assert response.json()["candidates"][1]["display_name"] == "Teacher B"

    response = client.get("/api/creator-search/export")
    assert response.status_code == 200
    assert "creator-1" in response.text


def test_monitor_pool_routes_create_and_add_creators(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        def __init__(self):
            self.pool = {
                "id": 1,
                "name": "K12 creator pool",
                "schedule_interval_minutes": 720,
                "comment_policy": {
                    "enable_comments": True,
                    "enable_sub_comments": False,
                },
                "research_job_id": None,
            }
            self.creators = []
            self.updated_job_payload = None

        async def create_monitor_pool(self, payload):
            self.pool = {"id": 1, **payload}
            return self.pool

        async def list_monitor_pools(self, enabled_only=False):
            return [self.pool]

        async def get_monitor_pool(self, pool_id):
            return self.pool

        async def add_monitor_pool_creators(self, pool_id, creators):
            self.creators.extend(creators)
            return creators

        async def list_monitor_pool_creators(self, pool_id, enabled_only=True):
            return self.creators

        async def create_job(self, payload):
            return {"id": 77, **payload}

        async def update_job(self, job_id, payload):
            self.updated_job_payload = payload
            return {"id": job_id, **payload}

        async def update_monitor_pool(self, pool_id, payload):
            self.pool.update(payload)
            return self.pool

    import api.routers.creator_search as creator_search_router

    repository = FakeRepository()
    monkeypatch.setattr(creator_search_router, "ResearchRepository", lambda: repository)
    client = TestClient(app)

    response = client.post(
        "/api/creator-search/monitor-pools",
        json={"name": "K12 creator pool", "platforms": ["xhs"]},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "K12 creator pool"

    response = client.post(
        "/api/creator-search/monitor-pools/1/creators",
        json={
            "creators": [
                {"platform": "xhs", "creator_id": "u1", "match_score": 88}
            ],
            "crawl_now": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["job"]["collection_mode"] == "creator"
    assert response.json()["job"]["creator_ids"] == ["u1"]

    response = client.patch(
        "/api/creator-search/monitor-pools/1",
        json={
            "schedule_interval_minutes": 360,
            "comment_policy": {
                "enable_comments": True,
                "enable_sub_comments": True,
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["pool"]["schedule_interval_minutes"] == 360
    assert response.json()["job"]["schedule_interval_minutes"] == 360
    assert repository.updated_job_payload["comment_policy"]["enable_sub_comments"] is True


def test_realtime_discovery_requires_explicit_switch(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/creator-search/discover/realtime",
        json={"keywords": ["K12"], "platforms": ["xhs"], "realtime": False},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"


def test_realtime_discovery_schedules_execution(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    import api.routers.creator_search as creator_router

    called = {}

    async def fake_execute(job_id, *, background=True, force_schedule=True):
        called["job_id"] = job_id
        called["background"] = background
        called["force_schedule"] = force_schedule
        return {"status": "accepted", "job_id": job_id, "schedule": {"created": 1}}

    class FakeRepository:
        async def create_job(self, payload):
            assert payload["collection_mode"] == "search"
            return {"id": 123, **payload}

    monkeypatch.setattr(creator_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(creator_router, "schedule_and_execute_research_job", fake_execute)
    client = TestClient(app)

    response = client.post(
        "/api/creator-search/discover/realtime",
        json={"keywords": ["K12"], "platforms": ["xhs"], "realtime": True},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert called["background"] is True
    assert called["force_schedule"] is True


def test_keyword_opportunity_route_respects_platform_heat_switch(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def get_platform_capability(self, platform):
            return {"platform": platform, "enabled": True, "keyword_heat_enabled": False}

    import api.routers.keyword_opportunities as keyword_router

    monkeypatch.setattr(keyword_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/keyword-opportunities?vertical_id=1&platform=xhs")

    assert response.status_code == 400
    assert "disabled" in response.json()["detail"]


def test_keyword_opportunity_route_falls_back_to_source_keyword_ranking(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def get_platform_capability(self, platform):
            return {"platform": platform, "enabled": True, "keyword_heat_enabled": True}

        async def list_tag_definitions(self, vertical_id=None, enabled_only=True):
            return []

        async def list_entity_tags(self, vertical_id=None, platform=None):
            return []

        async def list_creator_profiles(self, platforms=None):
            return []

        async def list_creator_daily_snapshots(self, platform=None):
            return []

        async def list_scene_packs(self, vertical_id=None, enabled_only=True):
            return [{"id": 1, "vertical_id": 1, "name": "education"}]

        async def list_scene_pack_keywords(self, scene_pack_ids=None, enabled_only=True):
            return [{"id": 1, "scene_pack_id": 1, "keyword": "K12教育", "keyword_type": "primary"}]

        async def list_all_posts(self, platform=None, limit=5000):
            return [
                {
                    "platform": "xhs",
                    "platform_post_id": "p1",
                    "title": "英语启蒙",
                    "content": "陪读记录",
                    "publish_time": None,
                    "engagement_json": {"source_keyword": "单亲妈妈陪读", "like_count": 12},
                },
                {
                    "platform": "xhs",
                    "platform_post_id": "p2",
                    "title": "小升初规划",
                    "content": "暑假班",
                    "publish_time": None,
                    "engagement_json": {"source_keyword": "单亲妈妈陪读", "like_count": 8},
                },
            ]

    import api.routers.keyword_opportunities as keyword_router

    monkeypatch.setattr(keyword_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/keyword-opportunities?vertical_id=1&platform=xhs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["opportunities"]
    assert payload["opportunities"][0]["tag_name"] == "单亲妈妈陪读"
