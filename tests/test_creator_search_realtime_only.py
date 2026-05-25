from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research import creator_search


class _NoLocalSearchRepository:
    def __init__(self) -> None:
        self.local_calls: list[str] = []

    async def list_tag_definitions(self, **kwargs):
        self.local_calls.append("list_tag_definitions")
        raise AssertionError("realtime_only must not load local tag definitions")

    async def list_verticals(self, **kwargs):
        self.local_calls.append("list_verticals")
        raise AssertionError("realtime_only must not load local verticals")

    async def list_creator_profiles(self, **kwargs):
        self.local_calls.append("list_creator_profiles")
        raise AssertionError("realtime_only must not load local creator profiles")

    async def list_posts_by_creator(self, **kwargs):
        self.local_calls.append("list_posts_by_creator")
        raise AssertionError("realtime_only must not load local creator posts")


@pytest.mark.asyncio
async def test_realtime_only_search_skips_local_database_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _NoLocalSearchRepository()
    calls: list[dict] = []

    async def fake_discover_realtime_creators(repository, request: dict):
        calls.append(request)
        return {
            "diagnostics": {
                "enabled": True,
                "status": "ok",
                "platforms": request.get("platforms") or [],
                "unsupported_platforms": [],
                "created_profiles": 1,
                "created_candidates": 1,
                "persisted_creators": 1,
                "requested_ratio": 0,
                "selected_count": 0,
                "selected_ratio": 0,
                "error": None,
            },
            "results": [
                {
                    "platform": "xhs",
                    "creator_id": "xhs-creator-1",
                    "display_name": "K12 Parents",
                    "follower_count": 36000,
                    "recent_post_count_30d": 5,
                    "avg_engagement_rate": 0.0034,
                    "hot_post_rate": 0.2,
                    "match_score": 88,
                    "matched_tags": [{"source": "realtime", "term": "K12"}],
                    "evidence": [],
                    "representative_posts": [],
                    "source_type": "realtime",
                    "source_labels": ["Realtime"],
                    "realtime_unverified": False,
                }
            ],
        }

    monkeypatch.setattr(creator_search, "discover_realtime_creators", fake_discover_realtime_creators)

    result = await creator_search.search_creators(
        repo,
        {
            "raw_query": "K12 family",
            "search_scope": "realtime_only",
            "platforms": ["xhs"],
            "limit": 10,
            "include_realtime": False,
            "follower_min": 2000,
            "recent_activity_min": 1,
        },
    )

    assert repo.local_calls == []
    assert len(calls) == 1
    assert calls[0]["include_realtime"] is True
    assert result["diagnostics"]["search_scope"] == "realtime_only"
    assert result["diagnostics"]["profile_count"] == 0
    assert result["realtime"]["selected_count"] == 1
    assert result["realtime"]["requested_ratio"] == 100
    assert result["results"][0]["creator_id"] == "xhs-creator-1"
