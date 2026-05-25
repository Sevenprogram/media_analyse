import asyncio
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import config
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from api.deps.auth import require_current_user
from media_platform.justoneapi.client import resolve_justone_api_key
from media_platform.tikhub.client import resolve_tikhub_api_key
from api.routers.research import (
    require_research_database,
    schedule_and_execute_research_job,
    wait_for_research_job_status,
)
from research.creator_search import (
    extract_creator_candidates_from_discovery_job,
    export_creator_candidates_csv,
    parse_search_intent,
    search_creators,
)
from research.auto_pooling import auto_pool_a_tier_candidates
from research.candidate_tiering import tier_creator_candidates
from research.monitor_pools import MonitorPoolService, automation_select_candidates
from research.realtime_creator_discovery import (
    REALTIME_PLATFORMS,
    probe_realtime_platforms,
)
from research.repository import ResearchRepository
from research.schemas import (
    CreatorCandidateUpsert,
    CreatorSearchIntentRequest,
    CreatorSearchRequest,
    MonitorPoolAddCreatorsRequest,
    MonitorPoolCreate,
    MonitorPoolUpdate,
)
from research.tikhub_creator_metrics import enrich_creator_metrics_from_tikhub

router = APIRouter(
    prefix="/creator-search",
    tags=["creator-search"],
    dependencies=[Depends(require_current_user)],
)

CREATOR_SEARCH_TASKS: dict[str, dict] = {}


class CreatorSearchTaskRequest(CreatorSearchRequest):
    wait: bool = False


class CreatorSearchSessionPersistRequest(BaseModel):
    raw_query: str = Field(default="", max_length=500)
    selected_vertical_id: int | None = Field(default=None, ge=1)
    search_payload: dict[str, Any] = Field(default_factory=dict)
    view_state: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    realtime: dict[str, Any] = Field(default_factory=dict)
    progress: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
    result_summary: str | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)
    saved: bool = False
    saved_name: str | None = Field(default=None, max_length=255)
    status: str = Field(default="completed", max_length=32)


class CreatorSearchSessionSaveRequest(BaseModel):
    saved: bool = True
    saved_name: str | None = Field(default=None, max_length=255)


@router.post("/parse-intent")
async def parse_creator_search_intent(request: CreatorSearchIntentRequest):
    require_research_database()
    repository = ResearchRepository()
    tag_definitions = await repository.list_tag_definitions(
        vertical_id=request.selected_vertical_id,
        enabled_only=True,
    )
    verticals = await repository.list_verticals(enabled_only=True)
    intent = parse_search_intent(
        raw_query=request.raw_query,
        verticals=verticals,
        tag_definitions=tag_definitions,
        selected_vertical_id=request.selected_vertical_id,
    )
    await repository.create_search_intent(
        {
            "raw_query": intent["raw_query"],
            "detected_verticals": [item["id"] for item in intent["detected_verticals"]],
            "selected_vertical_id": intent["selected_vertical_id"],
            "required_tags": intent["required_tags"],
            "optional_tags": intent["optional_tags"],
            "negative_tags": intent["negative_tags"],
            "confidence": intent["confidence"],
            "parser_source": intent["parser_source"],
        }
    )
    return intent


@router.post("/search")
async def search_creator_profiles(request: CreatorSearchRequest):
    require_research_database()
    result = await search_creators(
        ResearchRepository(),
        request.model_dump(mode="python"),
    )
    result["results"] = tier_creator_candidates(result.get("results") or [])
    return result


@router.post("/search-sessions")
async def persist_creator_search_session(request: CreatorSearchSessionPersistRequest):
    require_research_database()
    repository = ResearchRepository()
    session = await repository.create_creator_search_session(
        {
            "raw_query": request.raw_query,
            "selected_vertical_id": request.selected_vertical_id,
            "search_payload_json": request.search_payload,
            "view_state_json": request.view_state,
            "diagnostics_json": request.diagnostics,
            "realtime_json": request.realtime,
            "progress_json": request.progress,
            "message": request.message,
            "result_summary": request.result_summary,
            "result_count": len(request.results),
            "saved": request.saved,
            "saved_name": request.saved_name,
            "status": request.status,
        },
        results=request.results,
    )
    return {"session": session}


@router.get("/search-sessions/latest")
async def get_latest_creator_search_session():
    require_research_database()
    session = await ResearchRepository().get_latest_creator_search_session()
    return {"session": session}


@router.post("/search-sessions/{session_id}/save")
async def save_creator_search_session(session_id: int, request: CreatorSearchSessionSaveRequest):
    require_research_database()
    session = await ResearchRepository().mark_creator_search_session_saved(
        session_id,
        saved=request.saved,
        saved_name=request.saved_name,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Creator search session not found")
    return {"session": session}


@router.post("/search-tasks")
async def start_creator_search_task(request: CreatorSearchTaskRequest):
    require_research_database()
    task_id = uuid4().hex
    payload = request.model_dump(mode="python")
    wait = bool(payload.pop("wait", False))
    task = _new_creator_search_task(task_id, payload)
    CREATOR_SEARCH_TASKS[task_id] = task
    if wait:
        await _run_creator_search_task(task_id, payload)
    else:
        asyncio.create_task(_run_creator_search_task(task_id, payload))
    return CREATOR_SEARCH_TASKS[task_id]


@router.get("/search-tasks/{task_id}")
async def get_creator_search_task(task_id: str):
    require_research_database()
    task = CREATOR_SEARCH_TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Creator search task not found")
    return task


@router.post("/search-tasks/{task_id}/cancel")
async def cancel_creator_search_task(task_id: str):
    require_research_database()
    task = CREATOR_SEARCH_TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Creator search task not found")
    if task["status"] in {"completed", "failed", "cancelled"}:
        return task
    task["status"] = "cancelled"
    task["progress"] = {"stage": "cancelled", "label": "Cancelled", "percent": task["progress"].get("percent", 0)}
    task["updated_at"] = _now_iso()
    _append_creator_search_log(task, stage="cancelled", level="warning", message="达人搜索任务已取消")
    return task


def _new_creator_search_task(task_id: str, payload: dict) -> dict:
    now = _now_iso()
    return {
        "task_id": task_id,
        "status": "pending",
        "request": payload,
        "progress": {"stage": "queued", "label": "Queued", "percent": 5},
        "logs": [
            {
                "created_at": now,
                "stage": "queued",
                "level": "info",
                "message": _creator_search_log_message("queued", payload=payload),
            }
        ],
        "result": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }


async def _run_creator_search_task(task_id: str, payload: dict) -> None:
    task = CREATOR_SEARCH_TASKS.get(task_id)
    if task is None or task.get("status") == "cancelled":
        return
    try:
        realtime_only = payload.get("search_scope") == "realtime_only"
        if realtime_only:
            _update_creator_search_task(task, "running", "realtime", "Searching realtime platforms", 30)
        else:
            _update_creator_search_task(task, "running", "database", "Searching database", 20)
        if payload.get("include_realtime") and not realtime_only:
            _update_creator_search_task(task, "running", "realtime", "Searching realtime platforms", 50)
        result = await search_creators(ResearchRepository(), payload)
        if task.get("status") == "cancelled":
            return
        _update_creator_search_task(task, "running", "merging", "Merging results", 90)
        result["results"] = tier_creator_candidates(result.get("results") or [])
        task["result"] = result
        task["status"] = "completed"
        task["progress"] = result.get("progress") or {"stage": "complete", "label": "Complete", "percent": 100}
        task["updated_at"] = _now_iso()
        _append_creator_search_log(
            task,
            stage="complete",
            message=_creator_search_log_message("complete", result=result),
        )
    except Exception as exc:
        task["status"] = "failed"
        task["error"] = str(exc)
        task["progress"] = {"stage": "failed", "label": "Failed", "percent": 100}
        task["updated_at"] = _now_iso()
        _append_creator_search_log(task, stage="failed", level="error", message=str(exc))


def _update_creator_search_task(task: dict, status: str, stage: str, label: str, percent: int) -> None:
    task["status"] = status
    task["progress"] = {"stage": stage, "label": label, "percent": percent}
    task["updated_at"] = _now_iso()
    _append_creator_search_log(
        task,
        stage=stage,
        message=_creator_search_log_message(stage, payload=task.get("request") or {}),
    )


def _append_creator_search_log(task: dict, *, stage: str, message: str, level: str = "info") -> None:
    logs = task.setdefault("logs", [])
    entry = {
        "created_at": _now_iso(),
        "stage": stage,
        "level": level,
        "message": message,
    }
    if logs and logs[-1].get("stage") == stage and logs[-1].get("message") == message:
        logs[-1] = entry
    else:
        logs.append(entry)
    del logs[:-50]


def _creator_search_log_message(
    stage: str,
    *,
    payload: dict | None = None,
    result: dict | None = None,
) -> str:
    payload = payload or {}
    if stage == "queued":
        platforms = ", ".join(payload.get("platforms") or []) or "未选择平台"
        mode = "实时搜索" if payload.get("search_scope") == "realtime_only" else "达人搜索"
        return f"{mode}任务已提交；平台：{platforms}；上限：{payload.get('limit') or 50}"
    if stage == "database":
        return "正在检索本地达人画像、标签和近期内容证据"
    if stage == "realtime":
        if payload.get("search_scope") == "realtime_only":
            return "正在请求小红书 / 抖音实时发现，并保存命中达人"
        return "正在请求实时平台发现，并准备与本地结果合并"
    if stage == "merging":
        if payload.get("search_scope") == "realtime_only":
            return "正在整理实时结果、去重并计算达人分层"
        return "正在合并结果、去重并计算达人分层"
    if stage == "complete":
        count = len((result or {}).get("results") or [])
        return f"达人搜索完成；返回 {count} 个结果"
    return stage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/candidate-pool")
async def upsert_creator_candidate(request: CreatorCandidateUpsert):
    require_research_database()
    payload = request.model_dump(mode="python")
    payload["matched_tags_json"] = payload.pop("matched_tags")
    payload["evidence_json"] = payload.pop("evidence")
    return await ResearchRepository().upsert_creator_candidate(payload)


@router.get("/candidate-pool")
async def list_creator_candidates(
    pool_name: str | None = None,
    platform: str | None = None,
    vertical_id: int | None = None,
    include_profile_candidates: bool = False,
):
    require_research_database()
    repository = ResearchRepository()
    candidates = await repository.list_creator_candidates(
        pool_name=pool_name,
        platform=platform,
        vertical_id=vertical_id,
    )
    return {
        "candidates": tier_creator_candidates(await _enrich_creator_candidates_for_display(
            repository,
            candidates,
            include_profile_candidates=include_profile_candidates,
            platform=platform,
            pool_name=pool_name,
            vertical_id=vertical_id,
        ))
    }


@router.post("/candidate-pool/auto-pool")
async def auto_pool_creator_candidates(payload: dict):
    require_research_database()
    pool_id = int(payload.get("pool_id") or 0)
    if pool_id <= 0:
        raise HTTPException(status_code=400, detail="pool_id is required")
    try:
        candidates = payload.get("candidates")
        if candidates is None:
            repository = ResearchRepository()
            candidates = await repository.list_creator_candidates(
                pool_name=payload.get("pool_name"),
                platform=payload.get("platform"),
                vertical_id=payload.get("vertical_id"),
            )
        return await auto_pool_a_tier_candidates(
            ResearchRepository(),
            pool_id=pool_id,
            candidates=tier_creator_candidates(candidates),
            daily_cap=int(payload.get("daily_cap") or 20),
            crawl_now=bool(payload.get("crawl_now", False)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _enrich_creator_candidates_for_display(
    repository,
    candidates: list[dict],
    *,
    include_profile_candidates: bool,
    platform: str | None,
    pool_name: str | None,
    vertical_id: int | None,
) -> list[dict]:
    enriched = []
    seen: set[tuple[str | None, str | None]] = set()
    for item in candidates:
        next_item = {"source": "candidate_pool", **item}
        item_platform = item.get("platform")
        creator_id = item.get("creator_id")
        seen.add((item_platform, creator_id))
        profile = await _get_creator_profile(repository, item_platform, creator_id)
        if profile:
            _merge_profile_fields(next_item, profile)
        enriched.append(next_item)

    if not include_profile_candidates or pool_name or vertical_id is not None:
        return enriched

    profiles = await _list_creator_profiles(
        repository,
        platforms=[platform] if platform else None,
    )
    for profile in profiles:
        key = (profile.get("platform"), profile.get("creator_id"))
        if key in seen:
            continue
        profile_candidate = {
            "id": f"profile:{profile.get('platform')}:{profile.get('creator_id')}",
            "platform": profile.get("platform"),
            "creator_id": profile.get("creator_id"),
            "pool_name": "local-profile",
            "vertical_id": None,
            "match_score": None,
            "matched_tags": [],
            "evidence": {"source": "creator_profile"},
            "notes": "来自本地达人画像，尚未进入候选池评分",
            "source": "local_profile",
        }
        _merge_profile_fields(profile_candidate, profile)
        enriched.append(profile_candidate)
    return enriched


async def _get_creator_profile(repository, platform: str | None, creator_id: str | None) -> dict | None:
    if not platform or not creator_id or not hasattr(repository, "get_creator_profile"):
        return None
    return await repository.get_creator_profile(platform, creator_id)


async def _list_creator_profiles(repository, platforms: list[str] | None) -> list[dict]:
    if not hasattr(repository, "list_creator_profiles"):
        return []
    return await repository.list_creator_profiles(platforms=platforms)


def _merge_profile_fields(target: dict, profile: dict) -> None:
    for key in (
        "display_name",
        "profile_url",
        "bio",
        "follower_count",
        "following_count",
        "post_count",
        "avg_engagement_rate",
        "hot_post_rate",
        "recent_post_count_30d",
        "latest_snapshot_at",
        "tag_summary_json",
    ):
        if profile.get(key) not in (None, ""):
            target[key] = profile[key]


@router.post("/scene-packs/{scene_pack_id}/score-candidates")
async def score_scene_pack_candidates(
    scene_pack_id: int,
    platform: str | None = None,
    limit: int = 100,
):
    require_research_database()
    return {
        "candidates": await ResearchRepository().score_creator_candidates_for_scene_pack(
            scene_pack_id=scene_pack_id,
            platform=platform,
            limit=limit,
        )
    }


@router.post("/monitor-pools")
async def create_monitor_pool(request: MonitorPoolCreate):
    require_research_database()
    return await ResearchRepository().create_monitor_pool(
        request.model_dump(mode="python")
    )


@router.get("/monitor-pools")
async def list_monitor_pools(enabled_only: bool = False):
    require_research_database()
    return {"pools": await ResearchRepository().list_monitor_pools(enabled_only=enabled_only)}


@router.patch("/monitor-pools/{pool_id}")
async def update_monitor_pool(pool_id: int, payload: MonitorPoolUpdate):
    require_research_database()
    repository = ResearchRepository()
    result = await repository.update_monitor_pool(
        pool_id,
        payload.model_dump(mode="python", exclude_unset=True),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Monitor pool not found")
    sync = await MonitorPoolService(repository).sync_pool_job(pool_id)
    return {**sync["pool"], "pool": sync["pool"], "job": sync["job"]}


@router.get("/monitor-pools/{pool_id}/creators")
async def list_monitor_pool_creators(pool_id: int, enabled_only: bool = False):
    require_research_database()
    repository = ResearchRepository()
    if await repository.get_monitor_pool(pool_id) is None:
        raise HTTPException(status_code=404, detail="Monitor pool not found")
    return {
        "creators": await repository.list_monitor_pool_creators(
            pool_id,
            enabled_only=enabled_only,
        )
    }


@router.post("/monitor-pools/{pool_id}/creators")
async def add_creators_to_monitor_pool(
    pool_id: int,
    request: MonitorPoolAddCreatorsRequest,
):
    require_research_database()
    repository = ResearchRepository()
    service = MonitorPoolService(
        repository,
        execution_callback=lambda job_id: schedule_and_execute_research_job(
            job_id,
            background=True,
            force_schedule=True,
        ),
    )
    try:
        creators = list(request.creators)
        for profile_id in request.account_profile_ids:
            profile = await repository.get_account_profile(profile_id)
            if profile is None:
                raise HTTPException(status_code=404, detail=f"Account profile not found: {profile_id}")
            creators.append(
                {
                    "platform": profile["platform"],
                    "creator_id": profile["account_id"],
                    "display_name": profile.get("display_name"),
                    "account_profile_id": profile_id,
                    "source": "account_profile",
                }
            )
        return await service.add_creators(
            pool_id=pool_id,
            creators=creators,
            crawl_now=request.crawl_now,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/automation/select")
async def select_candidates_for_automation(payload: dict):
    candidates = payload.get("candidates") or []
    rules = payload.get("rules") or {}
    return {"selected": automation_select_candidates(candidates, rules)}


class CreatorRealtimeDiscoveryRequest(BaseModel):
    keywords: list[str] = Field(min_length=1)
    platforms: list[str] = Field(default_factory=list)
    realtime: bool = False
    wait: bool = False


class CreatorRealtimeProbeRequest(BaseModel):
    raw_query: str = Field(default="K12 家长", min_length=1, max_length=100)
    platforms: list[str] = Field(default_factory=lambda: list(REALTIME_PLATFORMS))


class CreatorMetricsEnrichRequest(BaseModel):
    creators: list[dict] = Field(default_factory=list)
    raw_query: str | None = None
    platforms: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=200)
    recent_activity_min: int | None = Field(default=1, ge=0)


@router.post("/profile-metrics/enrich")
async def enrich_creator_profile_metrics(request: CreatorMetricsEnrichRequest):
    require_research_database()
    repository = ResearchRepository()
    creators = request.creators
    if not creators and request.raw_query:
        search = await search_creators(
            repository,
            {
                "raw_query": request.raw_query,
                "platforms": request.platforms,
                "recent_activity_min": request.recent_activity_min,
                "limit": request.limit,
            },
        )
        creators = search.get("results") or []
    return await enrich_creator_metrics_from_tikhub(repository, creators)


@router.post("/realtime/check")
async def check_creator_realtime_capability(request: CreatorRealtimeProbeRequest):
    requested_platforms = [str(platform) for platform in request.platforms or []]
    selected_platforms = [
        platform
        for platform in (requested_platforms or list(REALTIME_PLATFORMS))
        if platform in REALTIME_PLATFORMS
    ]
    provider_enabled = {
        "xhs": bool(getattr(config, "ENABLE_JUSTONE_API", False)),
        "dy": bool(getattr(config, "ENABLE_TIKHUB", False)),
    }
    provider_api_key_set = {
        "xhs": bool(resolve_justone_api_key()),
        "dy": bool(resolve_tikhub_api_key()),
    }
    enabled = any(provider_enabled.get(platform, False) for platform in selected_platforms)
    api_key_set = any(provider_api_key_set.get(platform, False) for platform in selected_platforms)
    payload = {
        "enabled": enabled,
        "api_key_set": api_key_set,
        "provider": "mixed",
        "providers": {
            "xhs": "justoneapi",
            "dy": "tikhub",
        },
        "base_url": getattr(config, "TIKHUB_BASE_URL", ""),
        "provider_enabled": provider_enabled,
        "provider_api_key_set": provider_api_key_set,
        "base_urls": {
            "xhs": getattr(config, "JUSTONE_BASE_URL", ""),
            "dy": getattr(config, "TIKHUB_BASE_URL", ""),
        },
        "supported_platforms": list(REALTIME_PLATFORMS),
    }
    return {
        **payload,
        "probe": await probe_realtime_platforms(
            raw_query=request.raw_query,
            platforms=request.platforms,
        ),
    }


@router.post("/discover/realtime")
async def start_creator_realtime_discovery(request: CreatorRealtimeDiscoveryRequest):
    require_research_database()
    if not request.realtime:
        return {
            "status": "skipped",
            "reason": "realtime discovery switch is off",
        }
    if not request.platforms:
        raise HTTPException(
            status_code=400,
            detail="Realtime discovery requires selected or global default platforms",
        )
    repository = ResearchRepository()
    job = await repository.create_job(
        {
            "name": f"creator realtime discovery - {' '.join(request.keywords)}",
            "topic": "creator_realtime_discovery",
            "platforms": request.platforms,
            "collection_mode": "search",
            "keywords": request.keywords,
            "target_ids": [],
            "creator_ids": [],
            "start_date": date.today(),
            "end_date": date.today(),
            "status": "pending",
            "comment_policy": {
                "enable_comments": False,
                "enable_sub_comments": False,
            },
            "raw_record_mode": "minimal",
            "anonymize_authors": True,
        }
    )
    execution = await schedule_and_execute_research_job(
        job["id"],
        background=not request.wait,
        force_schedule=True,
    )
    return {"status": execution["status"], "job_id": job["id"], "execution": execution}


@router.get("/discover/{job_id}/status")
async def get_creator_discovery_status(job_id: int):
    require_research_database()
    job = await ResearchRepository().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Discovery job not found")
    return {"job_id": job_id, "status": job["status"]}


@router.post("/discover/{job_id}/wait-refresh")
async def wait_creator_discovery_and_refresh(job_id: int):
    require_research_database()
    job = await wait_for_research_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Discovery job not found")
    extraction = await extract_creator_candidates_from_discovery_job(
        ResearchRepository(),
        job_id=job_id,
    )
    return {"job_id": job_id, "status": job["status"], "refreshed": True, "extraction": extraction}


@router.post("/discover/{job_id}/extract-candidates")
async def extract_creator_discovery_candidates(job_id: int, pool_name: str | None = None):
    require_research_database()
    try:
        return await extract_creator_candidates_from_discovery_job(
            ResearchRepository(),
            job_id=job_id,
            pool_name=pool_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/export")
async def export_creator_candidates(
    pool_name: str | None = None,
    platform: str | None = None,
    vertical_id: int | None = None,
):
    require_research_database()
    candidates = await ResearchRepository().list_creator_candidates(
        pool_name=pool_name,
        platform=platform,
        vertical_id=vertical_id,
    )
    return Response(
        content=export_creator_candidates_csv(candidates),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="creator-candidates.csv"'},
    )


@router.get("/{platform}/{creator_id}/profile")
async def get_creator_profile(platform: str, creator_id: str):
    require_research_database()
    profile = await ResearchRepository().get_creator_profile(platform, creator_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Creator profile not found")
    return profile


@router.get("/{platform}/{creator_id}/evidence")
async def get_creator_evidence(platform: str, creator_id: str, vertical_id: int | None = None):
    require_research_database()
    repository = ResearchRepository()
    profile = await repository.get_creator_profile(platform, creator_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Creator profile not found")
    tags = await repository.list_entity_tags(
        entity_type="creator",
        entity_id=creator_id,
        platform=platform,
        vertical_id=vertical_id,
    )
    return {"profile": profile, "tags": tags, "evidence": [tag["evidence_json"] for tag in tags]}
