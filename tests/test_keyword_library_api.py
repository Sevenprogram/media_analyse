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
