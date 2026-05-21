import asyncio
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from api.routers.research import require_research_database
from database.db_session import create_tables
from research.ai_insights import run_ai_insight_analysis
from research.charts import build_chart_summary
from research.dashboard import build_dashboard_summary
from research.reporting import build_boss_report, build_growth_report
from research.repository import ResearchRepository

router = APIRouter(prefix="/reports", tags=["reports"])


class AIInsightRunRequest(BaseModel):
    provider_config_id: int | None = Field(default=None, ge=1)
    platforms: list[str] = Field(default_factory=lambda: ["xhs", "dy"])
    vertical_id: int | None = Field(default=None, ge=1)
    scene_pack_id: int | None = Field(default=None, ge=1)
    window_days: int = Field(default=7, ge=1, le=30)


class OpportunityFeedbackRequest(BaseModel):
    opportunity_id: str = Field(min_length=1, max_length=255)
    feedback: str = Field(pattern="^(valid|false_positive|watch)$")
    note: str | None = Field(default=None, max_length=1000)
    opportunity_type: str | None = Field(default=None, max_length=32)
    opportunity_name: str | None = Field(default=None, max_length=500)
    payload: dict = Field(default_factory=dict)


@router.get("/growth-summary")
async def get_growth_summary_report(
    vertical_id: int | None = None,
    platform: str | None = None,
):
    require_research_database()
    repository = ResearchRepository()
    jobs = await _maybe_call(repository, "list_jobs", default=[])
    competitor_compositions = await _maybe_call(
        repository,
        "list_competitor_composition_snapshots",
        platform=platform,
        limit=50,
        default=[],
    )
    keyword_heat_snapshots = await _maybe_call(
        repository,
        "list_keyword_heat_snapshots",
        platform=platform,
        limit=50,
        default=[],
    )
    content_snapshots = await _maybe_call(
        repository,
        "list_content_tracking_snapshots",
        platform=platform,
        limit=50,
        default=[],
    )
    if not keyword_heat_snapshots or not content_snapshots:
        fallback = await _build_dashboard_fallback_from_jobs(
            repository,
            jobs=jobs,
            platform=platform,
        )
        if not keyword_heat_snapshots:
            keyword_heat_snapshots = fallback["keyword_heat_snapshots"]
        if not content_snapshots:
            content_snapshots = fallback["content_snapshots"]
    return build_growth_report(
        vertical_id=vertical_id,
        platform=platform,
        creator_candidates=await _maybe_call(
            repository,
            "list_creator_candidates",
            vertical_id=vertical_id,
            platform=platform,
            default=[],
        ),
        creator_profiles=await repository.list_creator_profiles(
            platforms=[platform] if platform else None,
        ),
        competitors=await repository.list_competitor_accounts(),
        snapshots=await repository.list_creator_daily_snapshots(platform=platform),
        tag_definitions=await repository.list_tag_definitions(
            vertical_id=vertical_id,
            enabled_only=True,
        ),
        entity_tags=await repository.list_entity_tags(
            vertical_id=vertical_id,
            platform=platform,
        ),
        competitor_compositions=competitor_compositions,
        content_snapshots=content_snapshots,
        keyword_heat_snapshots=keyword_heat_snapshots,
    )


@router.get("/boss-summary")
async def get_boss_summary_report(
    vertical_id: int | None = None,
    platform: str | None = None,
):
    require_research_database()
    repository = ResearchRepository()
    creator_candidates = await _maybe_call(
        repository,
        "list_creator_candidates",
        vertical_id=vertical_id,
        platform=platform,
        default=[],
    )
    creator_candidates = await _enrich_creator_candidates(repository, creator_candidates)
    competitors = await _maybe_call(repository, "list_competitor_accounts", default=[])
    tag_definitions = await _maybe_call(
        repository,
        "list_tag_definitions",
        vertical_id=vertical_id,
        enabled_only=True,
        default=[],
    )
    entity_tags = await _maybe_call(
        repository,
        "list_entity_tags",
        vertical_id=vertical_id,
        platform=platform,
        default=[],
    )
    creator_profiles = await _maybe_call(
        repository,
        "list_creator_profiles",
        platforms=[platform] if platform else None,
        default=[],
    )
    snapshots = await _maybe_call(
        repository,
        "list_creator_daily_snapshots",
        platform=platform,
        default=[],
    )
    opportunities = build_growth_report(
        vertical_id=vertical_id,
        platform=platform,
        creator_candidates=creator_candidates,
        creator_profiles=creator_profiles,
        competitors=competitors,
        snapshots=snapshots,
        tag_definitions=tag_definitions,
        entity_tags=entity_tags,
    )["top_opportunities"]
    return build_boss_report(
        vertical_id=vertical_id,
        platform=platform,
        creator_candidates=creator_candidates,
        competitors=competitors,
        keyword_opportunities=opportunities,
        competitor_compositions=await _maybe_call(
            repository,
            "list_competitor_composition_snapshots",
            platform=platform,
            limit=50,
            default=[],
        ),
        content_snapshots=await _maybe_call(
            repository,
            "list_content_tracking_snapshots",
            platform=platform,
            limit=50,
            default=[],
        ),
        keyword_heat_snapshots=await _maybe_call(
            repository,
            "list_keyword_heat_snapshots",
            platform=platform,
            limit=50,
            default=[],
        ),
    )


@router.get("/dashboard-summary")
async def get_dashboard_summary(
    vertical_id: int | None = None,
    scene_pack_id: int | None = None,
    platform: str | None = None,
):
    require_research_database()
    repository = ResearchRepository()
    jobs = await _maybe_call(repository, "list_jobs", default=[])
    creator_candidates = await _maybe_call(
        repository,
        "list_creator_candidates",
        vertical_id=vertical_id,
        platform=platform,
        default=[],
    )
    creator_candidates = await _enrich_creator_candidates(repository, creator_candidates)
    keyword_heat_snapshots = await _maybe_call(
        repository,
        "list_keyword_heat_snapshots",
        vertical_id=vertical_id,
        scene_pack_id=scene_pack_id,
        platform=platform,
        limit=50,
        default=[],
    )
    competitor_compositions = await _maybe_call(
        repository,
        "list_competitor_composition_snapshots",
        platform=platform,
        limit=50,
        default=[],
    )
    competitor_accounts = await _maybe_call(
        repository,
        "list_competitor_accounts",
        enabled_only=True,
        default=[],
    )
    content_snapshots = await _maybe_call(
        repository,
        "list_content_tracking_snapshots",
        platform=platform,
        limit=50,
        default=[],
    )
    monitor_pools = await _maybe_call(
        repository,
        "list_monitor_pools",
        enabled_only=True,
        default=[],
    )
    feedback = await _maybe_call(
        repository,
        "list_opportunity_feedback",
        limit=500,
        default=[],
    )
    if not keyword_heat_snapshots or not content_snapshots:
        fallback = await _build_dashboard_fallback_from_jobs(
            repository,
            jobs=jobs,
            platform=platform,
        )
        if not keyword_heat_snapshots:
            keyword_heat_snapshots = fallback["keyword_heat_snapshots"]
        if not content_snapshots:
            content_snapshots = fallback["content_snapshots"]
    competitor_compositions = _merge_competitor_account_fallbacks(
        competitor_compositions,
        competitor_accounts,
        platform=platform,
    )
    return build_dashboard_summary(
        jobs=jobs,
        creator_candidates=creator_candidates,
        keyword_heat_snapshots=keyword_heat_snapshots,
        competitor_compositions=competitor_compositions,
        content_snapshots=content_snapshots,
        monitor_pools=monitor_pools,
        platform=platform,
        feedback=feedback,
    )


@router.post("/opportunity-feedback")
async def create_opportunity_feedback(request: OpportunityFeedbackRequest):
    require_research_database()
    repository = ResearchRepository()
    feedback = await repository.create_opportunity_feedback(request.model_dump(mode="python"))
    return {"feedback": feedback}


@router.post("/ai-insights/run")
async def run_ai_insights(request: AIInsightRunRequest):
    require_research_database()
    await create_tables()
    try:
        return await run_ai_insight_analysis(
            ResearchRepository(),
            provider_config_id=request.provider_config_id,
            platforms=request.platforms,
            vertical_id=request.vertical_id,
            scene_pack_id=request.scene_pack_id,
            window_days=request.window_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/ai-insights/latest")
async def get_latest_ai_insights(limit: int = 20):
    require_research_database()
    await create_tables()
    repository = ResearchRepository()
    runs = await repository.list_ai_insight_runs(limit=1)
    run = runs[0] if runs else None
    run_id = run["id"] if run else None
    return {
        "run": run,
        "hotspots": await repository.list_ai_hotspots(run_id=run_id, limit=limit)
        if run_id
        else [],
        "topic_ideas": await repository.list_ai_topic_ideas(run_id=run_id, limit=limit)
        if run_id
        else [],
    }


@router.get("/ai-topic-ideas")
async def list_ai_topic_ideas(status: str | None = "active", limit: int = 30):
    require_research_database()
    await create_tables()
    return {
        "topic_ideas": await ResearchRepository().list_ai_topic_ideas(
            status=status,
            limit=min(max(limit, 1), 100),
        )
    }


@router.get("/vertical/{vertical_id}")
async def get_vertical_boss_report(vertical_id: int, platform: str | None = None):
    return await get_boss_summary_report(vertical_id=vertical_id, platform=platform)


@router.get("/scene-pack/{scene_pack_id}")
async def get_scene_pack_boss_report(scene_pack_id: int, platform: str | None = None):
    require_research_database()
    repository = ResearchRepository()
    scene_pack = await _maybe_call(repository, "get_scene_pack", scene_pack_id, default=None)
    vertical_id = scene_pack.get("vertical_id") if scene_pack else None
    report = await get_boss_summary_report(vertical_id=vertical_id, platform=platform)
    report["scene_pack_id"] = scene_pack_id
    return report


async def _maybe_call(
    repository,
    method_name: str,
    *args,
    default=None,
    timeout_seconds: float = 3.0,
    **kwargs,
):
    method = getattr(repository, method_name, None)
    if method is None:
        return default
    try:
        return await asyncio.wait_for(
            method(*args, **kwargs),
            timeout=timeout_seconds,
        )
    except (TypeError, TimeoutError, asyncio.TimeoutError):
        return default
    except Exception:
        return default


async def _enrich_creator_candidates(repository, candidates: list[dict]) -> list[dict]:
    enriched = []
    for item in candidates:
        next_item = dict(item)
        profile = await _maybe_call(
            repository,
            "get_creator_profile",
            item.get("platform"),
            item.get("creator_id"),
            default=None,
            timeout_seconds=1.0,
        )
        if profile:
            for key in ("display_name", "profile_url", "bio", "follower_count", "post_count"):
                if profile.get(key) not in (None, ""):
                    next_item[key] = profile[key]
        enriched.append(next_item)
    return enriched


async def _build_dashboard_fallback_from_jobs(
    repository,
    *,
    jobs: list[dict],
    platform: str | None,
) -> dict[str, list[dict]]:
    keyword_counts: Counter[str] = Counter()
    keyword_latest_platform: dict[str, str | None] = {}
    content_snapshots: list[dict] = []
    recent_jobs = sorted(
        [item for item in jobs if _job_matches_platform(item, platform)],
        key=_job_fallback_priority,
    )[:20]
    filled_snapshots = 0

    for job in recent_jobs:
        posts = await _maybe_call(
            repository,
            "list_posts",
            job["id"],
            default=[],
            timeout_seconds=2.0,
        )
        comments = await _maybe_call(
            repository,
            "list_comments",
            job["id"],
            default=[],
            timeout_seconds=2.0,
        )
        if platform:
            posts = [item for item in posts if item.get("platform") == platform]
            comments = [item for item in comments if item.get("platform") == platform]
        if not posts and not comments:
            continue
        filled_snapshots += 1
        chart = build_chart_summary(posts=posts, comments=comments, ai_results=[])
        top_posts = sorted(
            posts,
            key=lambda item: _engagement_total(item.get("engagement_json") or {}),
            reverse=True,
        )[:3]
        keyword_distribution = {
            item["keyword"]: int(item["count"])
            for item in chart.get("keyword_ranking", [])[:12]
        }
        for keyword, count in keyword_distribution.items():
            keyword_counts[keyword] += int(count)
            keyword_latest_platform[keyword] = platform or (posts[0].get("platform") if posts else None)
        content_snapshots.append(
            {
                "tracker_id": job["id"],
                "platform": platform or (posts[0].get("platform") if posts else None),
                "total_content_count": len(posts),
                "hot_post_rate": _estimate_hot_post_rate(posts),
                "keyword_distribution": keyword_distribution,
                "snapshot_date": datetime.now(timezone.utc).date().isoformat(),
                "evidence": {
                    "top_posts": [_fallback_post_sample(item) for item in top_posts]
                },
            }
        )
        if filled_snapshots >= 5:
            break

    keyword_heat_snapshots = [
        {
            "keyword": keyword,
            "platform": keyword_latest_platform.get(keyword),
            "heat_score": min(100.0, 35 + count * 4),
            "growth_score": min(100.0, count * 1.5),
            "platform_signal": "boosting" if count >= 10 else "normal",
            "snapshot_date": datetime.now(timezone.utc).date().isoformat(),
            "evidence": {
                "items": [f"最近任务命中 {count} 条原始帖子"],
            },
        }
        for keyword, count in keyword_counts.most_common(20)
    ]
    return {
        "keyword_heat_snapshots": keyword_heat_snapshots,
        "content_snapshots": content_snapshots,
    }


def _merge_competitor_account_fallbacks(
    snapshots: list[dict],
    accounts: list[dict],
    *,
    platform: str | None,
) -> list[dict]:
    account_by_id = {item.get("id"): item for item in accounts if item.get("id") is not None}
    merged = []
    represented_ids = set()
    for snapshot in snapshots:
        item = dict(snapshot)
        competitor_id = item.get("competitor_id")
        represented_ids.add(competitor_id)
        account = account_by_id.get(competitor_id)
        if account:
            item.setdefault("display_name", account.get("display_name"))
            item.setdefault("competitor_name", account.get("display_name") or account.get("creator_id"))
            item.setdefault("profile_url", account.get("profile_url"))
        merged.append(item)

    for account in accounts:
        if platform and account.get("platform") != platform:
            continue
        if account.get("id") in represented_ids:
            continue
        merged.append(
            {
                "competitor_id": account.get("id"),
                "platform": account.get("platform"),
                "display_name": account.get("display_name"),
                "competitor_name": account.get("display_name") or account.get("creator_id") or f"友商 #{account.get('id')}",
                "profile_url": account.get("profile_url"),
                "total_flow_count": 0,
                "hot_post_rate": 0.0,
                "snapshot_date": datetime.now(timezone.utc).date().isoformat(),
                "sample_count": 0,
                "missing_execution_parameters": not account.get("profile_url"),
                "evidence": {
                    "items": [
                        "已配置友商账号，但还没有公开流量快照；请立即获取数据或重建快照。"
                    ]
                },
            }
        )
    return merged


def _engagement_total(engagement: dict) -> float:
    total = 0.0
    for key in (
        "digg_count",
        "like_count",
        "collect_count",
        "favorite_count",
        "comment_count",
        "share_count",
        "play_count",
        "view_count",
    ):
        value = engagement.get(key)
        if isinstance(value, (int, float)):
            total += float(value)
    return total


def _fallback_post_sample(item: dict) -> dict:
    return {
        "title": item.get("title") or item.get("platform_post_id") or "未命名内容",
        "body": item.get("content"),
        "platform": item.get("platform"),
        "platform_post_id": item.get("platform_post_id"),
        "url": item.get("url"),
        "publish_time": item.get("publish_time"),
        "engagement_json": item.get("engagement_json") or {},
    }


def _estimate_hot_post_rate(posts: list[dict]) -> float:
    if not posts:
        return 0.0
    hot = 0
    for item in posts:
        if _engagement_total(item.get("engagement_json") or {}) >= 100:
            hot += 1
    return hot / len(posts)


def _job_matches_platform(job: dict, platform: str | None) -> bool:
    if not platform:
        return True
    platforms = job.get("platforms") or []
    if isinstance(platforms, str):
        try:
            platforms = json.loads(platforms)
        except json.JSONDecodeError:
            platforms = [platforms]
    return platform in platforms


def _job_fallback_priority(job: dict) -> tuple[int, int, int]:
    status_priority = {
        "completed": 0,
        "running": 1,
        "queued": 3,
        "pending": 4,
    }.get(str(job.get("status") or ""), 2)
    mode_priority = 0 if job.get("collection_mode") == "search" else 1
    return (status_priority, mode_priority, -int(job.get("id") or 0))
