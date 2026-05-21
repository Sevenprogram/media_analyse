from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def calculate_keyword_heat_signal(
    *,
    keyword: str,
    current_24h: dict[str, float],
    avg_7d: dict[str, float],
    avg_30d: dict[str, float],
    metrics_7d: dict[str, float] | None = None,
    platform_count: int | None = None,
) -> dict[str, Any]:
    content_ratio = _ratio(
        current_24h.get("content_count", 0),
        avg_7d.get("content_count", 0),
    )
    engagement_ratio = _ratio(
        current_24h.get("engagement_total", 0),
        avg_7d.get("engagement_total", 0),
    )
    hot_ratio = _ratio(
        current_24h.get("hot_post_count", 0),
        avg_7d.get("hot_post_count", 0),
    )
    creator_ratio = _ratio(
        current_24h.get("creator_count", 0),
        avg_7d.get("creator_count", 0),
    )

    heat_score = _score_from_ratios(
        [content_ratio, engagement_ratio, hot_ratio, creator_ratio]
    )
    push_score = round(
        min(
            100.0,
            content_ratio * 22
            + engagement_ratio * 28
            + hot_ratio * 30
            + creator_ratio * 20,
        ),
        2,
    )
    cooldown_risk = round(
        max(0.0, 100.0 - push_score)
        if content_ratio < 0.8 or engagement_ratio < 0.8
        else max(0.0, 35.0 - push_score / 4),
        2,
    )
    label = _label(push_score=push_score, cooldown_risk=cooldown_risk)
    sample_quality = _sample_quality(
        current_24h=current_24h,
        metrics_7d=metrics_7d or _estimate_window_metrics(avg_7d, days=7),
        platform_count=platform_count,
    )
    confidence = sample_quality["confidence"]
    return {
        "keyword": keyword,
        "label": label,
        "heat_score": heat_score,
        "push_score": push_score,
        "cooldown_risk": cooldown_risk,
        "confidence": confidence,
        "sample_quality": sample_quality,
        "short_window": {"current_24h": current_24h, "avg_7d": avg_7d},
        "medium_window": {"avg_7d": avg_7d, "avg_30d": avg_30d},
        "evidence": _evidence(
            content_ratio,
            engagement_ratio,
            hot_ratio,
            creator_ratio,
            sample_quality,
        ),
    }


def build_keyword_heat_signal(
    *,
    keyword: str,
    platform: str,
    metrics: dict[str, float],
    ai_judgment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    volume_24h = float(metrics.get("volume_24h") or metrics.get("content_count") or 0)
    volume_7d_avg = float(metrics.get("volume_7d_avg") or metrics.get("avg_content_count") or 0)
    engagement_24h = float(
        metrics.get("engagement_24h") or metrics.get("engagement_total") or 0
    )
    hot_post_rate = float(metrics.get("hot_post_rate") or 0)
    if volume_24h < 3 and engagement_24h < 100:
        label = "insufficient_data"
        score = 0.0
    else:
        growth_ratio = _ratio(volume_24h, volume_7d_avg)
        score = round(
            min(
                100.0,
                growth_ratio * 35
                + hot_post_rate * 40
                + min(engagement_24h / 1000, 25),
            ),
            2,
        )
        if growth_ratio >= 1.8 and hot_post_rate >= 0.2:
            label = "boosting"
        elif growth_ratio <= 0.5:
            label = "cooling"
        else:
            label = "normal"
    ai = ai_judgment or {
        "label": "insufficient_data",
        "confidence": 0,
        "explanation": "AI judgment has not been generated.",
    }
    return {
        "keyword": keyword,
        "platform": platform,
        "rule": {"label": label, "score": score, "metrics": metrics},
        "ai": ai,
        "conflict": bool(ai.get("label") and ai.get("label") != label),
        "evidence": [
            f"24h content volume is {volume_24h:.0f}; 7d average is {volume_7d_avg:.2f}",
            f"24h engagement is {engagement_24h:.0f}",
            f"hot post rate is {hot_post_rate:.2%}",
        ],
        "label": label,
        "heat_score": score,
        "push_score": score if label == "boosting" else max(0.0, score - 20),
        "cooldown_risk": 100.0 - score if label in {"cooling", "limited"} else max(0.0, 40.0 - score / 3),
    }


def aggregate_keyword_heat_from_posts(
    *,
    keyword: str,
    posts: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    matched = [
        post
        for post in posts
        if keyword.lower() in _post_search_text(post)
    ]
    current_24h = _window_metrics(matched, now - timedelta(days=1), now)
    metrics_7d = _window_metrics(matched, now - timedelta(days=7), now)
    metrics_30d = _window_metrics(matched, now - timedelta(days=30), now)
    avg_7d = _average_window(metrics_7d, 7)
    avg_30d = _average_window(metrics_30d, 30)
    return calculate_keyword_heat_signal(
        keyword=keyword,
        current_24h=current_24h,
        avg_7d=avg_7d,
        avg_30d=avg_30d,
        metrics_7d=metrics_7d,
        platform_count=len({str(post.get("platform") or "") for post in matched if post.get("platform")}),
    )


def _ratio(current: float, baseline: float) -> float:
    if baseline <= 0:
        return 2.0 if current > 0 else 0.0
    return current / baseline


def _score_from_ratios(ratios: list[float]) -> float:
    return round(
        min(100.0, sum(min(3.0, ratio) for ratio in ratios) / len(ratios) / 3.0 * 100),
        2,
    )


def _label(*, push_score: float, cooldown_risk: float) -> str:
    if cooldown_risk >= 65:
        return "limited"
    if cooldown_risk >= 45:
        return "cooling"
    if push_score >= 70:
        return "boosting"
    return "normal"


def _estimate_window_metrics(avg_metrics: dict[str, float], *, days: int) -> dict[str, float]:
    return {key: float(value or 0) * days for key, value in avg_metrics.items()}


def _sample_quality(
    *,
    current_24h: dict[str, float],
    metrics_7d: dict[str, float],
    platform_count: int | None,
) -> dict[str, Any]:
    content_24h = int(current_24h.get("content_count") or 0)
    content_7d = int(metrics_7d.get("content_count") or 0)
    creator_7d = int(metrics_7d.get("creator_count") or 0)
    platform_count = int(platform_count or 0)

    confidence = _confidence(
        content_24h=content_24h,
        content_7d=content_7d,
        creator_7d=creator_7d,
    )
    return {
        "confidence": confidence,
        "content_24h": content_24h,
        "content_7d": content_7d,
        "creator_7d": creator_7d,
        "platform_count": platform_count,
        "reason": _confidence_reason(
            confidence=confidence,
            content_24h=content_24h,
            content_7d=content_7d,
            creator_7d=creator_7d,
            platform_count=platform_count,
        ),
    }


def _confidence(
    *,
    content_24h: int,
    content_7d: int,
    creator_7d: int,
) -> str:
    if content_7d >= 100 and creator_7d >= 20 and content_24h >= 10:
        return "high"
    if content_7d >= 30 and creator_7d >= 8 and content_24h >= 3:
        return "medium"
    return "low"


def _confidence_reason(
    *,
    confidence: str,
    content_24h: int,
    content_7d: int,
    creator_7d: int,
    platform_count: int,
) -> str:
    platform_text = (
        f", across {platform_count} platform(s)" if platform_count else ""
    )
    if confidence == "high":
        return (
            f"7d sample is {content_7d} posts from {creator_7d} creators"
            f" with {content_24h} posts in the latest 24h{platform_text}."
        )
    if confidence == "medium":
        return (
            f"7d sample is usable at {content_7d} posts from {creator_7d} creators"
            f"; latest 24h has {content_24h} posts{platform_text}."
        )
    return (
        f"Sample is still thin: {content_7d} posts in 7d, {creator_7d} creators,"
        f" and {content_24h} posts in the latest 24h{platform_text}."
    )


def _evidence(
    content_ratio: float,
    engagement_ratio: float,
    hot_ratio: float,
    creator_ratio: float,
    sample_quality: dict[str, Any],
) -> list[str]:
    return [
        f"24h content volume is {content_ratio:.2f}x the 7d average",
        f"24h engagement is {engagement_ratio:.2f}x the 7d average",
        f"hot post count is {hot_ratio:.2f}x the 7d average",
        f"active creator count is {creator_ratio:.2f}x the 7d average",
        (
            "7d sample is "
            f"{sample_quality['content_7d']} posts from "
            f"{sample_quality['creator_7d']} creators"
        ),
        f"latest 24h sample is {sample_quality['content_24h']} posts",
        f"sample confidence is {sample_quality['confidence']}",
    ]


def _window_metrics(
    posts: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> dict[str, float]:
    window_posts = [
        post
        for post in posts
        if start <= _as_utc(post.get("publish_time") or post.get("created_at") or end) <= end
    ]
    engagement_total = sum(_post_engagement(post) for post in window_posts)
    author_count = len({post.get("author_hash") for post in window_posts if post.get("author_hash")})
    hot_threshold = max(100, engagement_total / max(1, len(window_posts)) * 2)
    return {
        "content_count": float(len(window_posts)),
        "engagement_total": float(engagement_total),
        "hot_post_count": float(sum(1 for post in window_posts if _post_engagement(post) >= hot_threshold)),
        "creator_count": float(author_count),
    }


def _average_window(metrics: dict[str, float], days: int) -> dict[str, float]:
    return {key: round(value / max(1, days), 4) for key, value in metrics.items()}


def _post_engagement(post: dict[str, Any]) -> int:
    engagement = post.get("engagement_json") or post.get("engagement") or {}
    total = 0
    for key in (
        "liked_count",
        "like_count",
        "comment_count",
        "comments_count",
        "share_count",
        "shared_count",
        "collected_count",
        "favorite_count",
    ):
        try:
            total += int(engagement.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _post_search_text(post: dict[str, Any]) -> str:
    engagement = post.get("engagement_json") or post.get("engagement") or {}
    return " ".join(
        [
            str(post.get("title") or ""),
            str(post.get("content") or ""),
            str(engagement.get("source_keyword") or ""),
            str(engagement.get("tag_list") or ""),
        ]
    ).lower()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
