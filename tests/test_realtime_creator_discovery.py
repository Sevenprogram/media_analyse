from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from research.realtime_creator_discovery import (
    discover_realtime_creators,
    probe_realtime_platforms,
)


class _FakeRepository:
    def __init__(self) -> None:
        self.profiles: list[dict] = []
        self.candidates: list[dict] = []

    async def upsert_creator_profile(self, payload: dict) -> dict:
        self.profiles.append(payload)
        return payload

    async def upsert_creator_candidate(self, payload: dict) -> dict:
        self.candidates.append(payload)
        return payload


class _FakeTikHubClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def request(self, method: str, path: str, *, params=None, json=None):
        self.calls.append((method, path))
        now = int(datetime.now(timezone.utc).timestamp())
        recent_a = now - int(timedelta(days=5).total_seconds())
        recent_b = now - int(timedelta(days=20).total_seconds())
        old = now - int(timedelta(days=45).total_seconds())

        if method == "GET" and path == "/api/v1/xiaohongshu/app_v2/search_users":
            return {
                "users": [
                    {
                        "id": "xhs-user-1",
                        "name": "K12 Parents",
                        "desc": "education family",
                        "sub_title": "1.25w",
                    }
                ]
            }

        if method == "POST" and path == "/api/v1/douyin/search/fetch_user_search_v2":
            return {
                "user_list": [
                    {
                        "user_info": {
                            "uid": "123",
                            "sec_uid": "dy-sec-1",
                            "nickname": "K12 Growth",
                            "signature": "family education",
                            "follower_count": 5000,
                            "aweme_count": 80,
                        },
                    }
                ]
            }

        if method == "GET" and path == "/api/v1/xiaohongshu/app_v2/get_user_posted_notes":
            return {
                "notes": [
                    {
                        "id": "xhs-note-1",
                        "title": "K12 parent experience",
                        "desc": "education planning",
                        "create_time": recent_a,
                        "likes": 120,
                        "comments_count": 10,
                        "collected_count": 6,
                        "share_count": 2,
                        "user": {"userid": "xhs-user-1", "nickname": "K12 Parents"},
                    },
                    {
                        "id": "xhs-note-2",
                        "title": "family tips",
                        "desc": "school",
                        "create_time": recent_b,
                        "likes": 60,
                        "comments_count": 5,
                        "collected_count": 3,
                        "share_count": 1,
                        "user": {"userid": "xhs-user-1", "nickname": "K12 Parents"},
                    },
                    {
                        "id": "xhs-note-old",
                        "title": "old note",
                        "desc": "archive",
                        "create_time": old,
                        "likes": 999,
                        "comments_count": 99,
                        "collected_count": 50,
                        "share_count": 20,
                        "user": {"userid": "xhs-user-1", "nickname": "K12 Parents"},
                    },
                ]
            }

        if method == "GET" and path == "/api/v1/douyin/web/fetch_user_post_videos":
            return {
                "aweme_list": [
                    {
                        "aweme_id": "dy-video-1",
                        "desc": "K12 family note",
                        "create_time": recent_a,
                        "author": {"uid": "123", "sec_uid": "dy-sec-1", "nickname": "K12 Growth"},
                        "statistics": {
                            "digg_count": 400,
                            "comment_count": 20,
                            "collect_count": 10,
                            "share_count": 5,
                        },
                    },
                    {
                        "aweme_id": "dy-video-old",
                        "desc": "old video",
                        "create_time": old,
                        "author": {"uid": "123", "sec_uid": "dy-sec-1", "nickname": "K12 Growth"},
                        "statistics": {
                            "digg_count": 999,
                            "comment_count": 50,
                            "collect_count": 10,
                            "share_count": 5,
                        },
                    },
                ],
                "has_more": False,
                "max_cursor": 0,
            }

        raise AssertionError(f"unexpected request: {method} {path} params={params} json={json}")

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_discover_realtime_creators_uses_tikhub_user_search_and_creator_posts_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "ENABLE_TIKHUB", True, raising=False)
    repo = _FakeRepository()
    client = _FakeTikHubClient()

    from research import realtime_creator_discovery as mod

    monkeypatch.setattr(mod, "resolve_tikhub_api_key", lambda: "token")

    result = await discover_realtime_creators(
        repo,
        {
            "raw_query": "K12 family",
            "platforms": ["xhs", "dy"],
            "limit": 2,
            "recent_activity_min": 1,
        },
        client_factory=lambda: client,
    )

    assert result["diagnostics"]["status"] == "ok"
    assert ("GET", "/api/v1/xiaohongshu/app_v2/search_users") in client.calls
    assert ("POST", "/api/v1/douyin/search/fetch_user_search_v2") in client.calls

    by_platform = {item["platform"]: item for item in result["results"]}
    assert by_platform["xhs"]["recent_post_count_30d"] == 2
    assert by_platform["xhs"]["follower_count"] == 12500
    assert by_platform["xhs"]["avg_engagement_rate"] is not None
    assert by_platform["dy"]["recent_post_count_30d"] == 1
    assert by_platform["dy"]["follower_count"] == 5000
    assert by_platform["dy"]["avg_engagement_rate"] is not None
    assert all(profile["tag_summary_json"]["source"] == "tikhub_realtime" for profile in repo.profiles)
    assert all(candidate["notes"] == "Imported from TikHub realtime creator discovery" for candidate in repo.candidates)


@pytest.mark.asyncio
async def test_probe_realtime_platforms_uses_tikhub_user_search_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "ENABLE_TIKHUB", True, raising=False)
    client = _FakeTikHubClient()

    from research import realtime_creator_discovery as mod

    monkeypatch.setattr(mod, "resolve_tikhub_api_key", lambda: "token")

    result = await probe_realtime_platforms(
        raw_query="K12 family",
        platforms=["xhs", "dy"],
        client_factory=lambda: client,
    )

    assert result["status"] == "ok"
    assert [item["platform"] for item in result["results"]] == ["xhs", "dy"]
    assert ("GET", "/api/v1/xiaohongshu/app_v2/search_users") in client.calls
    assert ("POST", "/api/v1/douyin/search/fetch_user_search_v2") in client.calls
