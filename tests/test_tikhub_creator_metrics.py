import pytest

from research.tikhub_creator_metrics import enrich_creator_metrics_from_tikhub, native_creator_id


def test_native_creator_id_from_profile_url():
    assert (
        native_creator_id("xhs", {"profile_url": "https://www.xiaohongshu.com/user/profile/abc123?x=1"})
        == "abc123"
    )
    assert native_creator_id("dy", {"profile_url": "https://www.douyin.com/user/sec-user"}) == "sec-user"


@pytest.mark.asyncio
async def test_enrich_creator_metrics_updates_research_profile(monkeypatch):
    class FakeClient:
        async def request(self, method, path, *, params=None, json=None):
            return {
                "user": {
                    "id": "native-xhs",
                    "nickname": "Teacher A",
                    "followers_count": 1000,
                    "liked_count": 50000,
                    "collected_count": 300,
                    "notes_count": 20,
                }
            }

    class FakeRepository:
        def __init__(self):
            self.payload = None

        async def get_creator_profile(self, platform, creator_id):
            return {
                "platform": platform,
                "creator_id": creator_id,
                "post_count": 2,
                "tag_summary_json": {"1": {"count": 1}},
            }

        async def upsert_creator_profile(self, payload):
            self.payload = payload
            return payload

    saved = {}

    async def fake_save_creator(user_id, creator):
        saved["user_id"] = user_id
        saved["creator"] = creator

    monkeypatch.setattr("research.tikhub_creator_metrics.xhs_store.save_creator", fake_save_creator)
    repo = FakeRepository()

    result = await enrich_creator_metrics_from_tikhub(
        repo,
        [
            {
                "platform": "xhs",
                "creator_id": "xhs_hash",
                "profile_url": "https://www.xiaohongshu.com/user/profile/native-xhs",
            }
        ],
        client=FakeClient(),
    )

    assert result["enriched_count"] == 1
    assert saved["user_id"] == "native-xhs"
    assert repo.payload["follower_count"] == 1000
    assert repo.payload["post_count"] == 20
    assert repo.payload["tag_summary_json"]["profile_metrics"]["total_like_count"] == 50000
    assert repo.payload["tag_summary_json"]["profile_metrics"]["total_collect_count"] == 300


@pytest.mark.asyncio
async def test_enrich_douyin_metrics_uses_user_search_fallback(monkeypatch):
    class FakeClient:
        async def request(self, method, path, *, params=None, json=None):
            if path.endswith("fetch_user_profile_by_uid"):
                return {
                    "user": {
                        "uid": "native-dy",
                        "nickname": "Teacher B",
                        "follow_info": {"follower_count": 100, "following_count": 9},
                    }
                }
            return {
                "user_list": [
                    {
                        "user_id": "sec-dy",
                        "nick_name": "Teacher B",
                        "fans_cnt": 1200,
                        "like_cnt": 88000,
                        "publish_cnt": 35,
                    }
                ]
            }

    class FakeRepository:
        def __init__(self):
            self.payload = None

        async def get_creator_profile(self, platform, creator_id):
            return {"platform": platform, "creator_id": creator_id, "tag_summary_json": {}}

        async def upsert_creator_profile(self, payload):
            self.payload = payload
            return payload

    saved = {}

    async def fake_save_creator(user_id, creator):
        saved["user_id"] = user_id
        saved["creator"] = creator

    monkeypatch.setattr("research.tikhub_creator_metrics.douyin_store.save_creator", fake_save_creator)
    repo = FakeRepository()

    result = await enrich_creator_metrics_from_tikhub(
        repo,
        [
            {
                "platform": "dy",
                "creator_id": "dy_hash",
                "display_name": "Teacher B",
                "profile_url": "https://www.douyin.com/user/sec-dy",
                "evidence": [{"engagement": {"author_id": "native-dy", "sec_uid": "sec-dy"}}],
            }
        ],
        client=FakeClient(),
    )

    assert result["enriched_count"] == 1
    assert saved["creator"]["user"]["total_favorited"] == 88000
    assert repo.payload["follower_count"] == 1200
    assert repo.payload["post_count"] == 35
    assert repo.payload["tag_summary_json"]["profile_metrics"]["total_like_count"] == 88000
