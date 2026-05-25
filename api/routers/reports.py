import asyncio
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps.auth import require_current_user
from api.routers.research import require_research_database
from database.db_session import create_tables
from research.ai_insights import run_ai_insight_analysis
from research.ai_provider import OpenAICompatibleProvider
from research.charts import build_chart_summary
from research.content_strategy import (
    build_content_strategy_draft_prompt,
    build_content_strategy_summary,
    build_strategy_draft_fallback,
    normalize_strategy_draft_output,
    normalize_strategy_filters,
)
from research.content_strategy_refresh import (
    collect_active_project_keywords,
    generate_project_content_strategy_ai_bundle,
    load_project_content_strategy_state,
    refresh_interval_minutes as content_strategy_refresh_interval_minutes,
    save_project_content_strategy_state,
)
from research.dashboard import build_dashboard_summary
from research.lead_attribution import (
    build_daily_snapshot_payload,
    build_lead_attribution_summary,
    compute_attribution_rows,
    group_attribution_rows,
    normalize_attribution_config,
    setting_key_for_project,
)
from research.growth_projects import project_key_for_job
from research.reporting import build_boss_report, build_growth_report
from research.repository import ResearchRepository

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_current_user)],
)
GLOBAL_ATTRIBUTION_PROJECT_ID = "__global__"
GLOBAL_ATTRIBUTION_CONFIG_KEY = "research:lead-attribution:global:config"
PROJECT_CONTENT_STRATEGY_POST_LIMIT = 1500
PROJECT_CONTENT_STRATEGY_SNAPSHOT_LIMIT = 120


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


class ContentStrategyDraftRequest(BaseModel):
    kind: str = Field(pattern="^(copy|weekly_plan|topic_pack|framework|evidence_summary)$")
    payload: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    provider_config_id: int | None = Field(default=None, ge=1)


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


@router.get("/lead-attribution/summary")
async def get_lead_attribution_summary(
    project_id: str | None = None,
    scope: str = "project",
    model: str = "last_touch",
    date_from: str | None = None,
    date_to: str | None = None,
):
    require_research_database()
    repository = ResearchRepository()
    if _is_global_attribution_scope(scope=scope, project_id=project_id):
        return await _build_global_lead_attribution_payload(
            repository=repository,
            requested_model=model,
            date_from=date_from,
            date_to=date_to,
        )
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required for project scope")
    record = await _get_growth_project_record_by_identifier(repository, project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    payload = await _build_lead_attribution_payload(
        repository=repository,
        project_record=record,
        requested_model=model,
        date_from=date_from,
        date_to=date_to,
        persist_snapshot=False,
    )
    return payload


@router.post("/lead-attribution/summary/refresh")
async def refresh_lead_attribution_summary(
    project_id: str | None = None,
    scope: str = "project",
    model: str = "last_touch",
    date_from: str | None = None,
    date_to: str | None = None,
):
    require_research_database()
    repository = ResearchRepository()
    if _is_global_attribution_scope(scope=scope, project_id=project_id):
        payload = await _build_global_lead_attribution_payload(
            repository=repository,
            requested_model=model,
            date_from=date_from,
            date_to=date_to,
        )
        return {"refreshed": False, **payload}
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required for project scope")
    record = await _get_growth_project_record_by_identifier(repository, project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    payload = await _build_lead_attribution_payload(
        repository=repository,
        project_record=record,
        requested_model=model,
        date_from=date_from,
        date_to=date_to,
        persist_snapshot=True,
    )
    return {"refreshed": True, **payload}


@router.get("/lead-attribution/platform")
async def get_lead_attribution_platform(
    project_id: str | None = None,
    scope: str = "project",
    model: str = "last_touch",
    date_from: str | None = None,
    date_to: str | None = None,
):
    payload = await get_lead_attribution_summary(
        project_id=project_id,
        scope=scope,
        model=model,
        date_from=date_from,
        date_to=date_to,
    )
    return {"project_id": project_id, "model": payload["summary"]["model"], "rows": payload["top_platforms"]}


@router.get("/lead-attribution/keyword")
async def get_lead_attribution_keyword(
    project_id: str | None = None,
    scope: str = "project",
    model: str = "last_touch",
    date_from: str | None = None,
    date_to: str | None = None,
):
    payload = await get_lead_attribution_summary(
        project_id=project_id,
        scope=scope,
        model=model,
        date_from=date_from,
        date_to=date_to,
    )
    return {"project_id": project_id, "model": payload["summary"]["model"], "rows": payload["top_keywords"]}


@router.get("/lead-attribution/content")
async def get_lead_attribution_content(
    project_id: str | None = None,
    scope: str = "project",
    model: str = "last_touch",
    date_from: str | None = None,
    date_to: str | None = None,
):
    payload = await get_lead_attribution_summary(
        project_id=project_id,
        scope=scope,
        model=model,
        date_from=date_from,
        date_to=date_to,
    )
    return {"project_id": project_id, "model": payload["summary"]["model"], "rows": payload["top_contents"]}


@router.get("/lead-attribution/creator")
async def get_lead_attribution_creator(
    project_id: str | None = None,
    scope: str = "project",
    model: str = "last_touch",
    date_from: str | None = None,
    date_to: str | None = None,
):
    payload = await get_lead_attribution_summary(
        project_id=project_id,
        scope=scope,
        model=model,
        date_from=date_from,
        date_to=date_to,
    )
    return {"project_id": project_id, "model": payload["summary"]["model"], "rows": payload["top_creators"]}


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


@router.get("/content-strategy/summary")
async def get_content_strategy_summary(
    project_id: str | None = None,
    tracker_id: int | None = Query(default=None, ge=1),
    platform: str | None = None,
    time_range: str = Query("30d", alias="range"),
    goal: str = "conversion",
    audience: str = "all",
    stage: str = "boost",
):
    require_research_database()
    await create_tables()
    repository = ResearchRepository()
    return await _build_content_strategy_summary_response(
        repository=repository,
        project_id=project_id,
        platform=platform,
        tracker_id=tracker_id,
        time_range=time_range,
        goal=goal,
        audience=audience,
        stage=stage,
        record_manual_refresh=False,
    )


@router.post("/content-strategy/summary/refresh")
async def refresh_content_strategy_summary(
    project_id: str | None = None,
    tracker_id: int | None = Query(default=None, ge=1),
    platform: str | None = None,
    time_range: str = Query("30d", alias="range"),
    goal: str = "conversion",
    audience: str = "all",
    stage: str = "boost",
    wait: bool = Query(default=False),
):
    require_research_database()
    await create_tables()
    repository = ResearchRepository()
    return await _build_content_strategy_summary_response(
        repository=repository,
        project_id=project_id,
        platform=platform,
        tracker_id=tracker_id,
        time_range=time_range,
        goal=goal,
        audience=audience,
        stage=stage,
        record_manual_refresh=True,
        run_manual_refresh_inline=wait,
    )


async def _build_content_strategy_summary_response(
    *,
    repository: ResearchRepository,
    project_id: str | None,
    platform: str | None,
    tracker_id: int | None,
    time_range: str,
    goal: str,
    audience: str,
    stage: str,
    record_manual_refresh: bool,
    run_manual_refresh_inline: bool = True,
) -> dict[str, Any]:
    filters = normalize_strategy_filters(
        platform=platform,
        time_range=time_range,
        goal=goal,
        audience=audience,
        stage=stage,
    )
    if project_id:
        record = await _get_growth_project_record_by_identifier(repository, project_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Growth project not found")
        return await _build_project_content_strategy_summary_response(
            repository=repository,
            project_identifier=project_id,
            project_record=record,
            tracker_id=tracker_id,
            filters=filters,
            record_manual_refresh=record_manual_refresh,
            run_manual_refresh_inline=run_manual_refresh_inline,
        )
    return await _build_global_content_strategy_summary_response(
        repository=repository,
        filters=filters,
    )


async def _run_project_content_strategy_ai_refresh(
    *,
    project_identifier: str,
    project_record_id: int,
    tracker_id: int | None,
    platform: str | None,
    time_range: str,
    goal: str,
    audience: str,
    stage: str,
) -> None:
    try:
        await create_tables()
        repository = ResearchRepository()
        await _build_content_strategy_summary_response(
            repository=repository,
            project_id=project_identifier,
            platform=platform,
            tracker_id=tracker_id,
            time_range=time_range,
            goal=goal,
            audience=audience,
            stage=stage,
            record_manual_refresh=True,
            run_manual_refresh_inline=True,
        )
    except Exception as exc:
        repository = ResearchRepository()
        state = await load_project_content_strategy_state(repository, project_record_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        state["scheduled_refresh"].update(
            {
                "status": "failed",
                "trigger": "manual",
                "last_completed_at": now_iso,
                "last_error": f"{type(exc).__name__}: {exc}",
            }
        )
        await save_project_content_strategy_state(repository, project_record_id, state)


async def _build_global_content_strategy_summary_response(
    *,
    repository: ResearchRepository,
    filters: dict[str, Any],
) -> dict[str, Any]:
    platform_filter = filters["platform"]
    now = datetime.now(timezone.utc)
    start_at = now - timedelta(days=int(filters["window_days"]))
    dashboard = await get_dashboard_summary(platform=platform_filter)
    posts = await _maybe_call(
        repository,
        "list_all_posts",
        platform=platform_filter,
        start_at=start_at,
        end_at=now,
        limit=1500,
        default=[],
        timeout_seconds=4.0,
    )
    keyword_heat_snapshots = await _maybe_call(
        repository,
        "list_keyword_heat_snapshots",
        platform=platform_filter,
        limit=100,
        default=[],
    )
    content_snapshots = await _maybe_call(
        repository,
        "list_content_tracking_snapshots",
        platform=platform_filter,
        limit=100,
        default=[],
    )
    competitor_compositions = await _maybe_call(
        repository,
        "list_competitor_composition_snapshots",
        platform=platform_filter,
        limit=100,
        default=[],
    )
    ai_runs = await _maybe_call(repository, "list_ai_insight_runs", limit=1, default=[])
    ai_run = ai_runs[0] if ai_runs else None
    ai_topics = await _maybe_call(
        repository,
        "list_ai_topic_ideas",
        status="active",
        limit=50,
        default=[],
    )
    ai_hotspots = await _maybe_call(
        repository,
        "list_ai_hotspots",
        run_id=ai_run.get("id") if ai_run else None,
        limit=20,
        default=[],
    )
    return build_content_strategy_summary(
        filters=filters,
        dashboard=dashboard,
        posts=posts,
        keyword_heat_snapshots=keyword_heat_snapshots,
        content_snapshots=content_snapshots,
        competitor_compositions=competitor_compositions,
        ai_insights={
            "run": ai_run,
            "hotspots": ai_hotspots,
            "risk_notes": (ai_run.get("output") or {}).get("risk_notes", []) if ai_run else [],
        },
        ai_topic_ideas=ai_topics,
    )


async def _build_project_content_strategy_summary_response(
    *,
    repository: ResearchRepository,
    project_identifier: str,
    project_record: dict[str, Any],
    tracker_id: int | None,
    filters: dict[str, Any],
    record_manual_refresh: bool,
    run_manual_refresh_inline: bool = True,
) -> dict[str, Any]:
    platform_filter = filters["platform"]
    now = datetime.now(timezone.utc)
    start_at = now - timedelta(days=int(filters["window_days"]))
    project_jobs = await _project_jobs_for_sample_analysis(repository, project_record)
    job_ids = [
        int(item["id"])
        for item in project_jobs
        if item.get("id") is not None and str(item.get("id")).isdigit()
    ]
    posts_page = await _maybe_call(
        repository,
        "list_posts_page",
        job_ids=job_ids,
        limit=PROJECT_CONTENT_STRATEGY_POST_LIMIT,
        offset=0,
        default={"posts": [], "total": 0, "limit": PROJECT_CONTENT_STRATEGY_POST_LIMIT, "offset": 0},
        timeout_seconds=4.0,
    )
    posts = _filter_project_posts(
        (posts_page or {}).get("posts") or [],
        platform=platform_filter,
        start_at=start_at,
        end_at=now,
    )
    keyword_rows = await _maybe_call(
        repository,
        "list_growth_project_keywords",
        int(project_record["id"]),
        default=[],
    )
    active_keywords = collect_active_project_keywords(keyword_rows)
    project_platforms = [
        str(item).strip()
        for item in (project_record.get("platforms") or [])
        if str(item).strip()
    ]
    keyword_heat_snapshots = _filter_project_keyword_heat_snapshots(
        await _maybe_call(
            repository,
            "list_keyword_heat_snapshots",
            platform=platform_filter,
            limit=PROJECT_CONTENT_STRATEGY_SNAPSHOT_LIMIT,
            default=[],
        ),
        project_keywords=active_keywords,
        project_platforms=project_platforms,
    )
    content_snapshots = _filter_project_content_snapshots(
        await _maybe_call(
            repository,
            "list_content_tracking_snapshots",
            platform=platform_filter,
            limit=PROJECT_CONTENT_STRATEGY_SNAPSHOT_LIMIT,
            default=[],
        ),
        project_keywords=active_keywords,
        project_platforms=project_platforms,
    )
    competitor_compositions = _filter_project_competitor_snapshots(
        await _maybe_call(
            repository,
            "list_competitor_composition_snapshots",
            platform=platform_filter,
            limit=PROJECT_CONTENT_STRATEGY_SNAPSHOT_LIMIT,
            default=[],
        ),
        project_keywords=active_keywords,
        project_platforms=project_platforms,
    )
    if not keyword_heat_snapshots or not content_snapshots:
        fallback = await _build_dashboard_fallback_from_jobs(
            repository,
            jobs=project_jobs,
            platform=platform_filter,
        )
        if not keyword_heat_snapshots:
            keyword_heat_snapshots = _filter_project_keyword_heat_snapshots(
                fallback["keyword_heat_snapshots"],
                project_keywords=active_keywords,
                project_platforms=project_platforms,
            )
        if not content_snapshots:
            content_snapshots = _filter_project_content_snapshots(
                fallback["content_snapshots"],
                project_keywords=active_keywords,
                project_platforms=project_platforms,
            )
    feedback = await _maybe_call(
        repository,
        "list_opportunity_feedback",
        limit=500,
        default=[],
    )
    dashboard = build_dashboard_summary(
        jobs=_filter_project_jobs_by_platform(project_jobs, platform_filter),
        creator_candidates=[],
        keyword_heat_snapshots=keyword_heat_snapshots,
        competitor_compositions=competitor_compositions,
        content_snapshots=content_snapshots,
        monitor_pools=[],
        platform=platform_filter,
        feedback=feedback,
    )
    strategy_state = await load_project_content_strategy_state(repository, int(project_record["id"]))
    ai_bundle = strategy_state.get("ai_insights") or {}
    if record_manual_refresh:
        started_at = datetime.now(timezone.utc).isoformat()
        base_summary = build_content_strategy_summary(
            filters=filters,
            dashboard=dashboard,
            posts=posts,
            keyword_heat_snapshots=keyword_heat_snapshots,
            content_snapshots=content_snapshots,
            competitor_compositions=competitor_compositions,
            ai_insights={"run": None, "hotspots": [], "risk_notes": []},
            ai_topic_ideas=[],
        )
        strategy_state["scheduled_refresh"]["status"] = "ai_analyzing"
        strategy_state["scheduled_refresh"]["trigger"] = "manual"
        strategy_state["scheduled_refresh"]["last_started_at"] = started_at
        strategy_state["scheduled_refresh"]["last_error"] = None
        strategy_state = await save_project_content_strategy_state(
            repository,
            int(project_record["id"]),
            strategy_state,
        )
        if run_manual_refresh_inline:
            ai_bundle = await generate_project_content_strategy_ai_bundle(
                repository,
                project_record=project_record,
                keyword_rows=keyword_rows,
                posts=posts,
                window_days=int(filters["window_days"]),
                filters=filters,
                keyword_heat_snapshots=keyword_heat_snapshots,
                content_snapshots=content_snapshots,
                competitor_compositions=competitor_compositions,
                base_summary=base_summary,
            )
            now_iso = datetime.now(timezone.utc).isoformat()
            strategy_state["ai_insights"] = ai_bundle
            strategy_state["manual_analysis"]["last_refreshed_at"] = now_iso
            strategy_state["scheduled_refresh"].update(
                {
                    "status": ai_bundle.get("status") or "completed",
                    "trigger": "manual",
                    "last_started_at": started_at,
                    "last_completed_at": now_iso,
                    "last_error": ai_bundle.get("error"),
                }
            )
            strategy_state = await save_project_content_strategy_state(
                repository,
                int(project_record["id"]),
                strategy_state,
            )
        else:
            asyncio.create_task(
                _run_project_content_strategy_ai_refresh(
                    project_identifier=project_identifier,
                    project_record_id=int(project_record["id"]),
                    tracker_id=tracker_id,
                    platform=platform_filter,
                    time_range=str(filters.get("range") or "30d"),
                    goal=str(filters.get("goal") or "conversion"),
                    audience=str(filters.get("audience") or "all"),
                    stage=str(filters.get("stage") or "boost"),
                )
            )
    ai_run = None
    if ai_bundle.get("generated_at") or ai_bundle.get("provider") or ai_bundle.get("status") not in {None, "idle"}:
        ai_run = {
            "id": f"project-content-strategy:{project_record['id']}",
            "status": ai_bundle.get("status"),
            "generated_at": ai_bundle.get("generated_at"),
            "provider": ai_bundle.get("provider"),
            "input_summary": ai_bundle.get("input_summary") or {},
            "output": {
                "executive_summary": ai_bundle.get("executive_summary") or "",
                "platform_strategy": ai_bundle.get("platform_strategy") or {},
                "risk_notes": ai_bundle.get("risk_notes") or [],
                "content_strategy": ai_bundle.get("strategy_summary") or {},
            },
        }
    ai_topic_rows = _normalize_project_ai_topic_ideas(
        ai_bundle.get("topic_ideas") or [],
        platform=platform_filter,
    )
    ai_strategy_summary = (
        ai_bundle.get("strategy_summary")
        if ai_bundle.get("strategy_summary_source") in {"ai", "partial_ai"}
        and isinstance(ai_bundle.get("strategy_summary"), dict)
        else None
    )
    summary = build_content_strategy_summary(
        filters=filters,
        dashboard=dashboard,
        posts=posts,
        keyword_heat_snapshots=keyword_heat_snapshots,
        content_snapshots=content_snapshots,
        competitor_compositions=competitor_compositions,
        ai_insights={
            "run": ai_run,
            "hotspots": ai_bundle.get("hotspots") or [],
            "risk_notes": ai_bundle.get("risk_notes") or [],
        },
        ai_topic_ideas=ai_topic_rows,
        ai_strategy_summary=ai_strategy_summary,
    )
    bundle_strategy_note = str(((ai_bundle.get("strategy_summary") or {}) if isinstance(ai_bundle.get("strategy_summary"), dict) else {}).get("strategy_note") or "").strip()
    if bundle_strategy_note and not summary.get("strategy_note"):
        summary["strategy_note"] = bundle_strategy_note
    ai_source = (
        "project_ai_strategy"
        if ai_bundle.get("strategy_summary_source") == "ai"
        else "project_ai_partial"
        if ai_bundle.get("strategy_summary_source") == "partial_ai"
        else "project_ai_fallback"
        if ai_bundle.get("strategy_summary_source") == "fallback"
        else "latest_ai_topic_ideas"
        if ai_topic_rows
        else "deterministic_rules"
    )
    summary["ai_status"] = {
        **(summary.get("ai_status") or {}),
        "enabled": bool(ai_run or ai_topic_rows or ai_strategy_summary),
        "source": ai_source,
        "status": ai_bundle.get("status") or "idle",
        "generated_at": ai_bundle.get("generated_at"),
        "provider": ai_bundle.get("provider"),
        "error": ai_bundle.get("error"),
        "strategy_summary_source": ai_bundle.get("strategy_summary_source") or "none",
        "section_statuses": ai_bundle.get("section_statuses") or {},
    }
    summary["project_context"] = {
        "project_id": _slug_project_key(project_identifier or project_record.get("name")),
        "project_record_id": int(project_record["id"]),
        "project_name": project_record.get("name"),
        "platforms": project_platforms,
        "keywords": active_keywords,
        "primary_goal": project_record.get("primary_goal"),
        "comment_collection_enabled": bool(project_record.get("comment_collection_enabled")),
        "refresh_cadence": project_record.get("refresh_cadence") or "off",
        "custom_interval_value": project_record.get("custom_interval_value"),
        "custom_interval_unit": project_record.get("custom_interval_unit"),
    }
    if tracker_id is not None:
        summary["filters"] = {
            **(summary.get("filters") or {}),
            "tracker_id": tracker_id,
        }
        summary["source_tracker"] = await _build_content_strategy_source_tracker(
            repository=repository,
            tracker_id=tracker_id,
        )
        tracker_evidence = {
            "type": "source_tracker",
            "title": summary["source_tracker"]["name"],
            "platform": None,
            "reason": summary["source_tracker"].get("latest_headline")
            or "该追踪器作为本次项目策略分析的辅助信号。",
            "payload": summary["source_tracker"],
        }
        evidence_pack = summary.setdefault("evidence_pack", {"items": [], "risks": [], "total": 0})
        previous_items = evidence_pack.get("items") or []
        previous_total = int(evidence_pack.get("total") or len(previous_items))
        evidence_pack["items"] = [tracker_evidence, *previous_items]
        evidence_pack["total"] = previous_total + 1
        summary["hero"]["evidence_count"] = int(summary["hero"].get("evidence_count") or 0) + 1
    summary["refresh_status"] = _build_project_content_strategy_refresh_payload(
        project_record=project_record,
        strategy_state=strategy_state,
    )
    if (summary.get("section_sources") or {}).get("hero") != "ai":
        summary["hero"]["sample_summary"] = (
            f"项目 {project_record.get('name') or summary['project_context']['project_id']} 已形成 "
            f"{len(summary.get('suggestions') or [])} 条选题线索，证据 {summary['hero'].get('evidence_count') or 0} 条。"
        )
    return summary


async def _build_content_strategy_source_tracker(
    *,
    repository: ResearchRepository,
    tracker_id: int,
) -> dict[str, Any]:
    tracker = await repository.get_content_tracker(tracker_id)
    if tracker is None:
        raise HTTPException(status_code=404, detail="Content tracker not found")
    snapshot = await repository.get_latest_content_tracker_analysis_snapshot(tracker_id)
    overview = (snapshot or {}).get("overview") or {}
    trends = (snapshot or {}).get("trends") or {}
    decisions = (snapshot or {}).get("decisions") or {}
    latest_headline = (
        str(decisions.get("headline") or "").strip()
        or str(overview.get("headline") or "").strip()
        or None
    )
    return {
        "id": tracker["id"],
        "name": tracker.get("name") or f"追踪器 #{tracker_id}",
        "description": tracker.get("description"),
        "platforms": tracker.get("platforms") or [],
        "included_keywords": tracker.get("included_keywords") or [],
        "excluded_keywords": tracker.get("excluded_keywords") or [],
        "enabled": bool(tracker.get("enabled")),
        "latest_headline": latest_headline,
        "latest_status": overview.get("status") or (snapshot or {}).get("status"),
        "sample_quality_score": overview.get("sample_quality_score"),
        "trend_strength_score": trends.get("trend_strength_score"),
        "updated_at": overview.get("updated_at") or (snapshot or {}).get("snapshot_date") or tracker.get("updated_at"),
    }


@router.post("/content-strategy/draft")
async def generate_content_strategy_draft(request: ContentStrategyDraftRequest):
    require_research_database()
    repository = ResearchRepository()
    source_payload = {
        **request.payload,
        "kind": request.kind,
    }
    try:
        provider_config = await _resolve_strategy_ai_provider(
            repository,
            provider_config_id=request.provider_config_id,
        )
        provider = OpenAICompatibleProvider(
            base_url=provider_config["base_url"],
            api_key=provider_config["api_key"],
            model=provider_config["model"],
            timeout=provider_config.get("timeout") or 60,
        )
        default_params = provider_config.get("default_params") or {}
        output = await provider.complete_json(
            prompt=build_content_strategy_draft_prompt(
                kind=request.kind,
                payload=request.payload,
                context=request.context,
                filters=request.filters,
            ),
            params={
                **default_params,
                "temperature": 0.35,
                "max_tokens": 1800,
            },
        )
        return {
            "status": "completed",
            "mode": "ai",
            "provider": {
                "name": provider_config.get("name"),
                "model": provider_config.get("model"),
            },
            "draft": normalize_strategy_draft_output(output, source_payload=source_payload),
        }
    except Exception as exc:
        return {
            "status": "fallback",
            "mode": "rules",
            "provider": None,
            "error": f"{type(exc).__name__}: {exc}",
            "draft": build_strategy_draft_fallback(
                source_payload,
                reason=f"AI 生成失败：{type(exc).__name__}",
            ),
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


async def _get_growth_project_record_by_identifier(
    repository: ResearchRepository,
    project_id: str,
) -> dict | None:
    resolver = getattr(repository, "resolve_growth_project_record", None)
    if resolver is not None:
        return await resolver(project_id, include_archived=True)
    if project_id.isdigit():
        return await repository.get_growth_project_record(int(project_id))
    for record in await repository.list_growth_project_records(include_archived=True):
        slug = (
            str(record.get("name") or "")
            .strip()
            .lower()
            .replace(" ", "_")
        )
        slug = "".join(ch if ch.isalnum() or ch == "_" or ("\u4e00" <= ch <= "\u9fff") else "_" for ch in slug).strip("_")
        if slug == project_id:
            return record
    return None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    candidates = [value.strip()]
    if " " in candidates[0] and "T" in candidates[0]:
        head, tail = candidates[0].rsplit(" ", 1)
        candidates.append(f"{head}+{tail}")
    parsed = None
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            break
        except ValueError:
            continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_global_attribution_scope(*, scope: str | None, project_id: str | None) -> bool:
    normalized_scope = str(scope or "").strip().lower()
    normalized_project = str(project_id or "").strip().lower()
    return normalized_scope == "global" or normalized_project in {
        GLOBAL_ATTRIBUTION_PROJECT_ID,
        "global",
        "all",
        "all_data",
    }


async def _build_global_lead_attribution_payload(
    *,
    repository: ResearchRepository,
    requested_model: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    config_setting = await repository.get_global_setting(GLOBAL_ATTRIBUTION_CONFIG_KEY)
    config = normalize_attribution_config(config_setting.get("value") if config_setting else None)
    model = requested_model if requested_model in {"first_touch", "last_touch", "linear"} else config["default_model"]
    start_at = _parse_iso_datetime(date_from)
    end_at = _parse_iso_datetime(date_to)
    normalized_date_from = start_at.isoformat() if start_at is not None else None
    normalized_date_to = end_at.isoformat() if end_at is not None else None

    leads = await _maybe_call(repository, "list_all_leads", default=[])
    leads_by_id = {int(item["id"]): item for item in leads if item.get("id") is not None}
    conversion_events = await _maybe_call(
        repository,
        "list_all_conversion_events",
        start_at=start_at,
        end_at=end_at,
        default=[],
    )
    spend_rows = await _maybe_call(
        repository,
        "list_all_attribution_spend",
        start_date=start_at.date() if start_at is not None else None,
        end_date=end_at.date() if end_at is not None else None,
        default=[],
    )
    conversion_index = {int(item["id"]): item for item in conversion_events if item.get("id") is not None}
    if model == config["default_model"]:
        attribution_rows = await _maybe_call(
            repository,
            "list_all_attribution_results",
            model=model,
            default=[],
        )
        enriched_rows = []
        for row in attribution_rows:
            conversion_event = conversion_index.get(int(row["conversion_event_id"]))
            if conversion_event is None:
                continue
            lead = leads_by_id.get(int(row["lead_id"]))
            lead_status = str((lead or {}).get("lead_status") or "")
            enriched_rows.append(
                {
                    **row,
                    "lead_status": lead_status,
                    "lead_is_qualified": lead_status in {"qualified", "contacted", "dealt"}
                    or conversion_event.get("event_type") == "qualified",
                    "event_type": conversion_event.get("event_type"),
                    "event_value": conversion_event.get("event_value"),
                    "event_count": conversion_event.get("event_count"),
                }
            )
    else:
        enriched_rows = []
        for conversion_event in conversion_events:
            lead_id = int(conversion_event["lead_id"])
            touchpoints = await repository.list_lead_touchpoints(lead_id)
            lead = leads_by_id.get(lead_id)
            lead_status = str((lead or {}).get("lead_status") or "")
            rows = compute_attribution_rows(
                model=model,
                conversion_event=conversion_event,
                touchpoints=touchpoints,
                window_days=int(config["window_days"]),
                enabled_dimensions=list(config["enabled_dimensions"]),
            )
            for row in rows:
                enriched_rows.append(
                    {
                        "project_id": int(conversion_event["project_id"]),
                        "lead_id": lead_id,
                        "conversion_event_id": int(conversion_event["id"]),
                        "model": model,
                        "dimension": row["dimension"],
                        "dimension_key": row["dimension_key"],
                        "credit": row["credit"],
                        "window_days": int(config["window_days"]),
                        "meta_json": row.get("meta_json") or {},
                        "lead_status": lead_status,
                        "lead_is_qualified": lead_status in {"qualified", "contacted", "dealt"}
                        or conversion_event.get("event_type") == "qualified",
                        "event_type": conversion_event.get("event_type"),
                        "event_value": conversion_event.get("event_value"),
                        "event_count": conversion_event.get("event_count"),
                    }
                )

    diagnostics = []
    if not leads:
        diagnostics.append(
            {
                "code": "global_no_leads",
                "title": "全局暂无正式线索",
                "body": "当前全局模式会先基于所有爬虫帖子、评论和关键词做样本分析。",
            }
        )
    elif not conversion_events:
        diagnostics.append(
            {
                "code": "global_no_conversion_events",
                "title": "全局暂无转化事件",
                "body": "已汇总全局线索，但仍需要导入转化事件才能形成完整归因结果。",
            }
        )

    payload = build_lead_attribution_summary(
        leads=leads,
        conversion_events=conversion_events,
        attribution_rows=enriched_rows,
        spend_rows=spend_rows,
        model=model,
        date_from=normalized_date_from,
        date_to=normalized_date_to,
        diagnostics=diagnostics,
    )
    payload["project_id"] = GLOBAL_ATTRIBUTION_PROJECT_ID
    payload["project_name"] = "全部数据"
    payload["scope"] = "global"
    await _enrich_lead_attribution_content_rows(
        repository,
        payload.get("top_contents") or [],
    )
    if not leads:
        payload["sample_analysis"] = await _build_global_lead_sample_analysis(repository)
    return payload


async def _build_lead_attribution_payload(
    *,
    repository: ResearchRepository,
    project_record: dict,
    requested_model: str,
    date_from: str | None = None,
    date_to: str | None = None,
    persist_snapshot: bool = False,
) -> dict:
    config_setting = await repository.get_global_setting(
        setting_key_for_project(int(project_record["id"]))
    )
    config = normalize_attribution_config(config_setting.get("value") if config_setting else None)
    model = requested_model if requested_model in {"first_touch", "last_touch", "linear"} else config["default_model"]
    start_at = _parse_iso_datetime(date_from)
    end_at = _parse_iso_datetime(date_to)
    normalized_date_from = start_at.isoformat() if start_at is not None else None
    normalized_date_to = end_at.isoformat() if end_at is not None else None
    if model == config["default_model"]:
        snapshot = await repository.get_matching_lead_attribution_daily_snapshot(
            int(project_record["id"]),
            model=model,
            date_from=normalized_date_from,
            date_to=normalized_date_to,
        )
        if snapshot is not None:
            payload = {
                "project_id": project_record["id"],
                "project_name": project_record["name"],
                "summary": snapshot.get("summary") or {},
                "funnel": snapshot.get("funnel") or [],
                "top_platforms": snapshot.get("platform_metrics") or [],
                "top_keywords": snapshot.get("keyword_metrics") or [],
                "top_contents": snapshot.get("content_metrics") or [],
                "top_creators": snapshot.get("creator_metrics") or [],
                "diagnostics": [],
            }
            await _enrich_lead_attribution_content_rows(
                repository,
                payload.get("top_contents") or [],
            )
            if int((payload.get("summary") or {}).get("lead_count") or 0) == 0:
                payload["sample_analysis"] = await _build_lead_sample_analysis(
                    repository,
                    project_record,
                )
            return payload
    leads = await repository.list_project_leads(int(project_record["id"]))
    leads_by_id = {int(item["id"]): item for item in leads if item.get("id") is not None}
    conversion_events = await repository.list_project_conversion_events(
        int(project_record["id"]),
        start_at=start_at,
        end_at=end_at,
    )
    spend_rows = await repository.list_project_attribution_spend(
        int(project_record["id"]),
        start_date=start_at.date() if start_at is not None else None,
        end_date=end_at.date() if end_at is not None else None,
    )
    conversion_index = {int(item["id"]): item for item in conversion_events if item.get("id") is not None}
    if model == config["default_model"]:
        attribution_rows = await repository.list_project_attribution_results(
            int(project_record["id"]),
            model=model,
        )
        enriched_rows = []
        for row in attribution_rows:
            conversion_event = conversion_index.get(int(row["conversion_event_id"]))
            if conversion_event is None:
                continue
            lead = leads_by_id.get(int(row["lead_id"]))
            lead_status = str((lead or {}).get("lead_status") or "")
            enriched_rows.append(
                {
                    **row,
                    "lead_status": lead_status,
                    "lead_is_qualified": lead_status in {"qualified", "contacted", "dealt"}
                    or conversion_event.get("event_type") == "qualified",
                    "event_type": conversion_event.get("event_type"),
                    "event_value": conversion_event.get("event_value"),
                    "event_count": conversion_event.get("event_count"),
                }
            )
    else:
        enriched_rows = []
        for conversion_event in conversion_events:
            lead_id = int(conversion_event["lead_id"])
            touchpoints = await repository.list_lead_touchpoints(lead_id)
            lead = leads_by_id.get(lead_id)
            lead_status = str((lead or {}).get("lead_status") or "")
            rows = compute_attribution_rows(
                model=model,
                conversion_event=conversion_event,
                touchpoints=touchpoints,
                window_days=int(config["window_days"]),
                enabled_dimensions=list(config["enabled_dimensions"]),
            )
            for row in rows:
                enriched_rows.append(
                    {
                        "project_id": int(project_record["id"]),
                        "lead_id": lead_id,
                        "conversion_event_id": int(conversion_event["id"]),
                        "model": model,
                        "dimension": row["dimension"],
                        "dimension_key": row["dimension_key"],
                        "credit": row["credit"],
                        "window_days": int(config["window_days"]),
                        "meta_json": row.get("meta_json") or {},
                        "lead_status": lead_status,
                        "lead_is_qualified": lead_status in {"qualified", "contacted", "dealt"}
                        or conversion_event.get("event_type") == "qualified",
                        "event_type": conversion_event.get("event_type"),
                        "event_value": conversion_event.get("event_value"),
                        "event_count": conversion_event.get("event_count"),
                    }
                )
    diagnostics = []
    if not leads:
        diagnostics.append(
            {
                "code": "no_leads",
                "title": "暂无线索数据",
                "body": "请先导入线索主表后再查看归因报表。",
            }
        )
    elif not conversion_events:
        diagnostics.append(
            {
                "code": "no_conversion_events",
                "title": "暂无转化事件",
                "body": "请先导入加微、首聊或成交事件，归因结果才能成立。",
            }
        )
    payload = build_lead_attribution_summary(
        leads=leads,
        conversion_events=conversion_events,
        attribution_rows=enriched_rows,
        spend_rows=spend_rows,
        model=model,
        date_from=normalized_date_from,
        date_to=normalized_date_to,
        diagnostics=diagnostics,
    )
    payload["project_id"] = project_record["id"]
    payload["project_name"] = project_record["name"]
    await _enrich_lead_attribution_content_rows(
        repository,
        payload.get("top_contents") or [],
    )
    if not leads:
        payload["sample_analysis"] = await _build_lead_sample_analysis(
            repository,
            project_record,
        )
    if persist_snapshot:
        snapshot_payload = build_daily_snapshot_payload(
            project_id=int(project_record["id"]),
            model=model,
            summary_payload=payload,
        )
        await repository.create_lead_attribution_daily_snapshot(snapshot_payload)
    return payload


def _filter_project_jobs_by_platform(jobs: list[dict[str, Any]], platform: str | None) -> list[dict[str, Any]]:
    if not platform:
        return list(jobs)
    return [
        item
        for item in jobs
        if not item.get("platforms") or platform in (item.get("platforms") or [])
    ]


def _normalize_project_text(value: object) -> str:
    return str(value or "").strip().lower()


def _matches_project_keyword(value: object, project_keywords: list[str]) -> bool:
    if not project_keywords:
        return True
    normalized = _normalize_project_text(value)
    if not normalized:
        return False
    for keyword in project_keywords:
        candidate = _normalize_project_text(keyword)
        if candidate and (candidate in normalized or normalized in candidate):
            return True
    return False


def _project_keyword_hit_count(values: list[object], project_keywords: list[str]) -> int:
    count = 0
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_project_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if _matches_project_keyword(normalized, project_keywords):
            count += 1
    return count


def _platform_matches_scope(platform: object, project_platforms: list[str]) -> bool:
    if not project_platforms:
        return True
    candidate = str(platform or "").strip()
    return not candidate or candidate in project_platforms


def _filter_project_posts(
    posts: list[dict[str, Any]],
    *,
    platform: str | None,
    start_at: datetime,
    end_at: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for post in posts:
        if platform and post.get("platform") != platform:
            continue
        publish_time = post.get("publish_time")
        if isinstance(publish_time, datetime):
            candidate = publish_time if publish_time.tzinfo else publish_time.replace(tzinfo=timezone.utc)
            candidate = candidate.astimezone(timezone.utc)
            if candidate < start_at or candidate > end_at:
                continue
        rows.append(post)
    return rows


def _keyword_snapshot_priority(snapshot: dict[str, Any], project_keywords: list[str]) -> tuple[int, object]:
    return (
        _project_keyword_hit_count([snapshot.get("keyword")], project_keywords),
        snapshot.get("snapshot_date") or snapshot.get("created_at") or "",
    )


def _content_snapshot_priority(snapshot: dict[str, Any], project_keywords: list[str]) -> tuple[int, object]:
    values = list((snapshot.get("keyword_distribution") or {}).keys())
    top_posts = (snapshot.get("evidence") or {}).get("top_posts") or []
    values.extend(item.get("title") for item in top_posts if isinstance(item, dict))
    return (
        _project_keyword_hit_count(values, project_keywords),
        snapshot.get("snapshot_date") or snapshot.get("created_at") or "",
    )


def _competitor_snapshot_priority(snapshot: dict[str, Any], project_keywords: list[str]) -> tuple[int, object]:
    values = list((snapshot.get("keyword_distribution") or {}).keys())
    top_posts = (snapshot.get("evidence") or {}).get("top_posts") or []
    values.extend(item.get("title") for item in top_posts if isinstance(item, dict))
    return (
        _project_keyword_hit_count(values, project_keywords),
        snapshot.get("snapshot_date") or snapshot.get("created_at") or "",
    )


def _filter_project_keyword_heat_snapshots(
    snapshots: list[dict[str, Any]],
    *,
    project_keywords: list[str],
    project_platforms: list[str],
) -> list[dict[str, Any]]:
    platform_scoped = [
        item for item in snapshots if _platform_matches_scope(item.get("platform"), project_platforms)
    ]
    matched = [
        item for item in platform_scoped if _matches_project_keyword(item.get("keyword"), project_keywords)
    ]
    rows = matched or platform_scoped
    return sorted(
        rows,
        key=lambda item: _keyword_snapshot_priority(item, project_keywords),
        reverse=True,
    )[:40]


def _filter_project_content_snapshots(
    snapshots: list[dict[str, Any]],
    *,
    project_keywords: list[str],
    project_platforms: list[str],
) -> list[dict[str, Any]]:
    platform_scoped = [
        item for item in snapshots if _platform_matches_scope(item.get("platform"), project_platforms)
    ]
    matched = []
    for item in platform_scoped:
        values = list((item.get("keyword_distribution") or {}).keys())
        top_posts = (item.get("evidence") or {}).get("top_posts") or []
        values.extend(post.get("title") for post in top_posts if isinstance(post, dict))
        if _project_keyword_hit_count(values, project_keywords) > 0:
            matched.append(item)
    rows = matched or platform_scoped
    return sorted(
        rows,
        key=lambda item: _content_snapshot_priority(item, project_keywords),
        reverse=True,
    )[:30]


def _filter_project_competitor_snapshots(
    snapshots: list[dict[str, Any]],
    *,
    project_keywords: list[str],
    project_platforms: list[str],
) -> list[dict[str, Any]]:
    platform_scoped = [
        item for item in snapshots if _platform_matches_scope(item.get("platform"), project_platforms)
    ]
    matched = []
    for item in platform_scoped:
        values = list((item.get("keyword_distribution") or {}).keys())
        top_posts = (item.get("evidence") or {}).get("top_posts") or []
        values.extend(post.get("title") for post in top_posts if isinstance(post, dict))
        if _project_keyword_hit_count(values, project_keywords) > 0:
            matched.append(item)
    rows = matched or platform_scoped
    return sorted(
        rows,
        key=lambda item: _competitor_snapshot_priority(item, project_keywords),
        reverse=True,
    )[:30]


def _normalize_project_ai_topic_ideas(
    rows: list[dict[str, Any]],
    *,
    platform: str | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        idea_platform = row.get("platform")
        if platform and idea_platform and idea_platform != platform:
            continue
        normalized.append(
            {
                "id": row.get("id") or f"project-ai-{index}",
                "title": row.get("title") or row.get("topic") or row.get("name"),
                "platform": idea_platform,
                "target_audience": row.get("target_audience") or row.get("audience"),
                "keywords": row.get("keywords") or [],
                "content_angle": row.get("content_angle") or row.get("angle"),
                "outline": row.get("outline") or [],
                "reason": row.get("reason") or row.get("summary") or "",
                "risk_notes": row.get("risk_notes") or [],
                "evidence": row.get("evidence") or {},
                "confidence": row.get("confidence"),
            }
        )
    return normalized


def _build_project_content_strategy_refresh_payload(
    *,
    project_record: dict[str, Any],
    strategy_state: dict[str, Any],
) -> dict[str, Any]:
    ai_insights = strategy_state.get("ai_insights") or {}
    return {
        "cadence": {
            "value": project_record.get("refresh_cadence") or "off",
            "interval_minutes": content_strategy_refresh_interval_minutes(project_record),
            "custom_interval_value": project_record.get("custom_interval_value"),
            "custom_interval_unit": project_record.get("custom_interval_unit"),
        },
        "scheduled_refresh": strategy_state.get("scheduled_refresh") or {},
        "manual_analysis": strategy_state.get("manual_analysis") or {},
        "ai_insights": {
            "mode": ai_insights.get("mode") or "none",
            "status": ai_insights.get("status") or "idle",
            "generated_at": ai_insights.get("generated_at"),
            "provider": ai_insights.get("provider"),
            "executive_summary": ai_insights.get("executive_summary") or "",
            "strategy_summary_source": ai_insights.get("strategy_summary_source") or "none",
            "section_statuses": ai_insights.get("section_statuses") or {},
            "error": ai_insights.get("error"),
        },
        "updated_at": strategy_state.get("_updated_at"),
    }


def _slug_project_key(value: object) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_")
    return "".join(
        ch if ch.isalnum() or ch == "_" or ("\u4e00" <= ch <= "\u9fff") else "_"
        for ch in raw
    ).strip("_")


_PROJECT_TOKEN_STOPWORDS = {
    "collection",
    "initial",
    "project",
    "research",
    "topic",
}


def _project_semantic_tokens(value: object) -> set[str]:
    raw = str(value or "").strip().lower()
    if not raw:
        return set()
    tokens = set(re.findall(r"[a-z0-9]+", raw))
    if "education" in raw or "\u6559\u80b2" in raw:
        tokens.update({"education", "\u6559\u80b2"})
    if "summer" in raw or "\u6691" in raw:
        tokens.add("summer")
    return {
        token
        for token in tokens
        if len(token) > 1 and token not in _PROJECT_TOKEN_STOPWORDS
    }


def _job_semantic_tokens(job: dict) -> set[str]:
    tokens: set[str] = set()
    for value in (job.get("topic"), project_key_for_job(job)):
        tokens.update(_project_semantic_tokens(value))
    return tokens


def _is_semantic_project_job(project_tokens: set[str], job: dict) -> bool:
    if not project_tokens:
        return False
    job_tokens = _job_semantic_tokens(job)
    project_digits = {token for token in project_tokens if token.isdigit()}
    job_digits = {token for token in job_tokens if token.isdigit()}
    if project_digits and (
        not project_digits.issubset(job_digits)
        or bool(job_digits - project_digits)
    ):
        return False
    return len(project_tokens & job_tokens) >= 2


async def _project_jobs_for_sample_analysis(
    repository: ResearchRepository,
    project_record: dict,
) -> list[dict]:
    keys = {
        str(project_record.get("id") or ""),
        str(project_record.get("name") or ""),
        _slug_project_key(project_record.get("name")),
    }
    keys = {key for key in keys if key}
    jobs = await _maybe_call(
        repository,
        "list_jobs_for_project",
        sorted(keys),
        default=[],
    )
    all_jobs = await _maybe_call(repository, "list_jobs", default=[])
    normalized_keys = {_slug_project_key(key) for key in keys}
    project_tokens: set[str] = set()
    for key in keys:
        project_tokens.update(_project_semantic_tokens(key))
    seen_ids = {int(job["id"]) for job in jobs if job.get("id") is not None}
    related_jobs = [
        job
        for job in all_jobs
        if int(job["id"]) not in seen_ids
        and (
            _slug_project_key(project_key_for_job(job)) in normalized_keys
            or _is_semantic_project_job(project_tokens, job)
        )
    ]
    return [*jobs, *related_jobs]


def _engagement_score(post: dict) -> int:
    engagement = post.get("engagement_json") or {}
    total = 0
    for key in (
        "like_count",
        "liked_count",
        "likes",
        "comment_count",
        "comments",
        "share_count",
        "shares",
        "collect_count",
        "favorite_count",
    ):
        try:
            total += int(float(engagement.get(key) or 0))
        except (TypeError, ValueError):
            continue
    return total


def _sample_text(value: object, *, limit: int = 120) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _count_keyword_hits(keywords: Counter, texts: list[str]) -> list[dict]:
    rows = []
    lowered_texts = [text.lower() for text in texts if text]
    for keyword, base_count in keywords.items():
        key = str(keyword or "").strip()
        if not key:
            continue
        lowered = key.lower()
        hits = sum(text.count(lowered) for text in lowered_texts)
        rows.append(
            {
                "keyword": key,
                "sample_count": int(base_count),
                "hit_count": int(hits),
                "score": int(hits + base_count),
            }
        )
    return sorted(rows, key=lambda item: item["score"], reverse=True)[:10]


async def _build_lead_sample_analysis(
    repository: ResearchRepository,
    project_record: dict,
) -> dict:
    jobs = await _project_jobs_for_sample_analysis(repository, project_record)
    job_ids = [int(job["id"]) for job in jobs if job.get("id") is not None]
    stats_by_job_id = await _maybe_call(
        repository,
        "get_job_stats_many",
        job_ids,
        default={},
    )
    posts_page = await _maybe_call(
        repository,
        "list_posts_page",
        job_ids=job_ids,
        limit=120,
        offset=0,
        default={"posts": [], "total": 0},
    )
    posts = posts_page.get("posts") or []
    comments: list[dict] = []
    for job_id in job_ids[:20]:
        comments.extend(
            await _maybe_call(
                repository,
                "list_comments",
                job_id,
                limit=120,
                default=[],
            )
        )

    totals = {
        "job_count": len(job_ids),
        "raw_record_count": 0,
        "post_count": 0,
        "comment_count": 0,
        "creator_count": 0,
    }
    platform_posts: Counter = Counter()
    platform_comments: Counter = Counter()
    for stats in (stats_by_job_id or {}).values():
        totals["raw_record_count"] += int(stats.get("raw_records") or 0)
        totals["post_count"] += int(stats.get("posts") or 0)
        totals["comment_count"] += int(stats.get("comments") or 0)
        totals["creator_count"] += int(stats.get("authors") or stats.get("creators") or 0)
        by_platform = stats.get("by_platform") or {}
        platform_posts.update(by_platform.get("posts") or {})
        platform_comments.update(by_platform.get("comments") or {})
    if not platform_posts:
        platform_posts.update(post.get("platform") or "unknown" for post in posts)
    if not platform_comments:
        platform_comments.update(comment.get("platform") or "unknown" for comment in comments)

    all_platforms = sorted(set(platform_posts) | set(platform_comments))
    platform_rows = [
        {
            "dimension_key": platform,
            "platform": platform,
            "post_count": int(platform_posts.get(platform) or 0),
            "comment_count": int(platform_comments.get(platform) or 0),
            "sample_count": int((platform_posts.get(platform) or 0) + (platform_comments.get(platform) or 0)),
        }
        for platform in all_platforms
    ]
    platform_rows.sort(key=lambda item: item["sample_count"], reverse=True)

    top_contents = []
    for post in sorted(posts, key=_engagement_score, reverse=True)[:10]:
        top_contents.append(
            {
                "post_id": post.get("id"),
                "title": _sample_text(post.get("title") or post.get("content") or f"post:{post.get('id')}"),
                "platform": post.get("platform"),
                "publish_time": post.get("publish_time"),
                "engagement_score": _engagement_score(post),
                "url": post.get("url"),
            }
        )

    keyword_counter: Counter = Counter()
    for job in jobs:
        keyword_counter.update(job.get("keywords") or [])
    text_samples = [
        str(post.get("title") or "") + " " + str(post.get("content") or "")
        for post in posts
    ] + [str(comment.get("content") or "") for comment in comments]
    top_keywords = _count_keyword_hits(keyword_counter, text_samples)

    intent_terms = ["咨询", "价格", "多少钱", "报名", "购买", "怎么买", "链接", "私信", "客服", "加微信", "课程"]
    intent_counter: Counter = Counter()
    intent_comment_count = 0
    for comment in comments:
        content = str(comment.get("content") or "")
        matched = [term for term in intent_terms if term in content]
        if matched:
            intent_comment_count += 1
            intent_counter.update(matched)

    diagnostics = []
    if totals["post_count"] == 0:
        diagnostics.append(
            {
                "code": "no_sample_posts",
                "title": "暂无内容样本",
                "body": "当前项目还没有可用于样本分析的帖子数据。",
            }
        )
    if totals["comment_count"] == 0:
        diagnostics.append(
            {
                "code": "no_sample_comments",
                "title": "评论样本不足",
                "body": "评论样本不足会影响意向词和需求判断。",
            }
        )

    return {
        "mode": "sample_analysis",
        "summary": {
            **totals,
            "intent_comment_count": intent_comment_count,
            "intent_comment_rate": (intent_comment_count / totals["comment_count"]) if totals["comment_count"] else 0,
        },
        "platform_rows": platform_rows[:10],
        "top_contents": top_contents,
        "top_keywords": top_keywords,
        "intent_terms": [
            {"term": term, "count": count}
            for term, count in intent_counter.most_common(10)
        ],
        "diagnostics": diagnostics,
    }


async def _build_global_lead_sample_analysis(
    repository: ResearchRepository,
) -> dict:
    jobs = await _maybe_call(repository, "list_jobs", default=[])
    job_ids = [int(job["id"]) for job in jobs if job.get("id") is not None]
    stats_by_job_id = await _maybe_call(
        repository,
        "get_job_stats_many",
        job_ids,
        default={},
    )
    posts_page = await _maybe_call(
        repository,
        "list_posts_page",
        job_ids=job_ids,
        limit=120,
        offset=0,
        default={"posts": [], "total": 0},
    )
    posts = posts_page.get("posts") or []
    comments = await _maybe_call(
        repository,
        "list_all_comments",
        limit=2400,
        default=[],
    )

    totals = {
        "job_count": len(job_ids),
        "raw_record_count": 0,
        "post_count": 0,
        "comment_count": 0,
        "creator_count": 0,
    }
    platform_posts: Counter = Counter()
    platform_comments: Counter = Counter()
    for stats in (stats_by_job_id or {}).values():
        totals["raw_record_count"] += int(stats.get("raw_records") or 0)
        totals["post_count"] += int(stats.get("posts") or 0)
        totals["comment_count"] += int(stats.get("comments") or 0)
        totals["creator_count"] += int(stats.get("authors") or stats.get("creators") or 0)
        by_platform = stats.get("by_platform") or {}
        platform_posts.update(by_platform.get("posts") or {})
        platform_comments.update(by_platform.get("comments") or {})
    if not platform_posts:
        platform_posts.update(post.get("platform") or "unknown" for post in posts)
    if not platform_comments:
        platform_comments.update(comment.get("platform") or "unknown" for comment in comments)

    all_platforms = sorted(set(platform_posts) | set(platform_comments))
    platform_rows = [
        {
            "dimension_key": platform,
            "platform": platform,
            "post_count": int(platform_posts.get(platform) or 0),
            "comment_count": int(platform_comments.get(platform) or 0),
            "sample_count": int((platform_posts.get(platform) or 0) + (platform_comments.get(platform) or 0)),
        }
        for platform in all_platforms
    ]
    platform_rows.sort(key=lambda item: item["sample_count"], reverse=True)

    top_contents = []
    for post in sorted(posts, key=_engagement_score, reverse=True)[:10]:
        top_contents.append(
            {
                "post_id": post.get("id"),
                "title": _sample_text(post.get("title") or post.get("content") or f"post:{post.get('id')}"),
                "platform": post.get("platform"),
                "publish_time": post.get("publish_time"),
                "engagement_score": _engagement_score(post),
                "url": post.get("url"),
            }
        )

    keyword_counter: Counter = Counter()
    for job in jobs:
        keyword_counter.update(job.get("keywords") or [])
    text_samples = [
        str(post.get("title") or "") + " " + str(post.get("content") or "")
        for post in posts
    ] + [str(comment.get("content") or "") for comment in comments]
    top_keywords = _count_keyword_hits(keyword_counter, text_samples)

    intent_terms = ["咨询", "价格", "多少钱", "报名", "购买", "怎么买", "链接", "私信", "客服", "加微信", "课程"]
    intent_counter: Counter = Counter()
    intent_comment_count = 0
    for comment in comments:
        content = str(comment.get("content") or "")
        matched = [term for term in intent_terms if term in content]
        if matched:
            intent_comment_count += 1
            intent_counter.update(matched)

    diagnostics = []
    if totals["post_count"] == 0:
        diagnostics.append(
            {
                "code": "global_no_sample_posts",
                "title": "全局暂无内容样本",
                "body": "当前账号/数据库还没有可用于全局分析的帖子数据。",
            }
        )
    if totals["comment_count"] == 0:
        diagnostics.append(
            {
                "code": "global_no_sample_comments",
                "title": "全局评论样本不足",
                "body": "全局评论样本不足会影响意向词和需求判断。",
            }
        )

    return {
        "mode": "sample_analysis",
        "summary": {
            **totals,
            "intent_comment_count": intent_comment_count,
            "intent_comment_rate": (intent_comment_count / totals["comment_count"]) if totals["comment_count"] else 0,
        },
        "platform_rows": platform_rows[:10],
        "top_contents": top_contents,
        "top_keywords": top_keywords,
        "intent_terms": [
            {"term": term, "count": count}
            for term, count in intent_counter.most_common(10)
        ],
        "diagnostics": diagnostics,
    }


async def _enrich_lead_attribution_content_rows(
    repository: ResearchRepository,
    content_rows: list[dict],
) -> None:
    post_ids = [
        int(str(item["dimension_key"]).split("post:", 1)[1])
        for item in content_rows
        if str(item.get("dimension_key") or "").startswith("post:")
    ]
    posts = await repository.get_posts_by_ids(post_ids)
    posts_by_id = {int(item["id"]): item for item in posts if item.get("id") is not None}
    for row in content_rows:
        key = str(row.get("dimension_key") or "")
        if not key.startswith("post:"):
            continue
        post_id = int(key.split("post:", 1)[1])
        post = posts_by_id.get(post_id)
        if post:
            row["title"] = post.get("title") or post.get("content") or key
            row["platform"] = post.get("platform")
            row["source_keyword"] = str((post.get("engagement_json") or {}).get("source_keyword") or "")


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


async def _resolve_strategy_ai_provider(
    repository: ResearchRepository,
    *,
    provider_config_id: int | None,
) -> dict[str, Any]:
    if provider_config_id:
        provider = await repository.get_ai_provider(provider_config_id, include_secret=True)
        if provider is None:
            raise ValueError("AI provider config not found")
        return provider

    env_api_key = os.getenv("AI_GATEWAY_API_KEY")
    if env_api_key:
        return {
            "id": None,
            "name": os.getenv("AI_GATEWAY_NAME", "AI Gateway"),
            "base_url": os.getenv("AI_GATEWAY_BASE_URL", "https://4router.net/v1"),
            "api_key": env_api_key,
            "model": os.getenv("AI_GATEWAY_MODEL", "gpt-5.4-mini"),
            "timeout": int(os.getenv("AI_GATEWAY_TIMEOUT", "60")),
            "default_params": {
                "temperature": float(os.getenv("AI_GATEWAY_TEMPERATURE", "0.2")),
                "max_tokens": int(os.getenv("AI_GATEWAY_MAX_TOKENS", "1800")),
            },
        }

    providers = await repository.list_ai_providers()
    enabled = [item for item in providers if item.get("enabled") and item.get("api_key_set")]
    preferred = next((item for item in enabled if "gateway" in str(item.get("name") or "").lower()), None)
    selected = preferred or (enabled[0] if enabled else None)
    if selected is None:
        raise ValueError("AI_GATEWAY_API_KEY is not configured and no enabled AI provider exists")
    provider = await repository.get_ai_provider(selected["id"], include_secret=True)
    if provider is None:
        raise ValueError("AI provider config not found")
    return provider


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
