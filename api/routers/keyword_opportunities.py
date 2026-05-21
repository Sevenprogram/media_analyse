from collections import Counter

from fastapi import APIRouter, HTTPException
from datetime import date

from pydantic import BaseModel, Field

from api.routers.research import require_research_database
from research.competitors import calculate_keyword_opportunities
from research.keyword_heat import (
    aggregate_keyword_heat_from_posts,
    build_keyword_heat_signal,
    calculate_keyword_heat_signal,
)
from research.repository import ResearchRepository

router = APIRouter(prefix="/keyword-opportunities", tags=["keyword-opportunities"])


class KeywordHeatSignalRequest(BaseModel):
    keyword: str
    current_24h: dict[str, float]
    avg_7d: dict[str, float]
    avg_30d: dict[str, float]
    platform: str = "all"
    ai_judgment: dict[str, object] | None = None


class KeywordHeatRebuildRequest(BaseModel):
    keyword: str = Field(min_length=1)
    platform: str | None = None
    vertical_id: int | None = None
    scene_pack_id: int | None = None


@router.get("")
async def get_keyword_opportunities(
    vertical_id: int,
    platform: str | None = None,
):
    require_research_database()
    repository = ResearchRepository()
    if platform:
        capability = await repository.get_platform_capability(platform)
        if capability and (not capability["enabled"] or not capability["keyword_heat_enabled"]):
            raise HTTPException(status_code=400, detail="Platform keyword heat analysis is disabled")
    tags = await repository.list_tag_definitions(vertical_id=vertical_id, enabled_only=True)
    entity_tags = await repository.list_entity_tags(vertical_id=vertical_id, platform=platform)
    profiles = await repository.list_creator_profiles(platforms=[platform] if platform else None)
    snapshots = await repository.list_creator_daily_snapshots(platform=platform)
    if not tags:
        return {
            "opportunities": await _fallback_keyword_opportunities_from_posts(
                repository,
                vertical_id=vertical_id,
                platform=platform,
            )
        }
    return {
        "opportunities": calculate_keyword_opportunities(
            vertical_id=vertical_id,
            tag_definitions=tags,
            entity_tags=entity_tags,
            creator_profiles=profiles,
            snapshots=snapshots,
            platform=platform,
        )
    }


@router.post("/heat/signal")
async def calculate_heat_signal(request: KeywordHeatSignalRequest):
    require_research_database()
    legacy = calculate_keyword_heat_signal(
        keyword=request.keyword,
        current_24h=request.current_24h,
        avg_7d=request.avg_7d,
        avg_30d=request.avg_30d,
    )
    dual = build_keyword_heat_signal(
        keyword=request.keyword,
        platform=request.platform,
        metrics={
            "volume_24h": request.current_24h.get("content_count", 0),
            "volume_7d_avg": request.avg_7d.get("content_count", 0),
            "volume_30d_avg": request.avg_30d.get("content_count", 0),
            "engagement_24h": request.current_24h.get("engagement_total", 0),
            "hot_post_rate": _safe_rate(
                request.current_24h.get("hot_post_count", 0),
                request.current_24h.get("content_count", 0),
            ),
            "creator_participation": request.current_24h.get("creator_count", 0),
        },
        ai_judgment=request.ai_judgment,
    )
    return {**legacy, **dual}


def _safe_rate(value: float, total: float) -> float:
    return float(value or 0) / max(float(total or 0), 1.0)


@router.post("/heat/rebuild")
async def rebuild_heat_signal(request: KeywordHeatRebuildRequest):
    require_research_database()
    repository = ResearchRepository()
    posts = await repository.list_all_posts(platform=request.platform, limit=5000)
    signal = aggregate_keyword_heat_from_posts(keyword=request.keyword, posts=posts)
    snapshot = await repository.upsert_keyword_heat_snapshot(
        {
            "vertical_id": request.vertical_id,
            "scene_pack_id": request.scene_pack_id,
            "keyword": request.keyword,
            "platform": request.platform or "all",
            "snapshot_date": date.today(),
            "heat_score": signal["heat_score"],
            "growth_score": signal["heat_score"],
            "push_signal_score": signal["push_score"],
            "limit_signal_score": signal["cooldown_risk"],
            "platform_signal": signal["label"],
            "evidence": {
                "evidence": signal["evidence"],
                "short_window": signal["short_window"],
                "medium_window": signal["medium_window"],
                "sampling_advice": signal.get("sampling_advice"),
            },
        }
    )
    return {"signal": signal, "snapshot": snapshot}


@router.get("/{tag_id}/evidence")
async def get_keyword_opportunity_evidence(
    tag_id: int,
    vertical_id: int,
    platform: str | None = None,
):
    require_research_database()
    repository = ResearchRepository()
    tags = await repository.list_entity_tags(
        vertical_id=vertical_id,
        platform=platform,
        tag_ids=[tag_id],
    )
    snapshots = await repository.list_keyword_opportunity_snapshots(
        vertical_id=vertical_id,
        platform=platform,
        tag_id=tag_id,
    )
    if not tags and not snapshots:
        raise HTTPException(status_code=404, detail="Keyword opportunity evidence not found")
    return {
        "tag_id": tag_id,
        "vertical_id": vertical_id,
        "platform": platform,
        "entity_tags": tags[:100],
        "snapshots": snapshots[:30],
    }


async def _fallback_keyword_opportunities_from_posts(
    repository: ResearchRepository,
    *,
    vertical_id: int,
    platform: str | None,
) -> list[dict]:
    scene_packs = await repository.list_scene_packs(vertical_id=vertical_id, enabled_only=True)
    scene_pack_ids = [item["id"] for item in scene_packs]
    scene_keywords = await repository.list_scene_pack_keywords(
        scene_pack_ids=scene_pack_ids or None,
        enabled_only=True,
    )
    posts = await repository.list_all_posts(platform=platform, limit=5000)
    candidates = []
    seen: set[str] = set()
    for item in scene_keywords:
        keyword = str(item.get("keyword") or "").strip()
        if not keyword or keyword in seen or item.get("keyword_type") == "negative":
            continue
        seen.add(keyword)
        signal = aggregate_keyword_heat_from_posts(keyword=keyword, posts=posts)
        content_7d = int(((signal.get("medium_window") or {}).get("content_count")) or 0)
        if content_7d <= 0:
            continue
        candidates.append(
            {
                "vertical_id": vertical_id,
                "platform": platform,
                "tag_id": item.get("id") or len(candidates) + 1,
                "tag_name": keyword,
                "heat_score": round(float(signal.get("heat_score") or 0), 4),
                "growth_score": round(float(((signal.get("medium_window") or {}).get("content_count")) or 0), 4),
                "competition_score": round(float(((signal.get("medium_window") or {}).get("creator_count")) or 0), 4),
                "supply_gap_score": round(
                    max(
                        0.0,
                        float(((signal.get("medium_window") or {}).get("content_count")) or 0)
                        - float(((signal.get("medium_window") or {}).get("creator_count")) or 0),
                    ),
                    4,
                ),
                "platform_signal": signal.get("label") or "normal",
                "evidence": {
                    "source": "posts_fallback",
                    "sample_quality": signal.get("sample_quality"),
                    "evidence": signal.get("evidence") or [],
                },
            }
        )
    if candidates:
        candidates.sort(key=lambda item: (item["heat_score"], item["growth_score"]), reverse=True)
        return candidates[:30]

    source_keyword_counts = Counter()
    for post in posts:
        engagement = post.get("engagement_json") or {}
        source_keyword = str(engagement.get("source_keyword") or "").strip()
        if not source_keyword:
            continue
        source_keyword_counts[source_keyword] += 1

    for keyword, count in source_keyword_counts.most_common(30):
        signal = aggregate_keyword_heat_from_posts(keyword=keyword, posts=posts)
        candidates.append(
            {
                "vertical_id": vertical_id,
                "platform": platform,
                "tag_id": len(candidates) + 1,
                "tag_name": keyword,
                "heat_score": round(float(signal.get("heat_score") or 0), 4),
                "growth_score": round(float(((signal.get("medium_window") or {}).get("content_count")) or count), 4),
                "competition_score": round(float(((signal.get("medium_window") or {}).get("creator_count")) or 0), 4),
                "supply_gap_score": round(max(float(count) - float(((signal.get("medium_window") or {}).get("creator_count")) or 0), 0.0), 4),
                "platform_signal": signal.get("label") or "normal",
                "evidence": {
                    "source": "source_keyword_ranking",
                    "sample_quality": signal.get("sample_quality"),
                    "evidence": (signal.get("evidence") or []) + [f"原始采集关键词命中 {count} 条帖子"],
                },
            }
        )
    candidates.sort(key=lambda item: (item["heat_score"], item["growth_score"]), reverse=True)
    return candidates[:30]
