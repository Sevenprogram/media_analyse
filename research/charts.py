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


def build_daily_comment_trend(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = defaultdict(int)
    for comment in comments:
        publish_time = comment.get("publish_time")
        if not isinstance(publish_time, datetime):
            continue
        counts[publish_time.date().isoformat()] += 1
    return [{"date": date, "comments": counts[date]} for date in sorted(counts)]


def build_keyword_ranking(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter()
    for post in posts:
        engagement = post.get("engagement_json") or {}
        keyword = engagement.get("source_keyword")
        if keyword:
            counts[str(keyword)] += 1
    return [{"keyword": keyword, "count": count} for keyword, count in counts.most_common()]


def build_ai_distribution(
    ai_results: list[dict[str, Any]], *, field: str
) -> list[dict[str, Any]]:
    counts = Counter()
    for item in ai_results:
        result = item.get("result_json") or {}
        value = result.get(field)
        if isinstance(value, list):
            for part in value:
                counts[str(part)] += 1
        elif value:
            counts[str(value)] += 1
    return [{"name": name, "value": value} for name, value in counts.most_common()]


def build_chart_summary(
    *,
    posts: list[dict[str, Any]],
    comments: list[dict[str, Any]],
    ai_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ai_results = ai_results or []
    return {
        "platform_counts": build_platform_counts(posts, comments),
        "post_trend": build_daily_post_trend(posts),
        "comment_trend": build_daily_comment_trend(comments),
        "keyword_ranking": build_keyword_ranking(posts),
        "sentiment_distribution": build_ai_distribution(ai_results, field="sentiment"),
        "stance_distribution": build_ai_distribution(ai_results, field="stance"),
        "topic_tag_ranking": build_ai_distribution(ai_results, field="topic_tags"),
    }
