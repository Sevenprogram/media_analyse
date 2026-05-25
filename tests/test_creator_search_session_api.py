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
async def test_creator_search_session_persist_restore_and_save(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "creator-search-session.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))

    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await authenticate_test_client(
            client,
            email="creator-session@example.com",
            organization_name="Creator Session Workspace",
        )

        persist_response = await client.post(
            "/api/creator-search/search-sessions",
            json={
                "raw_query": "K12 家长",
                "selected_vertical_id": None,
                "search_payload": {
                    "raw_query": "K12 家长",
                    "platforms": ["xhs", "dy"],
                    "include_realtime": True,
                    "realtime_ratio": 50,
                    "limit": 50,
                },
                "view_state": {
                    "query": "K12 家长",
                    "selectedVerticalId": "all",
                    "platformFilter": "all",
                    "activeTab": "recommended",
                    "filters": {
                        "followerMinCount": "100",
                        "followerMaxCount": "",
                        "recentPostsMin": "1",
                        "activityLevel": "any",
                        "engagementMinPercent": "",
                        "viralMinPercent": "",
                    },
                    "includeRealtime": True,
                    "realtimeRatioPercent": "50",
                    "displayLimit": 10,
                    "analysisStatus": "done",
                },
                "diagnostics": {"profile_count": 12, "guidance": "搜索完成"},
                "realtime": {"status": "ok", "selected_count": 5},
                "progress": {"stage": "complete", "percent": 100},
                "message": "搜索完成，结果已按综合匹配分排序。",
                "result_summary": "返回 12 位达人",
                "results": [
                    {
                        "platform": "xhs",
                        "creator_id": "xhs-user-1",
                        "display_name": "学而思妈妈",
                        "profile_url": "https://example.com/xhs-user-1",
                        "follower_count": 12000,
                        "recent_post_count_30d": 6,
                        "avg_engagement_rate": 0.034,
                        "hot_post_rate": 0.11,
                        "match_score": 88,
                        "matched_tags": [{"term": "K12家长"}],
                        "evidence": [{"title": "代表内容"}],
                        "source_type": "mixed",
                        "source_labels": ["Database", "Realtime"],
                    },
                    {
                        "platform": "dy",
                        "creator_id": "dy-user-2",
                        "display_name": "育儿笔记",
                        "follower_count": 8600,
                        "recent_post_count_30d": 4,
                        "avg_engagement_rate": 0.027,
                        "hot_post_rate": 0.05,
                        "match_score": 79,
                        "matched_tags": [{"term": "家长"}],
                        "evidence": [],
                        "source_type": "local",
                        "source_labels": ["Database"],
                    },
                ],
            },
        )

        assert persist_response.status_code == 200, persist_response.text
        persisted = persist_response.json()["session"]
        assert persisted["raw_query"] == "K12 家长"
        assert persisted["result_count"] == 2
        assert len(persisted["results"]) == 2
        assert persisted["saved"] is False

        latest_response = await client.get("/api/creator-search/search-sessions/latest")
        assert latest_response.status_code == 200, latest_response.text
        latest = latest_response.json()["session"]
        assert latest["id"] == persisted["id"]
        assert latest["view_state"]["displayLimit"] == 10
        assert latest["results"][0]["creator_id"] == "xhs-user-1"

        save_response = await client.post(
            f"/api/creator-search/search-sessions/{persisted['id']}/save",
            json={"saved": True, "saved_name": "K12 家长搜索"},
        )
        assert save_response.status_code == 200, save_response.text
        saved = save_response.json()["session"]
        assert saved["saved"] is True
        assert saved["saved_name"] == "K12 家长搜索"

    await close_engines()
