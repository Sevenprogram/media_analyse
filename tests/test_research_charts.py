from datetime import datetime, timezone

from research.charts import build_daily_post_trend, build_platform_counts


def test_build_platform_counts_counts_posts_and_comments():
    posts = [{"platform": "wb"}, {"platform": "wb"}, {"platform": "zhihu"}]
    comments = [{"platform": "wb"}, {"platform": "zhihu"}, {"platform": "zhihu"}]

    result = build_platform_counts(posts, comments)

    assert result == [
        {"platform": "wb", "posts": 2, "comments": 1},
        {"platform": "zhihu", "posts": 1, "comments": 2},
    ]


def test_build_daily_post_trend_groups_by_date():
    posts = [
        {"publish_time": datetime(2026, 1, 1, 8, tzinfo=timezone.utc)},
        {"publish_time": datetime(2026, 1, 1, 9, tzinfo=timezone.utc)},
        {"publish_time": datetime(2026, 1, 2, 9, tzinfo=timezone.utc)},
        {"publish_time": None},
    ]

    result = build_daily_post_trend(posts)

    assert result == [
        {"date": "2026-01-01", "posts": 2},
        {"date": "2026-01-02", "posts": 1},
    ]
