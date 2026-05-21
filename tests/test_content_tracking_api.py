from fastapi.testclient import TestClient

import config
from api.main import app


def test_content_tracking_analyze_returns_hits(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_all_posts(self, platform=None, limit=None):
            return [
                {
                    "platform": "xhs",
                    "platform_post_id": "p1",
                    "title": "K12教育",
                    "content": "单亲妈妈如何陪伴学习",
                    "author_hash": "a1",
                    "engagement_json": {"liked_count": 100},
                }
            ]

        async def list_all_comments(self, platform=None, limit=None):
            return [
                {
                    "platform": "xhs",
                    "platform_comment_id": "c1",
                    "platform_post_id": "p1",
                    "content": "单亲妈妈很需要这类K12建议",
                    "like_count": 3,
                }
            ]

        async def list_entity_tags(self, vertical_id=None, platform=None):
            return [
                {
                    "entity_type": "post",
                    "entity_id": "p1",
                    "platform": "xhs",
                    "tag_id": 1,
                    "confidence": 0.9,
                }
            ]

        async def list_tag_definitions(self, vertical_id=None, enabled_only=False):
            return [{"id": 1, "tag_name": "单亲妈妈"}]

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/content-tracking/analyze",
        json={"query": "K12教育 + 单亲妈妈", "vertical_id": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["matched_posts"] == 1
    assert body["summary"]["matched_comments"] == 1


def test_content_tracking_extract_search_and_tracker_routes(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_scene_pack_keywords(self, scene_pack_ids=None, enabled_only=False):
            return [
                {
                    "scene_pack_id": 1,
                    "keyword": "K12",
                    "keyword_type": "primary",
                    "weight": 1,
                }
            ]

        async def list_all_posts(self, platform=None, limit=None):
            return [
                {
                    "platform": "xhs",
                    "platform_post_id": "p1",
                    "title": "K12 tutoring",
                    "content": "single parent mothers",
                    "engagement_json": {"liked_count": 20},
                }
            ]

        async def create_content_tracker(self, payload):
            return {"id": 1, **payload}

        async def list_content_trackers(self, enabled_only=False):
            return [{"id": 1, "name": "tracker"}]

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/content-tracking/extract-keywords",
        json={"text": "K12 tutoring", "scene_pack_ids": [1]},
    )
    assert response.status_code == 200
    assert response.json()["keywords"][0]["keyword"] == "K12"

    response = client.post(
        "/api/content-tracking/search-similar",
        json={"keywords": ["K12"], "platforms": ["xhs"]},
    )
    assert response.status_code == 200
    assert response.json()["candidates"][0]["platform_post_id"] == "p1"

    response = client.post(
        "/api/content-tracking/trackers",
        json={"name": "K12 tracker", "platforms": ["xhs"], "included_keywords": ["K12"]},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "K12 tracker"


def test_content_realtime_discovery_requires_explicit_switch(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/content-tracking/realtime-discovery",
        json={"keywords": ["K12"], "platforms": ["xhs"], "realtime": False},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"


def test_growth_report_returns_summary(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_creator_candidates(self, vertical_id=None, platform=None, pool_name=None):
            return [{"platform": "xhs", "creator_id": "a1", "vertical_id": vertical_id, "match_score": 88}]

        async def list_creator_profiles(self, platforms=None, limit=None):
            return [{"platform": "xhs", "creator_id": "a1", "tag_summary_json": {"1": {"count": 3}}}]

        async def list_competitor_accounts(self, enabled_only=False):
            return [{"platform": "xhs", "creator_id": "c1", "vertical_id": 1, "enabled": True}]

        async def list_creator_daily_snapshots(self, platform=None, creator_id=None):
            return [{"platform": "xhs", "tag_distribution_json": {"1": 8}}]

        async def list_tag_definitions(self, vertical_id=None, enabled_only=False):
            return [{"id": 1, "tag_name": "K12教育", "vertical_id": 1}]

        async def list_entity_tags(self, vertical_id=None, platform=None, tag_ids=None, entity_type=None, entity_id=None):
            return [{"tag_id": 1, "platform": "xhs"}]

    import api.routers.reports as reports_router

    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/reports/growth-summary?vertical_id=1&platform=xhs")

    assert response.status_code == 200
    assert response.json()["metrics"]["candidate_creators"] == 1

    response = client.get("/api/reports/boss-summary?vertical_id=1&platform=xhs")

    assert response.status_code == 200
    assert response.json()["sections"]["creator_discovery"]["count"] == 1
    assert response.json()["recommended_actions"]


def test_growth_report_falls_back_to_keyword_heat_snapshots(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_creator_candidates(self, vertical_id=None, platform=None, pool_name=None):
            return []

        async def list_creator_profiles(self, platforms=None, limit=None):
            return []

        async def list_competitor_accounts(self, enabled_only=False):
            return []

        async def list_creator_daily_snapshots(self, platform=None, creator_id=None):
            return []

        async def list_tag_definitions(self, vertical_id=None, enabled_only=False):
            return []

        async def list_entity_tags(self, vertical_id=None, platform=None, tag_ids=None, entity_type=None, entity_id=None):
            return []

        async def list_competitor_composition_snapshots(self, platform=None, limit=50):
            return []

        async def list_keyword_heat_snapshots(self, platform=None, limit=50):
            return [
                {
                    "keyword": "单亲妈妈陪读",
                    "platform": "xhs",
                    "heat_score": 88,
                    "growth_score": 19,
                    "platform_signal": "boosting",
                    "evidence": {"items": ["source keyword ranking"]},
                }
            ]

        async def list_content_tracking_snapshots(self, platform=None, limit=50):
            return []

    import api.routers.reports as reports_router

    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/reports/growth-summary?vertical_id=1&platform=xhs")

    assert response.status_code == 200
    assert response.json()["top_opportunities"]
    assert response.json()["top_opportunities"][0]["tag_name"] == "单亲妈妈陪读"
