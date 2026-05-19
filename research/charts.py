from collections import Counter, defaultdict
from datetime import datetime
from typing import Any


def build_platform_counts(
    posts: list[dict[str, Any]], comments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    post_counts = Counter(item["platform"] for item in posts)
    comment_counts = Counter(item["platform"] for item in comments)
    platforms = sorted(set(post_counts) | set(comment_counts))
    return [
        {
            "platform": platform,
            "posts": post_counts.get(platform, 0),
            "comments": comment_counts.get(platform, 0),
        }
        for platform in platforms
    ]


def build_daily_post_trend(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = defaultdict(int)
    for post in posts:
        publish_time = post.get("publish_time")
        if not isinstance(publish_time, datetime):
            continue
        counts[publish_time.date().isoformat()] += 1
    return [{"date": date, "posts": counts[date]} for date in sorted(counts)]
