from fastapi.testclient import TestClient

import config
from api.main import app


def test_admin_platform_capability_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def upsert_platform_capability(self, payload):
            return {"id": 1, **payload}

    import api.routers.admin as admin_router

    monkeypatch.setattr(admin_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.put(
        "/api/admin/platform-capabilities/xhs",
        json={"platform": "xhs", "enabled": False},
    )

    assert response.status_code == 200
    assert response.json()["platform"] == "xhs"
    assert response.json()["enabled"] is False


def test_creator_search_parse_intent_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_tag_definitions(self, vertical_id=None, enabled_only=False):
            return [
                {"id": 1, "vertical_id": 1, "tag_name": "K12教育", "keywords": ["K12"], "synonyms": []}
            ]

        async def list_verticals(self, enabled_only=False):
            return [{"id": 1, "name": "Education"}]

        async def create_search_intent(self, payload):
            return {"id": 1, **payload}

    import api.routers.creator_search as creator_search_router

    monkeypatch.setattr(creator_search_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post("/api/creator-search/parse-intent", json={"raw_query": "K12"})

    assert response.status_code == 200
    assert response.json()["required_tags"] == [1]


def test_competitor_create_rejects_disabled_platform(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def get_platform_capability(self, platform):
            return {"platform": platform, "enabled": False, "daily_monitor_enabled": True}

    import api.routers.competitors as competitors_router

    monkeypatch.setattr(competitors_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post("/api/competitors", json={"platform": "xhs", "creator_id": "u1"})

    assert response.status_code == 400
    assert "not enabled" in response.json()["detail"]
