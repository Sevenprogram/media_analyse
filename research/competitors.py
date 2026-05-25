from collections import Counter
from datetime import date, datetime, timedelta, timezone
import re
from typing import Any

import jieba

from research.enums import (
    PLATFORM_SIGNAL_BOOST,
    PLATFORM_SIGNAL_COOLING,
    PLATFORM_SIGNAL_NORMAL,
)

KEYWORD_TOKEN_PATTERN = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]{2,}")
ASIA_SHANGHAI = timezone(timedelta(hours=8))
KEYWORD_STOPWORDS = {
    "我们",
    "你们",
    "他们",
    "这个",
    "那个",
    "一个",
    "一些",
    "因为",
    "所以",
    "就是",
    "真的",
    "已经",
    "现在",
    "今天",
    "最近",
    "当前",
    "一下",
    "一下子",
    "什么",
    "怎么",
    "还是",
    "自己",
    "可以",
    "不是",
    "没有",
    "内容",
    "视频",
    "图文",
}


class CompetitorService:
    def __init__(self, repository):
        self.repository = repository

    async def create_competitor(self, payload: dict[str, Any]) -> dict[str, Any]:
        capability = await self.repository.get_platform_capability(payload["platform"])
        if capability and (not capability["enabled"] or not capability["daily_monitor_enabled"]):
            raise ValueError(f"Platform is not enabled for daily monitoring: {payload['platform']}")
        return await self.repository.upsert_competitor_account(payload)

    async def build_daily_snapshot(
        self,
        *,
        platform: str,
        creator_id: str,
        snapshot_date: date,
        posts: list[dict[str, Any]],
        entity_tags: list[dict[str, Any]],
        follower_count: int | None = None,
    ) -> dict[str, Any]:
        totals = [_post_engagement(post) for post in posts]
        threshold = max(100, (sum(totals) / max(1, len(totals))) * 2)
        tag_distribution = Counter(str(tag["tag_id"]) for tag in entity_tags)
        top_posts = sorted(
            [
                {
                    "platform_post_id": post.get("platform_post_id"),
                    "title": post.get("title"),
                    "engagement_total": _post_engagement(post),
                    "url": post.get("url"),
                }
                for post in posts
            ],
            key=lambda item: item["engagement_total"],
            reverse=True,
        )[:10]
        payload = {
            "platform": platform,
            "creator_id": creator_id,
            "snapshot_date": snapshot_date,
            "follower_count": follower_count,
            "total_like_count": sum(_metric(post, "liked_count") for post in posts),
            "total_comment_count": sum(
                _metric(post, "comment_count") + _metric(post, "comments_count")
                for post in posts
            ),
            "total_share_count": sum(
                _metric(post, "share_count") + _metric(post, "shared_count")
                for post in posts
            ),
            "new_post_count": len(posts),
            "hot_post_count": sum(1 for total in totals if total >= threshold),
            "tag_distribution_json": dict(tag_distribution),
            "top_posts_json": top_posts,
        }
        return await self.repository.upsert_creator_daily_snapshot(payload)


def calculate_keyword_opportunities(
    *,
    vertical_id: int,
    tag_definitions: list[dict[str, Any]],
    entity_tags: list[dict[str, Any]],
    creator_profiles: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    platform: str | None = None,
) -> list[dict[str, Any]]:
    tags_by_id = {int(tag["id"]): tag for tag in tag_definitions}
    tag_hit_counts = Counter(int(tag["tag_id"]) for tag in entity_tags)
    creator_counts = Counter()
    for profile in creator_profiles:
        summary = profile.get("tag_summary_json") or {}
        for tag_id in summary:
            try:
                creator_counts[int(tag_id)] += 1
            except ValueError:
                continue
    snapshot_distribution = Counter()
    for snapshot in snapshots:
        if platform and snapshot.get("platform") != platform:
            continue
        for tag_id, count in (snapshot.get("tag_distribution_json") or {}).items():
            snapshot_distribution[int(tag_id)] += int(count)

    opportunities = []
    for tag_id, tag in tags_by_id.items():
        heat = float(tag_hit_counts[tag_id] + snapshot_distribution[tag_id])
        competition = float(creator_counts[tag_id])
        supply_gap = max(0.0, heat - competition)
        growth = float(snapshot_distribution[tag_id])
        platform_signal = _platform_signal(heat=heat, growth=growth)
        opportunities.append(
            {
                "vertical_id": vertical_id,
                "platform": platform,
                "tag_id": tag_id,
                "tag_name": tag.get("tag_name"),
                "heat_score": round(heat, 4),
                "growth_score": round(growth, 4),
                "competition_score": round(competition, 4),
                "supply_gap_score": round(supply_gap, 4),
                "platform_signal": platform_signal,
                "evidence": {
                    "tag_hits": tag_hit_counts[tag_id],
                    "creator_count": creator_counts[tag_id],
                    "snapshot_tag_hits": snapshot_distribution[tag_id],
                },
            }
        )
    opportunities.sort(key=lambda item: (item["supply_gap_score"], item["heat_score"]), reverse=True)
    return opportunities


def build_competitor_composition_snapshot(
    *,
    competitor_account_id: int,
    snapshot_date,
    platform: str,
    posts: list[dict[str, Any]],
    entity_tags: list[dict[str, Any]],
    keywords: list[str],
) -> dict[str, Any]:
    composition = build_competitor_composition(
        posts=posts,
        entity_tags=entity_tags,
        keywords=keywords,
    )
    return {
        "competitor_id": competitor_account_id,
        "snapshot_date": snapshot_date,
        "platform": platform,
        "total_flow_count": composition["total_interaction"],
        "keyword_distribution": composition["keyword_distribution"],
        "tag_distribution": composition["tag_distribution"],
        "content_type_distribution": composition["content_type_distribution"],
        "publish_time_distribution": composition["publish_time_distribution"],
        "hot_post_rate": composition["hot_post_rate"],
        "interaction_structure": composition["interaction_structure"],
        "evidence": {
            **composition["evidence"],
            "new_post_count": composition["new_post_count"],
            "interaction_structure": composition["interaction_structure"],
        },
    }


def build_competitor_composition(
    *,
    posts: list[dict[str, Any]],
    entity_tags: list[dict[str, Any]],
    keywords: list[str],
    hot_threshold: int | None = None,
) -> dict[str, Any]:
    keyword_distribution = Counter()
    content_type_distribution = Counter()
    publish_time_distribution = Counter()
    interaction_structure = Counter()
    normalized_keywords = [str(keyword).strip() for keyword in keywords if str(keyword).strip()]
    for post in posts:
        text = _post_text(post)
        lowered = text.lower()
        for keyword in normalized_keywords:
            if keyword.lower() in lowered:
                keyword_distribution[keyword] += 1
        content_type_distribution[_resolved_content_type(post)] += 1
        publish_time = _as_asia_shanghai(post.get("publish_time"))
        hour = getattr(publish_time, "hour", None)
        if hour is not None:
            publish_time_distribution[_publish_time_bucket(hour)] += 1
        else:
            publish_time_distribution["unknown"] += 1
        interaction_structure["like"] += _metric(post, "liked_count")
        interaction_structure["comment"] += _metric(post, "comment_count") + _metric(
            post, "comments_count"
        )
        interaction_structure["share"] += _metric(post, "share_count") + _metric(
            post, "shared_count"
        )
        interaction_structure["collect"] += _metric(post, "collected_count")
    if not keyword_distribution:
        keyword_distribution.update(_fallback_keyword_distribution(posts))
    tag_distribution = Counter(str(tag["tag_id"]) for tag in entity_tags)
    totals = [_post_engagement(post) for post in posts]
    threshold = hot_threshold or max(100, int((sum(totals) / max(1, len(totals))) * 2))
    hot_count = sum(1 for total in totals if total >= threshold)
    return {
        "new_post_count": len(posts),
        "total_interaction": sum(totals),
        "keyword_distribution": dict(keyword_distribution),
        "tag_distribution": dict(tag_distribution),
        "content_type_distribution": dict(content_type_distribution),
        "publish_time_distribution": dict(publish_time_distribution),
        "interaction_structure": dict(interaction_structure),
        "hot_post_rate": round(hot_count / max(1, len(posts)), 4),
        "evidence": {
            "post_count": len(posts),
            "hot_threshold": threshold,
            "top_posts": _top_post_evidence(posts),
        },
    }


def _platform_signal(*, heat: float, growth: float) -> str:
    if heat >= 10 and growth >= 5:
        return PLATFORM_SIGNAL_BOOST
    if heat <= 1 and growth <= 0:
        return PLATFORM_SIGNAL_COOLING
    return PLATFORM_SIGNAL_NORMAL


def _post_engagement(post: dict[str, Any]) -> int:
    return sum(
        _metric(post, key)
        for key in (
            "liked_count",
            "comment_count",
            "comments_count",
            "share_count",
            "shared_count",
            "collected_count",
        )
    )


def _metric(post: dict[str, Any], key: str) -> int:
    engagement = post.get("engagement_json") or {}
    try:
        return int(engagement.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _publish_time_bucket(hour: int) -> str:
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 24:
        return "night"
    return "late_night"


def _as_asia_shanghai(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    resolved = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return resolved.astimezone(ASIA_SHANGHAI)


def _top_post_evidence(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "platform_post_id": post.get("platform_post_id"),
            "title": post.get("title"),
            "content_type": _resolved_content_type(post),
            "publish_time": _json_safe_time(post.get("publish_time")),
            "engagement_total": _post_engagement(post),
            "url": post.get("url"),
        }
        for post in sorted(posts, key=_post_engagement, reverse=True)[:10]
    ]


def _json_safe_time(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _post_text(post: dict[str, Any]) -> str:
    return f"{post.get('title') or ''} {post.get('content') or ''}".strip()


def _fallback_keyword_distribution(posts: list[dict[str, Any]]) -> Counter:
    combined = "\n".join(_post_text(post) for post in posts if _post_text(post))
    if not combined:
        return Counter()

    counts = Counter()
    for token in jieba.cut(combined, cut_all=False):
        normalized = str(token).strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in KEYWORD_STOPWORDS:
            continue
        if not KEYWORD_TOKEN_PATTERN.fullmatch(normalized):
            continue
        counts[normalized] += 1
    return Counter(dict(counts.most_common(20)))


def _resolved_content_type(post: dict[str, Any]) -> str:
    explicit = str(post.get("content_type") or "").strip().lower()
    if explicit and explicit != "unknown":
        return explicit

    engagement = post.get("engagement_json") or post.get("engagement") or {}
    if engagement.get("video_duration") or engagement.get("duration"):
        return "video"

    platform = str(post.get("platform") or "").strip().lower()
    if platform in {"dy", "douyin", "bili", "bilibili"}:
        return "video"
    if platform in {"xhs", "xiaohongshu"}:
        return "note"
    return explicit or "unknown"
