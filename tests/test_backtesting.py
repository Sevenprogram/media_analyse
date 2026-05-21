from datetime import date, datetime, timezone

import pytest

from research.backtesting import run_backtest


class FakeRepository:
    async def list_all_posts(self, platform=None, start_at=None, end_at=None, limit=None):
        del start_at, end_at, limit
        posts = [
            {
                "id": 1,
                "platform": "xhs",
                "platform_post_id": "x1",
                "title": "K12教育 单亲妈妈 规划",
                "content": "小学提分和家庭陪伴",
                "publish_time": datetime(2026, 5, 18, 9, tzinfo=timezone.utc),
                "engagement_json": {"like_count": 180, "comment_count": 30},
                "author_hash": "a1",
            },
            {
                "id": 2,
                "platform": "dy",
                "platform_post_id": "d1",
                "title": "K12教育 家长焦虑",
                "content": "单亲妈妈如何选择课程",
                "publish_time": datetime(2026, 5, 19, 21, tzinfo=timezone.utc),
                "engagement_json": {"like_count": 260, "comment_count": 50},
                "author_hash": "a2",
            },
        ]
        if platform:
            posts = [item for item in posts if item["platform"] == platform]
        return posts


@pytest.mark.asyncio
async def test_run_backtest_replays_daily_keyword_heat():
    report = await run_backtest(
        FakeRepository(),
        {
            "id": 1,
            "scenario": "K12教育+单亲妈妈",
            "keywords": ["K12教育", "单亲妈妈"],
            "platforms": ["xhs", "dy"],
            "start_date": date(2026, 5, 18),
            "end_date": date(2026, 5, 20),
            "use_tikhub_backfill": False,
            "replay_daily": True,
            "research_job_id": None,
        },
    )

    assert report["sample"]["matched_posts"] == 2
    assert len(report["daily"]) == 3
    assert report["daily"][-1]["sample_count"] == 2
    assert report["latest_keywords"][0]["keyword"] == "K12教育"
    assert report["calibration_notes"]
