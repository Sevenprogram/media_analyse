import pytest

from research.realtime_creator_discovery import discover_realtime_creators


class FakeTikHubClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def request(self, method, path, *, params=None, json=None):
        self.calls.append({"method": method, "path": path, "params": params, "json": json})
        keyword = (params or json or {}).get("keyword")
        return self.responses.get(keyword, [])

    async def close(self):
        pass


class FakeRepository:
    def __init__(self):
        self.profiles = []
        self.candidates = []

    async def upsert_creator_profile(self, payload):
        self.profiles.append(payload)
        return {"id": len(self.profiles), **payload}

    async def upsert_creator_candidate(self, payload):
        self.candidates.append(payload)
        return {"id": len(self.candidates), **payload}


@pytest.mark.asyncio
async def test_discover_realtime_creators_persists_xhs_author():
    repository = FakeRepository()
    client = FakeTikHubClient(
        {
            "K12": [
                {
                    "note": {
                        "id": "note-1",
                        "title": "K12 learning",
                        "desc": "single mom study plan",
                        "user": {
                            "user_id": "xhs-u1",
                            "nickname": "Teacher X",
                            "desc": "K12 teacher",
                            "fans": 3300,
                            "notes_count": 42,
                        },
                        "interact_info": {
                            "liked_count": 100,
                            "comment_count": 12,
                            "collected_count": 8,
                        },
                    }
                }
            ]
        }
    )

    result = await discover_realtime_creators(
        repository,
        {
            "raw_query": "K12",
            "platforms": ["xhs"],
            "limit": 20,
            "selected_vertical_id": 7,
        },
        client_factory=lambda: client,
    )

    assert result["diagnostics"]["status"] == "ok"
    assert result["diagnostics"]["created_profiles"] == 1
    assert result["diagnostics"]["created_candidates"] == 1
    assert client.calls[0]["params"]["page"] == 1
    assert result["results"][0]["platform"] == "xhs"
    assert result["results"][0]["creator_id"] == "xhs-u1"
    assert result["results"][0]["display_name"] == "Teacher X"
    assert result["results"][0]["source_type"] == "realtime"
    assert result["results"][0]["source_labels"] == ["Realtime"]
    assert result["results"][0]["realtime_unverified"] is True
    assert repository.profiles[0]["profile_url"].endswith("/xhs-u1")
    assert repository.candidates[0]["pool_name"] == "realtime"
    assert repository.candidates[0]["vertical_id"] == 7


@pytest.mark.asyncio
async def test_discover_realtime_creators_persists_douyin_author():
    repository = FakeRepository()
    client = FakeTikHubClient(
        {
            "K12": {
                "data": [
                    {
                        "aweme_info": {
                            "aweme_id": "aweme-1",
                            "desc": "K12 parent education",
                            "author": {
                                "uid": "dy-u1",
                                "sec_uid": "dy-sec-1",
                                "nickname": "Teacher D",
                                "signature": "K12 study coach",
                                "followers_count": 8600,
                                "aweme_count": 15,
                            },
                            "statistics": {
                                "digg_count": 220,
                                "comment_count": 30,
                                "collect_count": 11,
                                "share_count": 5,
                            },
                        }
                    }
                ]
            }
        }
    )

    result = await discover_realtime_creators(
        repository,
        {"raw_query": "K12", "platforms": ["dy"], "limit": 20},
        client_factory=lambda: client,
    )

    assert result["diagnostics"]["status"] == "ok"
    assert result["results"][0]["platform"] == "dy"
    assert result["results"][0]["creator_id"] == "dy-sec-1"
    assert result["results"][0]["display_name"] == "Teacher D"
    assert result["results"][0]["profile_url"].endswith("/dy-sec-1")
    assert repository.profiles[0]["follower_count"] == 8600
    assert repository.candidates[0]["matched_tags_json"] == [
        {"source": "tikhub_realtime", "keyword": "K12"}
    ]


@pytest.mark.asyncio
async def test_discover_realtime_creators_reports_unsupported_platforms():
    repository = FakeRepository()
    client = FakeTikHubClient({"K12": []})

    result = await discover_realtime_creators(
        repository,
        {"raw_query": "K12", "platforms": ["bili"], "limit": 20},
        client_factory=lambda: client,
    )

    assert result["results"] == []
    assert result["diagnostics"]["status"] == "skipped"
    assert result["diagnostics"]["unsupported_platforms"] == ["bili"]


@pytest.mark.asyncio
async def test_discover_realtime_creators_limits_persisted_creators():
    repository = FakeRepository()
    client = FakeTikHubClient(
        {
            "K12": [
                {
                    "note": {
                        "id": f"note-{index}",
                        "title": f"K12 creator {index}",
                        "desc": "parent education",
                        "user": {
                            "user_id": f"xhs-u{index}",
                            "nickname": f"Teacher {index}",
                            "fans": 1000 + index,
                        },
                        "interact_info": {
                            "liked_count": 100 * index,
                            "comment_count": 10,
                            "collected_count": 5,
                        },
                    }
                }
                for index in range(1, 4)
            ]
        }
    )

    result = await discover_realtime_creators(
        repository,
        {"raw_query": "K12", "platforms": ["xhs"], "limit": 2},
        client_factory=lambda: client,
    )

    assert len(result["results"]) == 2
    assert len(repository.profiles) == 2
    assert len(repository.candidates) == 2
    assert result["diagnostics"]["limit"] == 2
    assert result["diagnostics"]["matched_creators"] == 3
    assert result["diagnostics"]["persisted_creators"] == 2
