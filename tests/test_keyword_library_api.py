from fastapi.testclient import TestClient

import config
from api.main import app
import api.routers.keyword_library as keyword_library_router


def test_create_scene_pack_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def create_scene_pack(self, payload):
            return {"id": 1, **payload}

    monkeypatch.setattr(keyword_library_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/keyword-library/scene-packs",
        json={"vertical_id": 1, "name": "single parent mothers", "weight": 1.5},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "single parent mothers"


def test_update_scene_pack_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def update_scene_pack(self, scene_pack_id, payload):
            return {"id": scene_pack_id, "name": payload["name"], "enabled": payload["enabled"]}

    monkeypatch.setattr(keyword_library_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.patch(
        "/api/keyword-library/scene-packs/7",
        json={"name": "K12 updated", "enabled": False},
    )

    assert response.status_code == 200
    assert response.json() == {"id": 7, "name": "K12 updated", "enabled": False}


def test_update_scene_pack_keyword_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def update_scene_pack_keyword(self, keyword_id, payload):
            return {
                "id": keyword_id,
                "keyword": payload["keyword"],
                "keyword_type": payload["keyword_type"],
                "usage_flags": payload["usage_flags"],
            }

    monkeypatch.setattr(keyword_library_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.patch(
        "/api/keyword-library/keywords/9",
        json={
            "keyword": "升学焦虑",
            "keyword_type": "secondary",
            "usage_flags": ["creator_discovery", "keyword_heat"],
        },
    )

    assert response.status_code == 200
    assert response.json()["keyword"] == "升学焦虑"
    assert response.json()["usage_flags"] == ["creator_discovery", "keyword_heat"]


def test_update_keyword_route_returns_404(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def update_scene_pack_keyword(self, keyword_id, payload):
            return None

    monkeypatch.setattr(keyword_library_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.patch("/api/keyword-library/keywords/404", json={"enabled": False})

    assert response.status_code == 404


def test_delete_scene_pack_route_rejects_non_empty_pack(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def delete_scene_pack(self, scene_pack_id):
            return {
                "deleted": False,
                "reason": "scene_pack_has_keywords",
                "keyword_count": 2,
            }

    monkeypatch.setattr(keyword_library_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.delete("/api/keyword-library/scene-packs/7")

    assert response.status_code == 409
    assert response.json()["detail"]["keyword_count"] == 2


def test_delete_scene_pack_keyword_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def delete_scene_pack_keyword(self, keyword_id):
            return {"deleted": True, "id": keyword_id}

    monkeypatch.setattr(keyword_library_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.delete("/api/keyword-library/keywords/9")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": 9}


def test_ai_expand_keywords_route_requires_provider(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def get_ai_provider(self, provider_id, *, include_secret=False):
            return None

    monkeypatch.setattr(keyword_library_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/keyword-library/ai/expand",
        json={"input_text": "K12 education", "provider_config_id": 999},
    )

    assert response.status_code == 404


def test_scene_pack_tracking_pack_and_sampling_jobs(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def get_scene_pack(self, scene_pack_id):
            return {"id": scene_pack_id, "name": "K12", "vertical_id": 1, "default_platforms": ["xhs"], "enabled": True}

        async def list_scene_pack_keywords(self, scene_pack_ids=None, enabled_only=False):
            return [{"keyword": "K12教育", "keyword_type": "primary", "enabled": True}]

        async def create_job(self, payload):
            return {"id": 1, **payload}

    monkeypatch.setattr(keyword_library_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/keyword-library/scene-packs/1/tracking-pack")
    assert response.status_code == 200
    assert response.json()["tracking_pack"]["effective_keywords_by_platform"]["xhs"] == ["K12教育"]

    response = client.post(
        "/api/keyword-library/scene-packs/1/sampling-jobs",
        json={"daily_sample_limit_per_keyword": 100},
    )
    assert response.status_code == 200
    assert response.json()["created"] == 1
    assert response.json()["jobs"][0]["collection_mode"] == "search"
