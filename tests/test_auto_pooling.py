import pytest

from research.auto_pooling import auto_pool_a_tier_candidates


@pytest.mark.asyncio
async def test_auto_pool_adds_only_a_tier_candidates_and_respects_cap():
    class FakeRepository:
        def __init__(self):
            self.added = []

        async def get_monitor_pool(self, pool_id):
            return {"id": pool_id, "name": "A tier", "schedule_interval_minutes": 720}

        async def list_monitor_pool_creators(self, pool_id, enabled_only=False):
            return []

        async def add_monitor_pool_creators(self, pool_id, creators):
            self.added.extend(creators)
            return [{"id": index + 1, "pool_id": pool_id, **creator} for index, creator in enumerate(creators)]

        async def create_job(self, payload):
            return {"id": 99, **payload}

        async def update_monitor_pool(self, pool_id, payload):
            return {"id": pool_id, **payload}

    repository = FakeRepository()

    result = await auto_pool_a_tier_candidates(
        repository,
        pool_id=1,
        daily_cap=1,
        candidates=[
            {"platform": "xhs", "creator_id": "a", "match_score": 80, "matched_tags": [{}], "evidence": {"representative_posts": [{}]}},
            {"platform": "xhs", "creator_id": "b", "match_score": 80, "matched_tags": [{}], "evidence": {"representative_posts": [{}]}},
            {"platform": "xhs", "creator_id": "c", "match_score": 50, "evidence": {}},
        ],
    )

    assert [item["creator_id"] for item in result["selected"]] == ["a"]
    assert result["added"][0]["creator_id"] == "a"
    assert {item["skip_reason"] for item in result["skipped"]} == {"daily_cap_reached", "not_a_tier"}
