from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import config
from config.db_config import sqlite_db_config
from database.db_session import close_engines, create_tables
from saas_test_utils import authenticate_test_client


@pytest.mark.asyncio
async def test_realtime_check_returns_probe_payload(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "creator-realtime-check.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    monkeypatch.setattr(config, "ENABLE_TIKHUB", True, raising=False)
    await close_engines()
    await create_tables("sqlite")

    from api.main import app
    from api.routers import creator_search as creator_search_router

    async def fake_probe(*, raw_query: str, platforms: list[str], client_factory=None):
        assert raw_query == "K12 家长"
        assert platforms == ["xhs", "dy"]
        return {
            "status": "ok",
            "query": raw_query,
            "keyword": "K12",
            "platforms": platforms,
            "unsupported_platforms": [],
            "results": [
                {"platform": "xhs", "ok": True, "item_count": 3, "sample_creator": None, "error": None},
                {"platform": "dy", "ok": True, "item_count": 2, "sample_creator": None, "error": None},
            ],
        }

    monkeypatch.setattr(creator_search_router, "resolve_tikhub_api_key", lambda: "token")
    monkeypatch.setattr(creator_search_router, "probe_realtime_platforms", fake_probe)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await authenticate_test_client(
            client,
            email="creator-realtime@example.com",
            organization_name="Creator Realtime Workspace",
        )
        response = await client.post(
            "/api/creator-search/realtime/check",
            json={"raw_query": "K12 家长", "platforms": ["xhs", "dy"]},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["api_key_set"] is True
    assert payload["provider"] == "tikhub"
    assert payload["supported_platforms"] == ["xhs", "dy"]
    assert payload["probe"]["status"] == "ok"
    assert len(payload["probe"]["results"]) == 2


@pytest.mark.asyncio
async def test_realtime_check_skips_when_api_key_missing(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "creator-realtime-missing-key.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    monkeypatch.setattr(config, "ENABLE_TIKHUB", True, raising=False)
    await close_engines()
    await create_tables("sqlite")

    from api.main import app
    from api.routers import creator_search as creator_search_router

    monkeypatch.setattr(creator_search_router, "resolve_tikhub_api_key", lambda: "")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await authenticate_test_client(
            client,
            email="creator-realtime-missing@example.com",
            organization_name="Creator Realtime Missing Workspace",
        )
        response = await client.post(
            "/api/creator-search/realtime/check",
            json={"raw_query": "K12 家长", "platforms": ["xhs"]},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["api_key_set"] is False
    assert payload["probe"]["status"] == "skipped"
    assert payload["probe"]["reason"] == "TIKHUB_API_KEY is not configured"
    await close_engines()
    await close_engines()
