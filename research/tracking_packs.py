from __future__ import annotations

from datetime import date
from typing import Any


DEFAULT_DAILY_SAMPLE_LIMIT = 150
DEFAULT_TRACKING_INTERVAL_MINUTES = 24 * 60


def build_tracking_pack(
    *,
    scene_pack: dict[str, Any],
    keywords: list[dict[str, Any]],
    platforms: list[str] | None = None,
    daily_sample_limit_per_keyword: int = DEFAULT_DAILY_SAMPLE_LIMIT,
) -> dict[str, Any]:
    requested_platforms = platforms or scene_pack.get("default_platforms") or []
    positive_keywords: list[dict[str, Any]] = []
    negative_keywords: list[dict[str, Any]] = []
    platform_keywords: dict[str, list[dict[str, Any]]] = {
        platform: [] for platform in requested_platforms
    }

    for item in keywords:
        if not item.get("enabled", True):
            continue
        keyword_platform = item.get("platform")
        if keyword_platform and requested_platforms and keyword_platform not in requested_platforms:
            continue
        normalized = _keyword_payload(item)
        if normalized["keyword_type"] == "negative":
            negative_keywords.append(normalized)
            continue
        if keyword_platform:
            platform_keywords.setdefault(keyword_platform, []).append(normalized)
        else:
            positive_keywords.append(normalized)

    effective_by_platform: dict[str, list[str]] = {}
    platforms_to_expand = requested_platforms or sorted(platform_keywords.keys()) or ["all"]
    for platform in platforms_to_expand:
        platform_terms = positive_keywords + platform_keywords.get(platform, [])
        effective_by_platform[platform] = _dedupe_keywords(
            [item["keyword"] for item in platform_terms]
        )

    return {
        "scene_pack_id": scene_pack["id"],
        "name": scene_pack.get("name"),
        "vertical_id": scene_pack.get("vertical_id"),
        "platforms": platforms_to_expand,
        "daily_sample_limit_per_keyword": daily_sample_limit_per_keyword,
        "positive_keywords": positive_keywords,
        "negative_keywords": negative_keywords,
        "platform_keywords": platform_keywords,
        "effective_keywords_by_platform": effective_by_platform,
        "enabled": bool(scene_pack.get("enabled", True)),
    }


async def create_daily_sampling_jobs(
    repository,
    *,
    scene_pack_id: int,
    platforms: list[str] | None = None,
    daily_sample_limit_per_keyword: int = DEFAULT_DAILY_SAMPLE_LIMIT,
    schedule_interval_minutes: int = DEFAULT_TRACKING_INTERVAL_MINUTES,
    today: date | None = None,
) -> dict[str, Any]:
    scene_pack = await repository.get_scene_pack(scene_pack_id)
    if scene_pack is None:
        raise ValueError(f"Scene pack not found: {scene_pack_id}")
    keywords = await repository.list_scene_pack_keywords(
        scene_pack_ids=[scene_pack_id],
        enabled_only=True,
    )
    tracking_pack = build_tracking_pack(
        scene_pack=scene_pack,
        keywords=keywords,
        platforms=platforms,
        daily_sample_limit_per_keyword=daily_sample_limit_per_keyword,
    )
    today = today or date.today()
    jobs = []
    for platform, terms in tracking_pack["effective_keywords_by_platform"].items():
        if platform == "all" or not terms:
            continue
        job = await repository.create_job(
            {
                "name": f"{tracking_pack['name']} - {platform} daily sampling",
                "topic": f"tracking_pack:{scene_pack_id}",
                "platforms": [platform],
                "collection_mode": "search",
                "keywords": terms,
                "target_ids": [],
                "creator_ids": [],
                "start_date": today,
                "end_date": today,
                "status": "pending",
                "comment_policy": {
                    "enable_comments": False,
                    "enable_sub_comments": False,
                    "max_posts_per_job": daily_sample_limit_per_keyword * len(terms),
                },
                "raw_record_mode": "minimal",
                "anonymize_authors": True,
                "schedule_enabled": True,
                "schedule_interval_minutes": schedule_interval_minutes,
            }
        )
        jobs.append(job)
    return {
        "scene_pack": scene_pack,
        "tracking_pack": tracking_pack,
        "jobs": jobs,
        "created": len(jobs),
    }


def _keyword_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "keyword": str(item.get("keyword") or "").strip(),
        "keyword_type": item.get("keyword_type") or "secondary",
        "platform": item.get("platform"),
        "weight": float(item.get("weight") or 1.0),
        "reason": item.get("reason"),
        "usage_flags": item.get("usage_flags") or [],
    }


def _dedupe_keywords(keywords: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for keyword in keywords:
        normalized = keyword.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
