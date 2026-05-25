from __future__ import annotations

from typing import Any


ENGAGEMENT_KEYS = (
    "liked_count",
    "comment_count",
    "comments_count",
    "share_count",
    "shared_count",
    "collected_count",
    "favorite_count",
)


def to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def engagement_total_from_mapping(engagement: dict[str, Any] | None) -> int:
    payload = engagement or {}
    return sum(to_int(payload.get(key)) for key in ENGAGEMENT_KEYS)


def engagement_total_from_post(
    post: dict[str, Any],
    *,
    engagement_fields: tuple[str, ...] = ("engagement_json", "engagement"),
) -> int:
    for field in engagement_fields:
        value = post.get(field)
        if isinstance(value, dict):
            return engagement_total_from_mapping(value)
    return 0


def avg_engagement_rate_from_posts(
    posts: list[dict[str, Any]],
    follower_count: Any,
    *,
    engagement_fields: tuple[str, ...] = ("engagement_json", "engagement"),
) -> float | None:
    followers = to_int(follower_count)
    if not posts or followers <= 0:
        return None
    total = sum(
        engagement_total_from_post(post, engagement_fields=engagement_fields)
        for post in posts
    )
    return round(total / max(1, followers * len(posts)), 6)


def hot_post_rate_from_posts(
    posts: list[dict[str, Any]],
    *,
    engagement_fields: tuple[str, ...] = ("engagement_json", "engagement"),
) -> float | None:
    if not posts:
        return None
    totals = [
        engagement_total_from_post(post, engagement_fields=engagement_fields)
        for post in posts
    ]
    if not totals:
        return 0.0
    threshold = max(100, sum(totals) / len(totals) * 2)
    hot = sum(1 for total in totals if total >= threshold)
    return round(hot / len(posts), 6)
