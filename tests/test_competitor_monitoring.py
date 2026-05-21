from datetime import date

import pytest

from research.competitors import CompetitorService


class FakeRepository:
    def __init__(self, capability=None):
        self.capability = capability
        self.snapshot = None

    async def get_platform_capability(self, platform):
        return self.capability

    async def upsert_competitor_account(self, payload):
        return {"id": 1, **payload}

    async def upsert_creator_daily_snapshot(self, payload):
        self.snapshot = payload
        return {"id": 1, **payload}


@pytest.mark.asyncio
async def test_competitor_service_rejects_disabled_monitoring():
    repository = FakeRepository({"enabled": True, "daily_monitor_enabled": False})

    with pytest.raises(ValueError, match="daily monitoring"):
        await CompetitorService(repository).create_competitor(
            {"platform": "xhs", "creator_id": "u1"}
        )


@pytest.mark.asyncio
async def test_competitor_snapshot_aggregates_posts_and_tags():
    repository = FakeRepository()
    result = await CompetitorService(repository).build_daily_snapshot(
        platform="xhs",
        creator_id="u1",
        snapshot_date=date(2026, 5, 20),
        posts=[
            {"platform_post_id": "p1", "title": "A", "engagement_json": {"liked_count": 100, "comment_count": 2}},
            {"platform_post_id": "p2", "title": "B", "engagement_json": {"liked_count": 10, "share_count": 1}},
        ],
        entity_tags=[{"tag_id": 1}, {"tag_id": 1}, {"tag_id": 2}],
        follower_count=1000,
    )

    assert result["new_post_count"] == 2
    assert result["total_like_count"] == 110
    assert result["tag_distribution_json"] == {"1": 2, "2": 1}
