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


class _FakeJustOneAPIClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []

    async def request(self, method: str, path: str, *, params=None, json=None):
        self.calls.append((method, path, params))

        if method == "GET" and path == "/api/xiaohongshu-pgy/api/solar/cooperator/blogger/v2/v1":
            return {
                "kols": [
                    {
                        "userId": "xhs-user-1",
                        "kolId": "kol-1",
                        "nickName": "K12 Parents",
                        "desc": "education family",
                        "fansNumber": "3.6w",
                        "noteNumber": 40,
                    }
                ]
            }

        if method == "GET" and path == "/api/xiaohongshu-pgy/api/solar/kol/dataV3/notesRate/v1":
            return {
                "noteNumber": 5,
                "interactionRate": "0.34",
                "thousandLikePercent": "20",
                "notes": [
                    {
                        "noteId": "xhs-note-1",
                        "title": "K12 parent experience",
                        "interactionNum": 1200,
                    },
                    {
                        "noteId": "xhs-note-2",
                        "title": "family education planning",
                        "likeNum": 200,
                        "collectNum": 30,
                        "commentNum": 20,
                        "shareNum": 5,
                    },
                ],
            }

        raise AssertionError(f"unexpected JustOne request: {method} {path} params={params} json={json}")

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_discover_realtime_creators_uses_justone_for_xhs_and_tikhub_for_dy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "ENABLE_TIKHUB", True, raising=False)
    monkeypatch.setattr(config, "ENABLE_JUSTONE_API", True, raising=False)
    repo = _FakeRepository()
    tikhub_client = _FakeTikHubClient()
    justone_client = _FakeJustOneAPIClient()

    from research import realtime_creator_discovery as mod

    monkeypatch.setattr(mod, "resolve_tikhub_api_key", lambda: "token")
    monkeypatch.setattr(mod, "resolve_justone_api_key", lambda: "token")

    result = await discover_realtime_creators(
        repo,
        {
            "raw_query": "K12 family",
            "platforms": ["xhs", "dy"],
            "limit": 2,
            "recent_activity_min": 1,
        },
        client_factory=lambda: tikhub_client,
        justone_client_factory=lambda: justone_client,
    )

    assert result["diagnostics"]["status"] == "ok"
    assert ("GET", "/api/v1/xiaohongshu/app_v2/search_users") not in tikhub_client.calls
    assert ("POST", "/api/v1/douyin/search/fetch_user_search_v2") in tikhub_client.calls
    assert any(
        path == "/api/xiaohongshu-pgy/api/solar/cooperator/blogger/v2/v1"
        for _, path, _ in justone_client.calls
    )
    assert not any(
        path == "/api/xiaohongshu-pgy/api/solar/kol/dataV3/fansSummary/v1"
        for _, path, _ in justone_client.calls
    )
    assert any(
        path == "/api/xiaohongshu-pgy/api/solar/kol/dataV3/notesRate/v1"
        for _, path, _ in justone_client.calls
    )

    by_platform = {item["platform"]: item for item in result["results"]}
    assert by_platform["xhs"]["recent_post_count_30d"] == 5
    assert by_platform["xhs"]["follower_count"] == 36000
    assert by_platform["xhs"]["avg_engagement_rate"] == 0.0034
    assert by_platform["xhs"]["hot_post_rate"] == 0.2
    assert by_platform["dy"]["recent_post_count_30d"] == 1
    assert by_platform["dy"]["follower_count"] == 5000
    assert by_platform["dy"]["avg_engagement_rate"] is not None
    sources = {profile["platform"]: profile["tag_summary_json"]["source"] for profile in repo.profiles}
    assert sources == {"xhs": "justoneapi_xhs_realtime", "dy": "tikhub_realtime"}
    notes = {candidate["platform"]: candidate["notes"] for candidate in repo.candidates}
    assert notes == {
        "xhs": "Imported from JustOneAPI Xiaohongshu realtime creator discovery",
        "dy": "Imported from TikHub realtime creator discovery",
    }


@pytest.mark.asyncio
async def test_probe_realtime_platforms_uses_justone_for_xhs_and_tikhub_for_dy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "ENABLE_TIKHUB", True, raising=False)
    monkeypatch.setattr(config, "ENABLE_JUSTONE_API", True, raising=False)
    tikhub_client = _FakeTikHubClient()
    justone_client = _FakeJustOneAPIClient()

    from research import realtime_creator_discovery as mod

    monkeypatch.setattr(mod, "resolve_tikhub_api_key", lambda: "token")
    monkeypatch.setattr(mod, "resolve_justone_api_key", lambda: "token")

    result = await probe_realtime_platforms(
        raw_query="K12 family",
        platforms=["xhs", "dy"],
        client_factory=lambda: tikhub_client,
        justone_client_factory=lambda: justone_client,
    )

    assert result["status"] == "ok"
    assert [item["platform"] for item in result["results"]] == ["xhs", "dy"]
    assert ("GET", "/api/v1/xiaohongshu/app_v2/search_users") not in tikhub_client.calls
    assert ("POST", "/api/v1/douyin/search/fetch_user_search_v2") in tikhub_client.calls
    assert any(
        path == "/api/xiaohongshu-pgy/api/solar/cooperator/blogger/v2/v1"
        for _, path, _ in justone_client.calls
    )


class _PagedJustOneAPIClient:
    def __init__(self, *, profiles: list[dict], metrics: dict[str, dict]) -> None:
        self.profiles = profiles
        self.metrics = metrics
        self.calls: list[tuple[str, str, dict | None]] = []

    async def request(self, method: str, path: str, *, params=None, json=None):
        self.calls.append((method, path, params))
        if method == "GET" and path == "/api/xiaohongshu-pgy/api/solar/cooperator/blogger/v2/v1":
            page = int((params or {}).get("page") or 1)
            start = (page - 1) * 2
            return {"list": self.profiles[start : start + 2]}

        if method == "GET" and path == "/api/xiaohongshu-pgy/api/solar/kol/dataV3/notesRate/v1":
            user_id = str((params or {}).get("userId") or "")
            return self.metrics[user_id]

        raise AssertionError(f"unexpected JustOne request: {method} {path} params={params} json={json}")

    async def close(self) -> None:
        return None


def _xhs_profile(user_id: str, *, fans: int = 5000) -> dict:
    return {
        "userId": user_id,
        "nickName": f"K12 Parent {user_id}",
        "desc": "K12 family education",
        "fansNumber": fans,
        "noteNumber": 20,
    }


def _xhs_metrics(note_number: int, *, interaction_rate: str | None = "1.2") -> dict:
    payload = {
        "noteNumber": note_number,
        "thousandLikePercent": "10",
        "notes": [
            {
                "noteId": f"note-{note_number}",
                "title": "K12 family education",
                "interactionNum": 200,
            }
        ],
    }
    if interaction_rate is not None:
        payload["interactionRate"] = interaction_rate
    return payload


@pytest.mark.asyncio
async def test_discover_realtime_creators_expands_candidate_pool_before_relaxing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "ENABLE_JUSTONE_API", True, raising=False)

    from research import realtime_creator_discovery as mod

    monkeypatch.setattr(mod, "resolve_justone_api_key", lambda: "token")
    monkeypatch.setattr(mod, "_candidate_window", lambda limit: 2)
    monkeypatch.setattr(mod, "_expanded_candidate_window", lambda limit: 4)

    profiles = [_xhs_profile(f"xhs-{index}") for index in range(1, 5)]
    metrics = {f"xhs-{index}": _xhs_metrics(2) for index in range(1, 5)}
    client = _PagedJustOneAPIClient(profiles=profiles, metrics=metrics)

    result = await discover_realtime_creators(
        _FakeRepository(),
        {
            "raw_query": "K12",
            "platforms": ["xhs"],
            "limit": 3,
            "follower_min": 200,
            "recent_activity_min": 1,
        },
        justone_client_factory=lambda: client,
    )

    assert len(result["results"]) == 3
    assert result["diagnostics"]["completion_strategy"] == "expanded_strict"
    assert result["diagnostics"]["strict_matched_creators"] == 2
    assert result["diagnostics"]["expanded_strict_matched_creators"] == 4
    assert "expanded_candidate_pool" in result["diagnostics"]["relaxations"]
    assert any(
        path == "/api/xiaohongshu-pgy/api/solar/cooperator/blogger/v2/v1"
        and (params or {}).get("page") == 2
        for _, path, params in client.calls
    )


@pytest.mark.asyncio
async def test_discover_realtime_creators_relaxes_only_soft_filters_after_expansion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "ENABLE_JUSTONE_API", True, raising=False)

    from research import realtime_creator_discovery as mod

    monkeypatch.setattr(mod, "resolve_justone_api_key", lambda: "token")
    monkeypatch.setattr(mod, "_candidate_window", lambda limit: 2)
    monkeypatch.setattr(mod, "_expanded_candidate_window", lambda limit: 4)

    profiles = [
        _xhs_profile("strict"),
        _xhs_profile("activity"),
        _xhs_profile("engagement"),
        _xhs_profile("low-follower", fans=100),
    ]
    metrics = {
        "strict": _xhs_metrics(2, interaction_rate="1.5"),
        "activity": _xhs_metrics(0, interaction_rate="1.5"),
        "engagement": _xhs_metrics(2, interaction_rate=None),
        "low-follower": _xhs_metrics(2, interaction_rate="1.5"),
    }
    client = _PagedJustOneAPIClient(profiles=profiles, metrics=metrics)

    result = await discover_realtime_creators(
        _FakeRepository(),
        {
            "raw_query": "K12",
            "platforms": ["xhs"],
            "limit": 3,
            "follower_min": 200,
            "recent_activity_min": 1,
            "engagement_rate_min": 0.01,
        },
        justone_client_factory=lambda: client,
    )

    ids = {item["creator_id"] for item in result["results"]}
    assert ids == {"strict", "activity", "engagement"}
    assert "low-follower" not in ids
    assert result["diagnostics"]["completion_strategy"] == "soft_relaxed"
    assert result["diagnostics"]["relaxed_matched_creators"] == 2
    assert "activity_pending_verification" in result["diagnostics"]["relaxations"]
    assert "engagement_rate_missing" in result["diagnostics"]["relaxations"]

    by_id = {item["creator_id"]: item for item in result["results"]}
    assert by_id["activity"]["filter_relaxations"] == ["activity_pending_verification"]
    assert by_id["engagement"]["filter_relaxations"] == ["engagement_rate_missing"]
