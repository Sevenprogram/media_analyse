import asyncio
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import quote

import config
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError

from api.deps.auth import require_current_user
from saas.tenant_context import get_current_org_id
from api.schemas import SaveDataOptionEnum
from research.ai_analysis import AIAnalysisRunner
from research.ai_provider import OpenAICompatibleProvider
from research.automation_daemon import get_research_automation_status
from research.backfill import ExistingPlatformBackfill
from research.execution import (
    ResearchExecutionManager,
    ResearchExecutionOptions,
    build_crawler_start_requests,
    execution_plan_to_dict,
)
from research.exporter import ResearchExporter
from research.growth_ai import suggest_growth_project_keywords_with_provider
from research.charts import build_chart_summary
from research.content_strategy import (
    build_content_strategy_summary,
    normalize_strategy_filters,
)
from research.content_strategy_refresh import (
    collect_active_project_keywords,
    generate_project_content_strategy_ai_bundle,
    load_project_content_strategy_state,
    refresh_interval_minutes as content_strategy_refresh_interval_minutes,
    save_project_content_strategy_state,
)
from research.enums import (
    CRAWL_UNIT_CANCELLED,
    CRAWL_UNIT_FAILED,
    CRAWL_UNIT_PENDING,
    CRAWL_UNIT_RETRYING,
    CRAWL_UNIT_RUNNING,
    CRAWL_UNIT_SUCCEEDED,
    JOB_CANCELLED,
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_PAUSED_BY_PLATFORM_CONFIG,
    JOB_PENDING,
    JOB_QUEUED,
    JOB_RUNNING,
)
from research.database_guard import (
    ResearchDatabaseNotConfigured,
    assert_research_database_enabled,
    is_research_database_enabled,
)
from research.platforms import BACKFILL_RESEARCH_PLATFORMS, list_research_platform_options
from research.repository import ResearchRepository
from research.schedule_time import next_utc8_daily_run_at
from research.scheduler import ResearchScheduler
from research.schemas import (
    AttributionConfigUpdate,
    AttributionSpendImportRequest,
    AIAnalysisJobCreate,
    AIAnalysisResultCreate,
    AIProviderConfigCreate,
    AIPromptTemplateCreate,
    AuthProfileCreate,
    AuthProfileUpdate,
    CommentPolicy,
    ConversionEventImportRequest,
    ExistingDataBackfillRequest,
    GROWTH_COLLECTION_PLATFORMS,
    GlobalDefaultsUpsert,
    GrowthProjectCreate,
    GrowthProjectKeywordAISuggestRequest,
    GrowthProjectRunNowRequest,
    GrowthProjectUpdate,
    KeywordSetCreate,
    KeywordSetUpdate,
    LeadImportRequest,
    PlatformCapabilityUpsert,
    PlatformRateLimitUpsert,
    ResearchExecutionRequest,
    ResearchJobCreate,
    TouchpointImportRequest,
)
from research.schemas import ResearchJobUpdate
from research.service import ResearchJobService
from research.setup_status import build_research_setup_status
from research.validation import build_validation_checklist
from research.lead_attribution import (
    build_lead_attribution_explanation,
    build_lead_attribution_explanation_for_model,
    build_touchpoint_role_map,
    compute_attribution_rows,
    ensure_utc,
    normalize_attribution_config,
    SUPPORTED_MODELS,
    setting_key_for_project,
)
from research.ui_navigation import SIDE_NAV_CONFIG_KEY, normalize_side_nav_config
from api.services.crawler_manager import CrawlerManager, crawler_manager

router = APIRouter(
    prefix="/research",
    tags=["research"],
    dependencies=[Depends(require_current_user)],
)
logger = logging.getLogger(__name__)
_research_execution_task: asyncio.Task | None = None
_research_execution_job_id: int | None = None
_research_executions: dict[int, dict] = {}
_research_execution_queue: list[dict] = []
_research_queue_worker_task: asyncio.Task | None = None
_research_execution_concurrency: int = 1
AI_ANALYSIS_TASKS: dict[int, dict] = {}
EXPORT_BASE_DIR = Path("exports")
GLOBAL_DEFAULTS_KEY = "research_defaults"
DEFAULT_PROJECT_REFRESH_WINDOW_DAYS = 7
DEFAULT_PROJECT_DAILY_COLLECTION_LIMIT_PER_PLATFORM = 50
MAX_PROJECT_DAILY_COLLECTION_LIMIT_PER_PLATFORM = 500
DEFAULT_PROJECT_REFRESH_POSTS_PER_PLATFORM = DEFAULT_PROJECT_DAILY_COLLECTION_LIMIT_PER_PLATFORM
DEFAULT_AI_PROMPT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "stance": {"type": "string", "enum": ["support", "oppose", "mixed", "unknown"]},
        "topic_tags": {"type": "array", "items": {"type": "string"}},
        "pain_points": {"type": "array", "items": {"type": "string"}},
        "opportunities": {"type": "array", "items": {"type": "string"}},
        "risk_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary",
        "sentiment",
        "stance",
        "topic_tags",
        "pain_points",
        "opportunities",
        "risk_notes",
    ],
}

DEFAULT_AI_PROMPTS = [
    {
        "name": "default_post_understanding_v1",
        "task_type": "summary",
        "platform": "all",
        "version": "v1",
        "enabled": True,
        "output_schema": DEFAULT_AI_PROMPT_SCHEMA,
        "prompt_text": (
            "You are analyzing a social media post for growth research. "
            "Return only valid JSON matching this schema: summary, sentiment, stance, "
            "topic_tags, pain_points, opportunities, risk_notes. "
            "Use concise Chinese unless the source text is mostly another language.\n\n"
            "Platform: {platform}\n"
            "Target ID: {target_id}\n"
            "Title: {title}\n"
            "Content: {content}\n"
            "Publish time: {publish_time}\n"
            "Engagement JSON: {engagement_json}"
        ),
    },
    {
        "name": "default_comment_understanding_v1",
        "task_type": "comment_digest",
        "platform": "all",
        "version": "v1",
        "enabled": True,
        "output_schema": DEFAULT_AI_PROMPT_SCHEMA,
        "prompt_text": (
            "You are analyzing a user comment for growth research. "
            "Return only valid JSON matching this schema: summary, sentiment, stance, "
            "topic_tags, pain_points, opportunities, risk_notes. "
            "Focus on user demand, objection, urgency, and concrete evidence.\n\n"
            "Platform: {platform}\n"
            "Target ID: {target_id}\n"
            "Content: {content}\n"
            "Publish time: {publish_time}\n"
            "Engagement JSON: {engagement_json}"
        ),
    },
]


def default_global_settings() -> dict:
    return GlobalDefaultsUpsert().model_dump(mode="python")


def get_service() -> ResearchJobService:
    return ResearchJobService(ResearchRepository())


def require_research_database() -> None:
    try:
        assert_research_database_enabled()
    except ResearchDatabaseNotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _save_option_from_config() -> SaveDataOptionEnum:
    value = str(getattr(config, "SAVE_DATA_OPTION", "sqlite") or "sqlite").lower()
    return SaveDataOptionEnum(value) if value in {item.value for item in SaveDataOptionEnum} else SaveDataOptionEnum.SQLITE


def default_execution_options() -> ResearchExecutionOptions:
    return ResearchExecutionOptions(save_option=_save_option_from_config())


def _task_is_live(task: asyncio.Task | None) -> bool:
    return bool(task and hasattr(task, "done") and not task.done())


def _live_research_executions() -> dict[int, dict]:
    for job_id, record in list(_research_executions.items()):
        if not _task_is_live(record.get("task")):
            _research_executions.pop(job_id, None)
    return {
        job_id: record
        for job_id, record in _research_executions.items()
        if _task_is_live(record.get("task"))
    }


def _sync_legacy_execution_pointer() -> None:
    global _research_execution_job_id, _research_execution_task
    live = _live_research_executions()
    if live:
        job_id, record = next(iter(live.items()))
        _research_execution_job_id = job_id
        _research_execution_task = record.get("task")
        return
    if not _task_is_live(_research_execution_task):
        _research_execution_job_id = None
        _research_execution_task = None


def _running_research_job_ids() -> list[int]:
    live = _live_research_executions()
    ids = list(live.keys())
    if _task_is_live(_research_execution_task) and _research_execution_job_id is not None:
        if _research_execution_job_id not in ids:
            ids.append(_research_execution_job_id)
    return ids


def _research_execution_at_capacity() -> bool:
    return len(_running_research_job_ids()) >= _research_execution_concurrency


def get_research_execution_concurrency() -> dict:
    return {
        "max_concurrent": _research_execution_concurrency,
        "running": len(_running_research_job_ids()),
        "default": 1,
        "min": 1,
        "max": 16,
    }


def set_research_execution_concurrency(value: int) -> dict:
    global _research_execution_concurrency, _research_queue_worker_task
    _research_execution_concurrency = max(1, min(16, int(value or 1)))
    if _research_queue_worker_task is None or _research_queue_worker_task.done():
        if _research_execution_queue:
            _research_queue_worker_task = asyncio.create_task(_run_research_execution_queue())
    return get_research_execution_concurrency()


def _coerce_org_id(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _repository_for_org(org_id: int | None) -> ResearchRepository:
    return ResearchRepository(org_id=org_id) if org_id is not None else ResearchRepository()


async def _resolve_research_job_org_id(job_id: int, org_id: int | None = None) -> int | None:
    explicit_org_id = _coerce_org_id(org_id)
    if explicit_org_id is not None:
        return explicit_org_id
    current_org_id = _coerce_org_id(get_current_org_id())
    if current_org_id is not None:
        return current_org_id
    job = await ResearchRepository.global_scope().get_job(job_id)
    return _coerce_org_id((job or {}).get("org_id"))


def _execution_busy() -> bool:
    current = asyncio.current_task()
    return any(record.get("task") is not current for record in _live_research_executions().values())


async def schedule_and_execute_research_job(
    job_id: int,
    *,
    background: bool = True,
    force_schedule: bool = True,
    org_id: int | None = None,
) -> dict:
    global _research_execution_job_id, _research_execution_task
    require_research_database()
    if _research_execution_at_capacity():
        return {
            "status": "busy",
            "job_id": _running_research_job_ids()[0] if _running_research_job_ids() else None,
            "running_job_ids": _running_research_job_ids(),
            "message": "Research execution concurrency limit reached",
        }
    resolved_org_id = await _resolve_research_job_org_id(job_id, org_id)
    repository = _repository_for_org(resolved_org_id)
    scheduler = ResearchScheduler(repository)
    schedule = await scheduler.schedule_job(job_id, force=force_schedule)
    job = await repository.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    options = default_execution_options()
    salt = os.getenv("RESEARCH_AUTHOR_HASH_SALT")
    if options.backfill_after_crawl and not salt:
        await repository.create_event(
            job_id=job_id,
            platform=None,
            event_type="backfill_skipped_missing_salt",
            message="RESEARCH_AUTHOR_HASH_SALT is not configured; crawler execution will run without research backfill",
            stats=None,
        )
        options.backfill_after_crawl = False
    if background:
        local_crawler_manager = CrawlerManager()
        task = asyncio.create_task(
            _run_research_execution_background(
                job=job,
                options=options,
                salt=salt,
                crawler=local_crawler_manager,
                org_id=resolved_org_id,
            )
        )
        _research_executions[job_id] = {
            "task": task,
            "crawler_manager": local_crawler_manager,
            "org_id": resolved_org_id,
            "started_at": date.today().isoformat(),
        }
        _sync_legacy_execution_pointer()
        return {"status": "accepted", "job_id": job_id, "schedule": schedule}
    local_crawler_manager = CrawlerManager()
    task = asyncio.current_task()
    _research_executions[job_id] = {
        "task": task,
        "crawler_manager": local_crawler_manager,
        "org_id": resolved_org_id,
        "started_at": date.today().isoformat(),
    }
    _sync_legacy_execution_pointer()
    try:
        await _run_research_execution_background(
            job=job,
            options=options,
            salt=salt,
            crawler=local_crawler_manager,
            org_id=resolved_org_id,
        )
    finally:
        _research_executions.pop(job_id, None)
        _sync_legacy_execution_pointer()
    return {"status": "completed", "job_id": job_id, "schedule": schedule}


async def cancel_active_research_execution_job(job_id: int) -> dict:
    record = _live_research_executions().get(job_id)
    task = record.get("task") if record else None
    if record is None and _research_execution_job_id == job_id and _task_is_live(_research_execution_task):
        record = {"task": _research_execution_task, "crawler_manager": crawler_manager}
        task = _research_execution_task
    if not record or not _task_is_live(task):
        return {
            "status": "not_running",
            "job_id": job_id,
            "active_job_id": _running_research_job_ids()[0] if _running_research_job_ids() else None,
            "crawler_stopped": False,
        }
    if _task_is_live(task):
        task.cancel()
    manager = record.get("crawler_manager") or crawler_manager
    stopped_crawler = await manager.stop()
    return {
        "status": "stopping",
        "job_id": job_id,
        "crawler_stopped": stopped_crawler,
    }


async def enqueue_research_collection_job(
    job_id: int,
    *,
    project_id: str | None = None,
    org_id: int | None = None,
) -> dict:
    global _research_queue_worker_task
    require_research_database()
    resolved_org_id = await _resolve_research_job_org_id(job_id, org_id)
    if job_id in _running_research_job_ids():
        return {
            "status": "running",
            "job_id": job_id,
            "project_id": project_id,
            "org_id": resolved_org_id,
            "queue_position": 0,
            "queue": _collection_queue_snapshot(),
        }
    queued = {
        "job_id": job_id,
        "project_id": project_id,
        "org_id": resolved_org_id,
        "enqueued_at": date.today().isoformat(),
    }
    existing = next((item for item in _research_execution_queue if item["job_id"] == job_id), None)
    if existing is None:
        _research_execution_queue.append(queued)
        await _repository_for_org(resolved_org_id).update_job(job_id, {"status": JOB_QUEUED})
    elif existing.get("org_id") is None and resolved_org_id is not None:
        existing["org_id"] = resolved_org_id
    if _research_queue_worker_task is None or _research_queue_worker_task.done():
        _research_queue_worker_task = asyncio.create_task(_run_research_execution_queue())
    return {
        "status": "queued",
        "job_id": job_id,
        "project_id": project_id,
        "org_id": resolved_org_id,
        "queue_position": _queue_position(job_id),
        "queue": _collection_queue_snapshot(),
    }


async def _run_research_execution_queue() -> None:
    while _research_execution_queue:
        if _research_execution_at_capacity():
            await asyncio.sleep(1)
            continue
        queued = _research_execution_queue.pop(0)
        job_id = int(queued["job_id"])
        org_id = _coerce_org_id(queued.get("org_id")) or await _resolve_research_job_org_id(job_id)
        repository = _repository_for_org(org_id)
        try:
            job = await repository.get_job(job_id)
            if job and job.get("status") in {JOB_CANCELLED, JOB_FAILED, JOB_COMPLETED}:
                continue
            execution = await schedule_and_execute_research_job(job_id, background=True, org_id=org_id)
            if execution.get("status") == "busy":
                _research_execution_queue.insert(0, queued)
                await asyncio.sleep(1)
        except Exception as exc:
            await repository.update_job(job_id, {"status": JOB_FAILED})
            await repository.create_event(
                job_id=job_id,
                platform=None,
                event_type="queue_execution_failed",
                message=str(exc),
                stats={"project_id": queued.get("project_id"), "org_id": org_id},
            )


def _collection_queue_snapshot() -> dict:
    running_job_ids = _running_research_job_ids()
    return {
        "running_job_id": running_job_ids[0] if running_job_ids else None,
        "running_job_ids": running_job_ids,
        "max_concurrent": _research_execution_concurrency,
        "queued_jobs": [
            {
                "job_id": item["job_id"],
                "project_id": item.get("project_id"),
                "org_id": item.get("org_id"),
                "queue_position": index + 1,
                "enqueued_at": item.get("enqueued_at"),
            }
            for index, item in enumerate(_research_execution_queue)
        ],
        "queue_length": len(_research_execution_queue),
    }


def _queue_position(job_id: int) -> int:
    for index, item in enumerate(_research_execution_queue):
        if int(item["job_id"]) == int(job_id):
            return index + 1
    return 0


async def wait_for_research_job_status(
    job_id: int,
    *,
    timeout_seconds: float = 30.0,
    poll_seconds: float = 1.0,
) -> dict:
    repository = ResearchRepository()
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    terminal = {"completed", "failed", "cancelled", "paused_by_platform_config"}
    job = await repository.get_job(job_id)
    while job and job.get("status") not in terminal and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(poll_seconds)
        job = await repository.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job


@router.get("/health")
async def research_health():
    return {"status": "ok", "module": "research"}


@router.get("/setup/status")
async def get_research_setup_status():
    return build_research_setup_status()


@router.get("/workers")
async def list_research_workers(stale_after_seconds: int = 60):
    require_research_database()
    repository = ResearchRepository()
    return {
        "workers": await repository.list_worker_heartbeats(
            stale_after_seconds=stale_after_seconds
        )
    }


@router.get("/workers/status")
async def get_research_workers_status(stale_after_seconds: int = 60):
    require_research_database()
    repository = ResearchRepository()
    workers = await repository.list_worker_heartbeats(
        stale_after_seconds=stale_after_seconds
    )
    return {
        "online": sum(1 for worker in workers if worker["online"]),
        "offline": sum(1 for worker in workers if not worker["online"]),
        "workers": workers,
    }


@router.get("/automation/status")
async def get_research_automation_runtime_status():
    return get_research_automation_status()


@router.get("/platform-rate-limits")
async def list_platform_rate_limits():
    require_research_database()
    repository = ResearchRepository()
    return {"rate_limits": await repository.list_platform_rate_limits()}


@router.put("/platform-rate-limits/{platform}")
async def upsert_platform_rate_limit(platform: str, request: PlatformRateLimitUpsert):
    require_research_database()
    payload = request.model_dump(mode="python")
    payload["platform"] = platform
    try:
        validated = PlatformRateLimitUpsert(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    repository = ResearchRepository()
    return await repository.upsert_platform_rate_limit(validated.model_dump(mode="python"))


@router.get("/platform-capabilities")
async def list_platform_capabilities():
    require_research_database()
    repository = ResearchRepository()
    return {"capabilities": await repository.list_platform_capabilities()}


@router.put("/platform-capabilities/{platform}")
async def upsert_platform_capability(platform: str, request: PlatformCapabilityUpsert):
    require_research_database()
    payload = request.model_dump(mode="python")
    payload["platform"] = platform
    try:
        validated = PlatformCapabilityUpsert(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    repository = ResearchRepository()
    return await repository.upsert_platform_capability(validated.model_dump(mode="python"))


@router.get("/global-settings/defaults")
async def get_global_defaults():
    require_research_database()
    repository = ResearchRepository()
    setting = await repository.get_global_setting(GLOBAL_DEFAULTS_KEY)
    return {
        "key": GLOBAL_DEFAULTS_KEY,
        "value": setting["value"] if setting else default_global_settings(),
        "updated_at": setting["updated_at"] if setting else None,
    }


@router.put("/global-settings/defaults")
async def upsert_global_defaults(request: GlobalDefaultsUpsert):
    require_research_database()
    repository = ResearchRepository()
    return await repository.upsert_global_setting(
        GLOBAL_DEFAULTS_KEY,
        request.model_dump(mode="python"),
    )


@router.get("/ui/side-nav-config")
async def get_side_nav_config():
    require_research_database()
    repository = ResearchRepository()
    setting = await repository.get_global_setting(SIDE_NAV_CONFIG_KEY)
    return {
        "key": SIDE_NAV_CONFIG_KEY,
        "value": normalize_side_nav_config(setting["value"] if setting else None),
        "updated_at": setting["updated_at"] if setting else None,
    }


@router.get("/keyword-sets")
async def list_keyword_sets(enabled_only: bool = False):
    require_research_database()
    repository = ResearchRepository()
    return {"keyword_sets": await repository.list_keyword_sets(enabled_only=enabled_only)}


@router.post("/keyword-sets")
async def create_keyword_set(request: KeywordSetCreate):
    require_research_database()
    repository = ResearchRepository()
    return await repository.create_keyword_set(request.model_dump(mode="python"))


@router.patch("/keyword-sets/{keyword_set_id}")
async def update_keyword_set(keyword_set_id: int, request: KeywordSetUpdate):
    require_research_database()
    repository = ResearchRepository()
    keyword_set = await repository.update_keyword_set(
        keyword_set_id,
        request.model_dump(mode="python", exclude_unset=True),
    )
    if keyword_set is None:
        raise HTTPException(status_code=404, detail="Keyword set not found")
    return keyword_set


@router.post("/auth-profiles")
async def create_auth_profile(request: AuthProfileCreate):
    require_research_database()
    repository = ResearchRepository()
    return await repository.create_auth_profile(request.model_dump(mode="python"))


@router.get("/auth-profiles")
async def list_auth_profiles(platform: str | None = None):
    require_research_database()
    repository = ResearchRepository()
    return {"profiles": await repository.list_auth_profiles(platform=platform)}


@router.patch("/auth-profiles/{profile_id}")
async def update_auth_profile(profile_id: int, request: AuthProfileUpdate):
    require_research_database()
    repository = ResearchRepository()
    profile = await repository.update_auth_profile(
        profile_id,
        request.model_dump(mode="python", exclude_unset=True),
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Auth profile not found")
    return profile


@router.post("/auth-profiles/{profile_id}/test")
async def test_auth_profile(profile_id: int):
    require_research_database()
    repository = ResearchRepository()
    profile = await repository.mark_auth_profile_verified(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Auth profile not found")
    return {"ok": True, "profile": profile}


@router.post("/jobs")
async def create_research_job(request: ResearchJobCreate):
    require_research_database()
    service = get_service()
    return await service.create_job(request)


@router.get("/jobs")
async def list_research_jobs():
    require_research_database()
    service = get_service()
    return {"jobs": await service.list_jobs()}


@router.get("/collection-queue")
async def get_collection_queue():
    require_research_database()
    return _collection_queue_snapshot()


@router.get("/growth-projects")
async def list_growth_projects():
    require_research_database()
    service = get_service()
    return {"projects": await service.list_growth_projects()}


@router.post("/growth-projects")
async def create_growth_project(request: GrowthProjectCreate):
    require_research_database()
    service = get_service()
    project_id = _project_slug(request.name)
    repository = ResearchRepository()
    scene_pack = None
    scene_keywords: list[dict] = []
    if request.scene_pack_id is not None:
        scene_pack = await repository.get_scene_pack(request.scene_pack_id)
        if scene_pack is None:
            raise HTTPException(status_code=404, detail="Scene pack not found")
        scene_keywords = await repository.list_scene_pack_keywords(
            scene_pack_ids=[request.scene_pack_id],
            enabled_only=True,
        )
        request_platforms = request.platforms or scene_pack.get("default_platforms") or []
        request_keywords = _collection_keywords_from_scene_pack(scene_keywords)
    else:
        request_platforms = request.platforms
        request_keywords = request.keywords
    if not request_platforms:
        raise HTTPException(status_code=400, detail="Growth project requires at least one platform")
    if not request_keywords:
        raise HTTPException(status_code=400, detail="Growth project requires collection keywords")

    project_record = None
    try:
        project_record = await repository.create_growth_project(
            {
                "name": request.name,
                "primary_goal": request.primary_goal,
                "scene_pack_id": request.scene_pack_id,
                "platforms": request_platforms,
                "collection_status": "queued" if request.start_immediately else "not_started",
                "comment_collection_enabled": request.collection_depth != "lightweight",
                "refresh_cadence": request.refresh_cadence,
                "refresh_time_utc8": request.refresh_time_utc8 if request.refresh_cadence == "daily" else None,
                "daily_collection_limit_per_platform": request.daily_collection_limit_per_platform,
                "sample_status": "sample_insufficient",
                "recommended_action": "wait_for_collection"
                if request.start_immediately
                else "start_collection",
            }
        )
        if scene_keywords:
            for keyword in scene_keywords:
                keyword_type, status = _project_keyword_type_and_status(keyword.get("keyword_type"))
                await repository.create_growth_project_keyword(
                    {
                        "project_id": project_record["id"],
                        "scene_pack_id": request.scene_pack_id,
                        "keyword": keyword["keyword"],
                        "keyword_type": keyword_type,
                        "source": "scene_pack",
                        "status": status,
                    }
                )
        else:
            for keyword in request_keywords:
                await repository.create_growth_project_keyword(
                    {
                        "project_id": project_record["id"],
                        "keyword": keyword,
                        "keyword_type": "core",
                        "source": "manual",
                        "status": "active",
                    }
                )
        for platform in request_platforms:
            await repository.create_growth_project_collection_plan(
                {
                    "project_id": project_record["id"],
                    "platform": platform,
                    "collection_mode": "search",
                    "keyword_scope": "active",
                    "enabled": True,
                    "schedule_mode": "interval" if request.refresh_cadence != "off" else "manual",
                    "schedule_interval_minutes": _refresh_interval_minutes(request.refresh_cadence),
                }
            )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=409, detail="Growth project already exists") from exc

    enable_comments = request.collection_depth in {"standard", "deep"}
    keyword_rows = (
        await repository.list_growth_project_keywords(project_record["id"])
        if project_record is not None
        else [
            {"keyword": keyword, "keyword_type": "core", "status": "active"}
            for keyword in request_keywords
        ]
    )
    job = await _sync_growth_project_scheduled_job(
        repository,
        project_id=project_id,
        project_record=project_record
        or {
            "id": 0,
            "refresh_cadence": request.refresh_cadence,
            "custom_interval_value": None,
            "custom_interval_unit": None,
            "refresh_time_utc8": request.refresh_time_utc8 if request.refresh_cadence == "daily" else None,
            "daily_collection_limit_per_platform": request.daily_collection_limit_per_platform,
        },
        project_name=request.name,
        platforms=request_platforms,
        keyword_rows=keyword_rows,
        comment_collection_enabled=enable_comments,
        start_immediately=request.start_immediately,
    )
    if project_record is not None:
        await repository.update_growth_project(
            project_record["id"],
            {
                "collection_status": "queued" if request.start_immediately else "scheduled",
                "recommended_action": "wait_for_collection"
                if request.start_immediately
                else "review_strategy",
            },
        )
    if request.start_immediately:
        await enqueue_research_collection_job(int(job["id"]), project_id=project_id)
    return {
        "project_id": project_id,
        "project_record_id": project_record["id"] if project_record else None,
        "job": job,
        "scene_pack": scene_pack,
        "keyword_snapshot": scene_keywords,
    }


@router.get("/growth-projects/{project_id}")
async def get_growth_project(project_id: str):
    require_research_database()
    service = get_service()
    started_at = perf_counter()
    project = await service.get_growth_project(project_id)
    elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
    logger.info(
        "[perf] growth_project_detail project_id=%s elapsed_ms=%s found=%s",
        project_id,
        elapsed_ms,
        project is not None,
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    return project


@router.get("/growth-projects/{project_id}/posts")
async def list_growth_project_posts(project_id: str, limit: int = 20, offset: int = 0):
    require_research_database()
    service = get_service()
    project = await service.get_growth_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    job_ids = [
        int(job_id)
        for job_id in project.get("project", {}).get("job_ids", [])
        if isinstance(job_id, int) or str(job_id).isdigit()
    ]
    repository = ResearchRepository()
    page = await repository.list_posts_page(
        job_ids=job_ids,
        limit=max(1, min(limit, 100)),
        offset=max(0, offset),
    )
    return {**page, "has_more": page["offset"] + len(page["posts"]) < page["total"]}


@router.patch("/growth-projects/{project_id}")
async def update_growth_project(project_id: str, request: GrowthProjectUpdate):
    require_research_database()
    repository = ResearchRepository()
    record = await _ensure_growth_project_record_for_identifier(repository, project_id)
    payload = request.model_dump(mode="python", exclude_unset=True)
    keywords_payload = payload.pop("keywords", None)
    if not payload:
        if keywords_payload is not None:
            await _replace_growth_project_keywords(
                repository,
                project_record_id=record["id"],
                keywords=keywords_payload,
            )
            detail = await get_service().get_growth_project(project_id)
            return {
                "project_id": detail["project"]["id"] if detail else project_id,
                "project": detail["project"] if detail else record,
                "detail": detail,
            }
        return {"project_id": project_id, "project": record}
    old_project_key = project_id if not project_id.isdigit() else _project_slug(record["name"])
    scene_pack_id = payload.pop("scene_pack_id", None)
    keyword_mode = payload.pop("scene_pack_keyword_mode", None)
    if scene_pack_id is not None:
        scene_pack = await repository.get_scene_pack(scene_pack_id)
        if scene_pack is None:
            raise HTTPException(status_code=404, detail="Scene pack not found")
        payload["scene_pack_id"] = scene_pack_id
        if keyword_mode in {"replace", "append"}:
            await _apply_scene_pack_keywords_to_growth_project(
                repository,
                project_record_id=record["id"],
                scene_pack_id=scene_pack_id,
                mode=keyword_mode,
            )
    if payload.get("refresh_cadence") and payload.get("refresh_cadence") != "daily":
        payload["refresh_time_utc8"] = None
    project = await repository.update_growth_project(record["id"], payload)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    new_project_key = _project_slug(project["name"])
    if "name" in payload and old_project_key != new_project_key:
        await repository.retag_project_jobs(old_project_key, new_project_key)
    if keywords_payload is not None:
        await _replace_growth_project_keywords(
            repository,
            project_record_id=record["id"],
            keywords=keywords_payload,
        )
    if (
        "platforms" in payload
        or "refresh_cadence" in payload
        or "custom_interval_value" in payload
        or "custom_interval_unit" in payload
        or "refresh_time_utc8" in payload
    ):
        await _sync_growth_project_collection_plans(repository, project)
    keyword_rows = await repository.list_growth_project_keywords(record["id"])
    await _sync_growth_project_scheduled_job(
        repository,
        project_id=new_project_key,
        project_record=project,
        project_name=project["name"],
        platforms=project.get("platforms") or [],
        keyword_rows=keyword_rows,
        comment_collection_enabled=bool(project.get("comment_collection_enabled", True)),
    )
    detail = await get_service().get_growth_project(new_project_key)
    return {
        "project_id": detail["project"]["id"] if detail else new_project_key,
        "project": detail["project"] if detail else project,
        "detail": detail,
    }


@router.delete("/growth-projects/{project_id}")
async def delete_growth_project(project_id: str):
    require_research_database()
    repository = ResearchRepository()
    record = await _ensure_growth_project_record_for_identifier(repository, project_id)
    project = await repository.update_growth_project(record["id"], {"archived": True})
    return {
        "deleted": True,
        "archived": True,
        "project": project,
        "message": "Project archived; collected samples and research jobs are preserved.",
    }


@router.get("/growth-projects/{project_id}/keywords")
async def list_growth_project_keywords(project_id: int):
    require_research_database()
    repository = ResearchRepository()
    project = await repository.get_growth_project_record(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    return {"keywords": await repository.list_growth_project_keywords(project_id)}


@router.post("/growth-projects/{project_id}/keywords/ai-suggest")
async def suggest_growth_project_keywords(
    project_id: str,
    request: GrowthProjectKeywordAISuggestRequest,
):
    require_research_database()
    repository = ResearchRepository()
    detail = await get_service().get_growth_project(project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    provider_config = await _resolve_growth_project_ai_provider(repository)
    summary = detail.get("project") or {}
    suggestions_request = {
        "project_name": summary.get("name") or "Growth Project",
        "primary_goal": summary.get("primary_goal") or "mixed_research",
        "target_platforms": summary.get("platforms") or [],
        "input_text": request.input_text,
        "existing_keywords": [
            str(item.get("keyword") or "").strip()
            for item in detail.get("keywords", [])
            if str(item.get("keyword") or "").strip()
        ],
        "count": request.count,
    }
    try:
        suggestions = await suggest_growth_project_keywords_with_provider(
            provider_config,
            suggestions_request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("growth project keyword AI suggestion failed", exc_info=exc)
        raise HTTPException(status_code=502, detail="AI keyword suggestion failed") from exc
    return {
        "suggestions": suggestions,
        "provider": {
            "name": provider_config.get("name") or "AI Gateway",
            "model": provider_config.get("model"),
        },
        "context": {
            "project_id": summary.get("id") or project_id,
            "project_name": summary.get("name") or "Growth Project",
            "primary_goal": summary.get("primary_goal") or "mixed_research",
            "platforms": summary.get("platforms") or [],
            "requested_count": request.count,
            "existing_keyword_count": len(suggestions_request["existing_keywords"]),
        },
    }


@router.get("/growth-projects/{project_id}/collection-plans")
async def list_growth_project_collection_plans(project_id: int):
    require_research_database()
    repository = ResearchRepository()
    project = await repository.get_growth_project_record(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    return {"collection_plans": await repository.list_growth_project_collection_plans(project_id)}


@router.post("/growth-projects/{project_id}/collection/start")
async def start_growth_project_collection(
    project_id: str,
    request: GrowthProjectRunNowRequest | None = None,
):
    return await run_growth_project_collection_now(project_id, request)


@router.post("/growth-projects/{project_id}/collection/run-now")
async def run_growth_project_collection_now(
    project_id: str,
    request: GrowthProjectRunNowRequest | None = None,
):
    require_research_database()
    service = get_service()
    repository = ResearchRepository()
    project = await service.get_growth_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    summary = project["project"]
    request = request or GrowthProjectRunNowRequest()
    project_keywords = [item["keyword"] for item in project.get("keywords", []) if item.get("keyword")]
    if not project_keywords and request.keyword_scope != "extra_only":
        raise HTTPException(status_code=400, detail="Growth project has no keywords to collect")
    selected_keywords = [keyword for keyword in request.selected_keywords if keyword in set(project_keywords)]
    if request.keyword_scope in {"selected_project", "selected_project_plus_extra"} and not selected_keywords:
        raise HTTPException(status_code=400, detail="Selected keywords are not part of this growth project")
    if request.keyword_scope == "all_project":
        keywords = project_keywords
    elif request.keyword_scope == "selected_project":
        keywords = selected_keywords
    elif request.keyword_scope == "all_project_plus_extra":
        keywords = [*project_keywords, *request.extra_keywords]
    elif request.keyword_scope == "selected_project_plus_extra":
        keywords = [*selected_keywords, *request.extra_keywords]
    else:
        keywords = request.extra_keywords
    keywords = list(dict.fromkeys([keyword for keyword in keywords if keyword]))
    if not keywords:
        raise HTTPException(status_code=400, detail="Collection task requires at least one keyword")
    platforms = _growth_collection_platforms(
        project_platforms=summary["platforms"],
        requested_platforms=request.platforms,
    )
    if not platforms:
        raise HTTPException(
            status_code=400,
            detail="Collection task requires at least one Xiaohongshu or Douyin platform",
        )
    per_keyword_limit = (
        request.max_results_per_keyword_per_platform
        or request.target_posts_per_platform
    )
    target_posts_total = _collection_target_posts_total(
        keywords=keywords,
        platforms=platforms,
        per_keyword_limit=per_keyword_limit,
    )
    active_job_id = _active_project_collection_job_id(project_id=project_id, project=project)
    if active_job_id is not None:
        progress = await _job_progress_snapshot(active_job_id)
        queue = _collection_queue_snapshot()
        active_status = _project_collection_progress_status(
            running_job_id=active_job_id if active_job_id in _running_research_job_ids() else None,
            queued_jobs=[item for item in queue["queued_jobs"] if int(item["job_id"]) == int(active_job_id)],
            queue=queue,
            progress=progress,
        )
        return {
            "status": active_status,
            "project_id": project_id,
            "job_id": active_job_id,
            "job": progress.get("job"),
            "target_posts_per_platform": request.target_posts_per_platform,
            "target_posts_total": target_posts_total,
            "platforms": platforms,
            "keywords": keywords,
            "keyword_scope": request.keyword_scope,
            "collection_window_days": request.collection_window_days,
            "prefer_latest_posts": request.prefer_latest_posts,
            "sort_mode": request.sort_mode,
            "time_preset": request.time_preset,
            "time_start": request.time_start.isoformat() if request.time_start else None,
            "time_end": request.time_end.isoformat() if request.time_end else None,
            "max_results_per_keyword_per_platform": per_keyword_limit,
            "fill_strategy": request.fill_strategy,
            "max_extra_pages": request.max_extra_pages,
            "queue_position": _queue_position(active_job_id),
            "queue": queue,
            "message": "Growth project already has an active collection job",
        }
    record = await _growth_project_record_for_identifier(repository, project_id)
    comment_policy = _comment_policy_for_growth_project(project)
    if record is not None:
        comment_policy.growth_project_key = _growth_project_job_key(record["id"])
    comment_policy.max_posts_per_job = request.target_posts_per_platform
    comment_policy.prefer_latest_posts = request.prefer_latest_posts
    comment_policy.sort_mode = request.sort_mode
    comment_policy.time_preset = request.time_preset
    comment_policy.time_start = request.time_start
    comment_policy.time_end = request.time_end
    comment_policy.max_results_per_keyword_per_platform = per_keyword_limit
    comment_policy.fill_strategy = request.fill_strategy
    comment_policy.max_extra_pages = request.max_extra_pages
    end_date = date.today()
    if request.time_start and request.time_end:
        start_date = request.time_start.date()
        end_date = request.time_end.date()
        comment_policy.disable_time_window = False
    elif request.collection_window_days is None:
        start_date = date(1970, 1, 1)
        comment_policy.disable_time_window = True
    else:
        start_date = end_date - timedelta(days=request.collection_window_days - 1)
    job = await service.create_job(
        ResearchJobCreate(
            name=f"{summary['name']} collection {date.today().isoformat()}",
            topic=project_id,
            platforms=platforms,
            keywords=keywords,
            start_date=start_date,
            end_date=end_date,
            collection_mode="search",
            comment_policy=comment_policy,
        )
    )
    if record:
        if request.persist_to_project:
            merged_platforms = list(
                dict.fromkeys([*(summary.get("platforms") or []), *platforms])
            )
            await repository.update_growth_project(record["id"], {"platforms": merged_platforms})
            for keyword in request.extra_keywords:
                await repository.create_growth_project_keyword(
                    {
                        "project_id": record["id"],
                        "keyword": keyword,
                        "keyword_type": "expanded",
                        "source": "manual",
                        "status": "active",
                    }
                )
        await repository.update_growth_project(
            record["id"],
            {"collection_status": "queued", "recommended_action": "wait_for_collection"},
        )
        await repository.update_growth_project_collection_plans(record["id"], {"enabled": True})
    queue = await enqueue_research_collection_job(int(job["id"]), project_id=project_id)
    return {
        "status": "queued",
        "project_id": project_id,
        "job": job,
        "target_posts_per_platform": request.target_posts_per_platform,
        "target_posts_total": target_posts_total,
        "platforms": platforms,
        "keywords": keywords,
        "keyword_scope": request.keyword_scope,
        "collection_window_days": request.collection_window_days,
        "prefer_latest_posts": request.prefer_latest_posts,
        "sort_mode": request.sort_mode,
        "time_preset": request.time_preset,
        "time_start": request.time_start.isoformat() if request.time_start else None,
        "time_end": request.time_end.isoformat() if request.time_end else None,
        "max_results_per_keyword_per_platform": per_keyword_limit,
        "fill_strategy": request.fill_strategy,
        "max_extra_pages": request.max_extra_pages,
        **queue,
    }


@router.get("/growth-projects/{project_id}/collection/progress")
async def get_growth_project_collection_progress(project_id: str):
    require_research_database()
    service = get_service()
    repository = ResearchRepository()
    started_at = perf_counter()
    project_started_at = perf_counter()
    project = await service.get_growth_project(project_id)
    project_elapsed_ms = round((perf_counter() - project_started_at) * 1000, 1)
    if project is None:
        logger.info(
            "[perf] growth_project_progress project_id=%s detail_ms=%s total_ms=%s found=false",
            project_id,
            project_elapsed_ms,
            round((perf_counter() - started_at) * 1000, 1),
        )
        raise HTTPException(status_code=404, detail="Growth project not found")
    records = project.get("collection_records", [])
    job_ids = [int(record["id"]) for record in records if record.get("id") is not None]
    latest_record = max(
        (
            record
            for record in records
            if record.get("id") is not None
        ),
        key=lambda item: (
            str(item.get("updated_at") or ""),
            int(item.get("id") or 0),
        ),
        default=None,
    )
    latest_job_id = int(latest_record["id"]) if latest_record is not None else None
    queued_for_project = [
        item for item in _collection_queue_snapshot()["queued_jobs"]
        if item.get("project_id") == project_id
    ]
    running_job_ids = [job_id for job_id in _running_research_job_ids() if job_id in job_ids]
    running_job_id = running_job_ids[0] if running_job_ids else None
    current_job_id = running_job_id or (
        queued_for_project[0]["job_id"]
        if queued_for_project
        else (latest_job_id or (job_ids[0] if job_ids else None))
    )
    snapshot_started_at = perf_counter()
    progress = await _job_progress_snapshot(current_job_id) if current_job_id else _empty_progress()
    snapshot_elapsed_ms = round((perf_counter() - snapshot_started_at) * 1000, 1)
    total_elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
    logger.info(
        "[perf] growth_project_progress project_id=%s current_job_id=%s detail_ms=%s snapshot_ms=%s total_ms=%s queued_jobs=%s",
        project_id,
        current_job_id,
        project_elapsed_ms,
        snapshot_elapsed_ms,
        total_elapsed_ms,
        len(queued_for_project),
    )
    return {
        "project_id": project_id,
        "status": _project_collection_progress_status(
            running_job_id=running_job_id,
            queued_jobs=queued_for_project,
            queue=_collection_queue_snapshot(),
            progress=progress,
        ),
        "current_job_id": current_job_id,
        "running_job_id": running_job_id,
        "queued_jobs": queued_for_project,
        "queue": _collection_queue_snapshot(),
        "progress": progress,
        "automation": await _growth_project_automation_snapshot(repository, project_id=project_id),
    }


@router.get("/growth-projects/{project_id}/attribution-config")
async def get_growth_project_attribution_config(project_id: str):
    require_research_database()
    repository = ResearchRepository()
    record = await _ensure_growth_project_record_for_identifier(repository, project_id)
    setting = await repository.get_global_setting(setting_key_for_project(record["id"]))
    config = normalize_attribution_config(setting.get("value") if setting else None)
    return {"project_id": project_id, "project_record_id": record["id"], "config": config}


@router.put("/growth-projects/{project_id}/attribution-config")
async def update_growth_project_attribution_config(
    project_id: str,
    request: AttributionConfigUpdate,
):
    require_research_database()
    repository = ResearchRepository()
    record = await _ensure_growth_project_record_for_identifier(repository, project_id)
    config = normalize_attribution_config(request.model_dump(mode="python"))
    await repository.upsert_global_setting(setting_key_for_project(record["id"]), config)
    return {"project_id": project_id, "project_record_id": record["id"], "config": config}


@router.get("/growth-projects/{project_id}/leads")
async def list_growth_project_leads(
    project_id: str,
    status: str | None = None,
    platform: str | None = None,
    keyword: str | None = None,
    owner: str | None = None,
):
    require_research_database()
    repository = ResearchRepository()
    record = await _ensure_growth_project_record_for_identifier(repository, project_id)
    leads = await repository.list_project_leads(
        record["id"],
        status=status,
        platform=platform,
        keyword=keyword,
        owner=owner,
    )
    return {"project_id": project_id, "project_record_id": record["id"], "leads": leads}


@router.post("/growth-projects/{project_id}/leads/import")
async def import_growth_project_leads(project_id: str, request: LeadImportRequest):
    require_research_database()
    repository = ResearchRepository()
    record = await _ensure_growth_project_record_for_identifier(repository, project_id)
    config = await _load_project_attribution_config(repository, record["id"])
    created = 0
    updated = 0
    leads: list[dict] = []
    for item in request.items:
        payload = item.model_dump(mode="python")
        existing = await repository.find_lead_for_dedupe(
            project_id=record["id"],
            dedupe_by=config["dedupe_by"],
            external_lead_id=payload.get("external_lead_id"),
            phone_hash=payload.get("phone_hash"),
            wechat_hash=payload.get("wechat_hash"),
        )
        lead_payload = {
            **payload,
            "project_id": record["id"],
            "meta_json": {
                **(payload.get("meta_json") or {}),
                "source_system": request.source_system,
            },
        }
        if existing:
            lead = await repository.update_lead(int(existing["id"]), lead_payload)
            updated += 1
        else:
            lead = await repository.create_lead(lead_payload)
            created += 1
        leads.append(lead)
    return {
        "project_id": project_id,
        "project_record_id": record["id"],
        "created": created,
        "updated": updated,
        "leads": leads,
    }


@router.post("/growth-projects/{project_id}/touchpoints/import")
async def import_growth_project_touchpoints(project_id: str, request: TouchpointImportRequest):
    require_research_database()
    repository = ResearchRepository()
    record = await _ensure_growth_project_record_for_identifier(repository, project_id)
    created = 0
    skipped: list[dict] = []
    touchpoints: list[dict] = []
    for item in request.items:
        payload = item.model_dump(mode="python")
        external_lead_id = payload.pop("external_lead_id")
        lead = await repository.get_lead_by_external_id(record["id"], external_lead_id)
        if lead is None:
            skipped.append(
                {
                    "external_lead_id": external_lead_id,
                    "reason": "lead_not_found",
                }
            )
            continue
        touch_time = ensure_utc(payload["touch_time"])
        existing = await repository.find_lead_touchpoint_for_dedupe(
            lead_id=int(lead["id"]),
            touch_type=str(payload["touch_type"]),
            platform=payload.get("platform"),
            source_keyword=payload.get("source_keyword"),
            post_id=payload.get("post_id"),
            raw_record_id=payload.get("raw_record_id"),
            touch_time=touch_time,
        )
        if existing is not None:
            skipped.append(
                {
                    "external_lead_id": external_lead_id,
                    "reason": "duplicate_touchpoint",
                    "touchpoint_id": existing["id"],
                }
            )
            continue
        touchpoint = await repository.create_lead_touchpoint(
            {
                **payload,
                "lead_id": int(lead["id"]),
                "project_id": record["id"],
                "touch_time": touch_time,
            }
        )
        first_touch_at = ensure_utc(lead.get("first_touch_at"))
        last_touch_at = ensure_utc(lead.get("last_touch_at"))
        next_update: dict[str, object] = {}
        if first_touch_at is None or touch_time < first_touch_at:
            next_update["first_touch_at"] = touch_time
        if last_touch_at is None or touch_time > last_touch_at:
            next_update["last_touch_at"] = touch_time
        if next_update:
            await repository.update_lead(int(lead["id"]), next_update)
        created += 1
        touchpoints.append(touchpoint)
    return {
        "project_id": project_id,
        "project_record_id": record["id"],
        "created": created,
        "skipped": skipped,
        "touchpoints": touchpoints,
    }


@router.post("/growth-projects/{project_id}/conversion-events/import")
async def import_growth_project_conversion_events(
    project_id: str,
    request: ConversionEventImportRequest,
):
    require_research_database()
    repository = ResearchRepository()
    record = await _ensure_growth_project_record_for_identifier(repository, project_id)
    config = await _load_project_attribution_config(repository, record["id"])
    created = 0
    skipped: list[dict] = []
    events: list[dict] = []
    for item in request.items:
        payload = item.model_dump(mode="python")
        external_lead_id = payload.pop("external_lead_id")
        lead = await repository.get_lead_by_external_id(record["id"], external_lead_id)
        if lead is None:
            skipped.append(
                {
                    "external_lead_id": external_lead_id,
                    "reason": "lead_not_found",
                }
            )
            continue
        event_time = ensure_utc(payload["event_time"])
        source_system = request.source_system
        existing = await repository.find_lead_conversion_event_for_dedupe(
            lead_id=int(lead["id"]),
            event_type=str(payload["event_type"]),
            event_value=payload.get("event_value"),
            event_count=int(payload.get("event_count") or 1),
            event_time=event_time,
            source_system=source_system,
        )
        if existing is not None:
            skipped.append(
                {
                    "external_lead_id": external_lead_id,
                    "reason": "duplicate_conversion_event",
                    "event_id": existing["id"],
                }
            )
            continue
        event = await repository.create_lead_conversion_event(
            {
                **payload,
                "lead_id": int(lead["id"]),
                "project_id": record["id"],
                "source_system": source_system,
                "event_time": event_time,
            }
        )
        created += 1
        events.append(event)
        await _recompute_conversion_event_attribution(
            repository=repository,
            config=config,
            lead_id=int(lead["id"]),
            conversion_event=event,
            project_record_id=record["id"],
        )
    return {
        "project_id": project_id,
        "project_record_id": record["id"],
        "created": created,
        "skipped": skipped,
        "events": events,
    }


@router.post("/growth-projects/{project_id}/attribution-spend/import")
async def import_growth_project_attribution_spend(
    project_id: str,
    request: AttributionSpendImportRequest,
):
    require_research_database()
    repository = ResearchRepository()
    record = await _ensure_growth_project_record_for_identifier(repository, project_id)
    created = 0
    updated = 0
    spend_rows: list[dict] = []
    for item in request.items:
        payload = item.model_dump(mode="python")
        existing = await repository.find_lead_attribution_spend_for_dedupe(
            project_id=record["id"],
            spend_date=payload["spend_date"],
            dimension=str(payload["dimension"]),
            dimension_key=str(payload["dimension_key"]),
            source_system=request.source_system,
        )
        spend_payload = {
            **payload,
            "project_id": record["id"],
            "source_system": request.source_system,
        }
        if existing:
            spend = await repository.update_lead_attribution_spend(
                int(existing["id"]),
                spend_payload,
            )
            updated += 1
        else:
            spend = await repository.create_lead_attribution_spend(spend_payload)
            created += 1
        spend_rows.append(spend)
    return {
        "project_id": project_id,
        "project_record_id": record["id"],
        "created": created,
        "updated": updated,
        "spend": spend_rows,
    }


@router.get("/leads")
async def list_research_leads(
    scope: str = "global",
    status: str | None = None,
    platform: str | None = None,
    keyword: str | None = None,
    owner: str | None = None,
):
    require_research_database()
    if str(scope or "").strip().lower() != "global":
        raise HTTPException(status_code=400, detail="Only global lead listing is supported on this endpoint")
    repository = ResearchRepository()
    leads = await repository.list_all_leads(
        status=status,
        platform=platform,
        keyword=keyword,
        owner=owner,
    )
    return {"scope": "global", "leads": leads}


@router.get("/leads/{lead_id}")
async def get_lead_detail(lead_id: int, model: str | None = None):
    require_research_database()
    repository = ResearchRepository()
    lead = await repository.get_lead(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    touchpoints = await repository.list_lead_touchpoints(lead_id)
    conversion_events = await repository.list_lead_conversion_events(lead_id)
    config = await _load_project_attribution_config(repository, int(lead["project_id"]))
    selected_model = _resolve_attribution_model(model, config)
    attribution = await _build_lead_model_attribution_rows(
        repository=repository,
        lead=lead,
        touchpoints=touchpoints,
        conversion_events=conversion_events,
        config=config,
        model=selected_model,
    )
    attribution_explanation = build_lead_attribution_explanation_for_model(
        lead=lead,
        touchpoints=touchpoints,
        conversion_events=conversion_events,
        attribution_rows=attribution,
        config=config,
        model=selected_model,
    )
    return {
        "lead": lead,
        "touchpoints": touchpoints,
        "conversion_events": conversion_events,
        "attribution": attribution,
        "attribution_explanation": attribution_explanation,
    }


@router.get("/leads/{lead_id}/timeline")
async def get_lead_timeline(lead_id: int, model: str | None = None):
    require_research_database()
    repository = ResearchRepository()
    lead = await repository.get_lead(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    touchpoints = await repository.list_lead_touchpoints(lead_id)
    conversion_events = await repository.list_lead_conversion_events(lead_id)
    config = await _load_project_attribution_config(repository, int(lead["project_id"]))
    selected_model = _resolve_attribution_model(model, config)
    attribution = await _build_lead_model_attribution_rows(
        repository=repository,
        lead=lead,
        touchpoints=touchpoints,
        conversion_events=conversion_events,
        config=config,
        model=selected_model,
    )
    role_map = build_touchpoint_role_map(
        touchpoints=touchpoints,
        conversion_events=conversion_events,
        attribution_rows=attribution,
        window_days=int(config["window_days"]),
    )
    timeline = [
        {
            "kind": "touchpoint",
            "time": item["touch_time"],
            "payload": item,
            "model": selected_model,
            **(role_map.get(int(item["id"])) if item.get("id") is not None else {"role": "unattributed"}),
        }
        for item in touchpoints
    ] + [
        {
            "kind": "conversion_event",
            "time": item["event_time"],
            "payload": item,
            "model": selected_model,
        }
        for item in conversion_events
    ]
    timeline.sort(key=lambda row: row["time"])
    return {"lead_id": lead_id, "timeline": timeline}


def _active_project_collection_job_id(*, project_id: str, project: dict) -> int | None:
    job_ids = [
        int(record["id"])
        for record in project.get("collection_records", [])
        if record.get("id") is not None
    ]
    if not job_ids:
        return None
    running = [job_id for job_id in _running_research_job_ids() if job_id in job_ids]
    if running:
        return running[0]
    queued = [
        int(item["job_id"])
        for item in _collection_queue_snapshot()["queued_jobs"]
        if item.get("project_id") == project_id and int(item["job_id"]) in job_ids
    ]
    if queued:
        return queued[0]
    return None


async def _load_project_attribution_config(
    repository: ResearchRepository,
    project_record_id: int,
) -> dict:
    setting = await repository.get_global_setting(setting_key_for_project(project_record_id))
    return normalize_attribution_config(setting.get("value") if setting else None)


def _resolve_attribution_model(requested_model: str | None, config: dict) -> str:
    if requested_model in SUPPORTED_MODELS:
        return str(requested_model)
    return str(config["default_model"])


async def _build_lead_model_attribution_rows(
    *,
    repository: ResearchRepository,
    lead: dict,
    touchpoints: list[dict],
    conversion_events: list[dict],
    config: dict,
    model: str,
) -> list[dict]:
    if model == config["default_model"]:
        attribution = await repository.list_project_attribution_results(
            int(lead["project_id"]),
            model=model,
        )
        rows = [item for item in attribution if int(item["lead_id"]) == int(lead["id"])]
        if rows:
            return rows
    rows: list[dict] = []
    for conversion_event in conversion_events:
        computed_rows = compute_attribution_rows(
            model=model,
            conversion_event=conversion_event,
            touchpoints=touchpoints,
            window_days=int(config["window_days"]),
            enabled_dimensions=list(config["enabled_dimensions"]),
        )
        for row in computed_rows:
            rows.append(
                {
                    "project_id": int(lead["project_id"]),
                    "lead_id": int(lead["id"]),
                    "conversion_event_id": int(conversion_event["id"]),
                    "model": model,
                    "dimension": row["dimension"],
                    "dimension_key": row["dimension_key"],
                    "credit": row["credit"],
                    "window_days": int(config["window_days"]),
                    "meta_json": row.get("meta_json") or {},
                    "computed_at": ensure_utc(conversion_event.get("event_time")),
                }
            )
    return rows


async def _recompute_conversion_event_attribution(
    *,
    repository: ResearchRepository,
    config: dict,
    lead_id: int,
    conversion_event: dict,
    project_record_id: int,
) -> list[dict]:
    touchpoints = await repository.list_lead_touchpoints(lead_id)
    rows = compute_attribution_rows(
        model=config["default_model"],
        conversion_event=conversion_event,
        touchpoints=touchpoints,
        window_days=int(config["window_days"]),
        enabled_dimensions=list(config["enabled_dimensions"]),
    )
    payloads = [
        {
            "project_id": project_record_id,
            "lead_id": lead_id,
            "conversion_event_id": int(conversion_event["id"]),
            "model": config["default_model"],
            "dimension": row["dimension"],
            "dimension_key": row["dimension_key"],
            "credit": row["credit"],
            "window_days": int(config["window_days"]),
            "meta_json": {
                **(row.get("meta_json") or {}),
                "event_type": conversion_event.get("event_type"),
                "event_value": conversion_event.get("event_value"),
                "event_count": conversion_event.get("event_count"),
            },
        }
        for row in rows
    ]
    return await repository.replace_lead_attribution_results(
        conversion_event_id=int(conversion_event["id"]),
        rows=payloads,
    )


@router.post("/growth-projects/{project_id}/collection/pause")
async def pause_growth_project_collection(project_id: str):
    require_research_database()
    service = get_service()
    repository = ResearchRepository()
    project = await service.get_growth_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    record = await _growth_project_record_for_identifier(repository, project_id)
    if record:
        await repository.update_growth_project(
            record["id"],
            {"collection_status": "paused", "recommended_action": "start_collection"},
        )
        await repository.update_growth_project_collection_plans(record["id"], {"enabled": False})
        await _pause_growth_project_scheduled_jobs(repository, project_id=project_id)
    return {"status": "paused", "project_id": project_id}


@router.post("/growth-projects/{project_id}/collection/stop-current-run")
async def stop_growth_project_current_run(project_id: str):
    require_research_database()
    service = get_service()
    repository = ResearchRepository()
    project = await service.get_growth_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    project_job_ids = {
        int(record["id"])
        for record in project.get("collection_records", [])
        if record.get("id") is not None
    }
    _research_execution_queue[:] = [
        item
        for item in _research_execution_queue
        if not (item.get("project_id") == project_id or int(item["job_id"]) in project_job_ids)
    ]
    stopped = []
    stopped_crawler = False
    for record in project.get("collection_records", []):
        if record.get("status") in {"pending", "queued", "running"}:
            updated = await repository.update_job(int(record["id"]), {"status": "cancelled"})
            if updated:
                stopped.append(updated)
            active = await cancel_active_research_execution_job(int(record["id"]))
            if active["status"] == "stopping":
                stopped_crawler = bool(active.get("crawler_stopped"))
    project_record = await _growth_project_record_for_identifier(repository, project_id)
    if project_record:
        await repository.update_growth_project(
            project_record["id"],
            {"collection_status": "stopped", "recommended_action": "start_collection"},
        )
    return {
        "status": "stopped",
        "project_id": project_id,
        "jobs": stopped,
        "crawler_stopped": stopped_crawler,
    }


@router.post("/growth-projects/{project_id}/archive")
async def archive_growth_project(project_id: str):
    require_research_database()
    repository = ResearchRepository()
    record = await _ensure_growth_project_record_for_identifier(repository, project_id)
    project = await repository.update_growth_project(record["id"], {"archived": True})
    return {"status": "archived", "project": project}


@router.get("/jobs/{job_id}")
async def get_research_job(job_id: int):
    require_research_database()
    service = get_service()
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job


@router.get("/jobs/{job_id}/events")
async def list_research_job_events(job_id: int, limit: int = 200):
    require_research_database()
    repository = ResearchRepository()
    return {"events": await repository.list_events(job_id=job_id, limit=limit)}


@router.post("/jobs/{job_id}/schedule")
async def schedule_research_job(job_id: int):
    require_research_database()
    scheduler = ResearchScheduler(ResearchRepository())
    try:
        return await scheduler.schedule_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/crawl-units")
async def list_research_job_crawl_units(job_id: int, status: str | None = None):
    require_research_database()
    repository = ResearchRepository()
    return {"units": await repository.list_crawl_units(job_id=job_id, status=status)}


@router.get("/jobs/{job_id}/stats")
async def get_research_job_stats(job_id: int):
    require_research_database()
    repository = ResearchRepository()
    return await repository.get_job_stats(job_id)


@router.get("/database/stats")
async def get_research_database_stats():
    require_research_database()
    repository = ResearchRepository()
    return await repository.get_database_collection_stats()


@router.get("/jobs/{job_id}/posts")
async def list_research_job_posts(job_id: int, limit: int = 200, offset: int = 0):
    require_research_database()
    repository = ResearchRepository()
    page = await repository.list_posts_page(
        job_id=job_id,
        limit=max(1, min(limit, 500)),
        offset=max(0, offset),
    )
    return {**page, "has_more": page["offset"] + len(page["posts"]) < page["total"]}


@router.get("/jobs/{job_id}/comments")
async def list_research_job_comments(job_id: int, limit: int = 200):
    require_research_database()
    repository = ResearchRepository()
    return {"comments": await repository.list_comments(job_id, limit=limit)}


@router.get("/jobs/{job_id}/raw-records")
async def list_research_job_raw_records(job_id: int, limit: int = 100):
    require_research_database()
    repository = ResearchRepository()
    return {"raw_records": await repository.list_raw_records(job_id, limit=limit)}


@router.patch("/jobs/{job_id}")
async def update_research_job(job_id: int, request: ResearchJobUpdate):
    require_research_database()
    service = get_service()
    try:
        job = await service.update_job(job_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job


@router.get("/config/options")
async def get_research_config_options():
    platforms = list_research_platform_options()
    if is_research_database_enabled():
        try:
            capabilities = await ResearchRepository().list_platform_capabilities()
            enabled = {item["platform"] for item in capabilities if item["enabled"]}
            if enabled:
                platforms = [item for item in platforms if item["value"] in enabled]
        except SQLAlchemyError:
            capabilities = []
    return {
        "platforms": platforms,
        "collection_modes": [
            {"value": "search", "label": "Keyword search"},
            {"value": "detail", "label": "Specified content"},
            {"value": "creator", "label": "Creator timeline"},
        ],
        "raw_record_modes": [
            {"value": "minimal", "label": "Minimal"},
            {"value": "full", "label": "Full"},
        ],
        "comment_presets": [
            {
                "value": "limited",
                "label": "Limited comments",
                "policy": {
                    "enable_comments": True,
                    "comment_limit_per_post": 100,
                    "enable_sub_comments": False,
                    "sub_comment_limit_per_comment": 0,
                    "full_comment_crawl": False,
                },
            },
            {
                "value": "full",
                "label": "Full comments with guardrails",
                "requires": [
                    "rate_limit_per_minute",
                    "max_posts_per_job or stop_after_hours",
                    "ethical_note",
                ],
            },
        ],
    }


@router.get("/validation/checklist")
async def get_real_collection_validation_checklist(
    platform: list[str] | None = Query(default=None),
):
    try:
        return build_validation_checklist(platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _execution_options_from_request(request: ResearchExecutionRequest) -> ResearchExecutionOptions:
    return ResearchExecutionOptions(
        login_type=request.login_type,
        save_option=request.save_option,
        cookies=request.cookies,
        headless=request.headless,
        start_page=request.start_page,
        backfill_after_crawl=request.backfill_after_crawl,
    )


def _project_slug(value: str) -> str:
    return "_".join(part for part in value.lower().replace("-", " ").split() if part)


def _growth_project_job_key(project_record_id: int) -> str:
    return f"growth_project_record_{project_record_id}"


def _empty_progress() -> dict:
    return {
        "percent": 0,
        "sample_percent": 0,
        "step_percent": 0,
        "unit_counts": {
            CRAWL_UNIT_PENDING: 0,
            CRAWL_UNIT_RUNNING: 0,
            CRAWL_UNIT_RETRYING: 0,
            CRAWL_UNIT_SUCCEEDED: 0,
            CRAWL_UNIT_FAILED: 0,
            CRAWL_UNIT_CANCELLED: 0,
            "total": 0,
        },
        "sample_counts": {"posts": 0, "comments": 0, "raw_records": 0, "creators": 0},
        "target_counts": {"posts": 0},
        "progress_basis": "samples",
        "job": None,
        "latest_event": None,
        "events": [],
        "crawler": None,
    }


async def _job_progress_snapshot(job_id: int | None) -> dict:
    if job_id is None:
        return _empty_progress()
    repository = ResearchRepository()
    overall_started_at = perf_counter()
    get_job_started_at = perf_counter()
    job = await repository.get_job(int(job_id))
    get_job_elapsed_ms = round((perf_counter() - get_job_started_at) * 1000, 1)
    if job is None:
        logger.info(
            "[perf] job_progress_snapshot job_id=%s get_job_ms=%s total_ms=%s found=false",
            job_id,
            get_job_elapsed_ms,
            round((perf_counter() - overall_started_at) * 1000, 1),
        )
        return _empty_progress()
    units_started_at = perf_counter()
    units = await repository.list_crawl_units(int(job_id))
    units_elapsed_ms = round((perf_counter() - units_started_at) * 1000, 1)
    stats_started_at = perf_counter()
    stats = await repository.get_job_stats(int(job_id))
    stats_elapsed_ms = round((perf_counter() - stats_started_at) * 1000, 1)
    events_started_at = perf_counter()
    events = await repository.list_events(int(job_id), limit=20)
    events = _enrich_progress_events(events)
    events_elapsed_ms = round((perf_counter() - events_started_at) * 1000, 1)
    comment_policy = job.get("comment_policy") or {}
    target_posts_per_platform = int(comment_policy.get("max_posts_per_job") or 0)
    per_keyword_limit = int(
        comment_policy.get("max_results_per_keyword_per_platform")
        or target_posts_per_platform
        or 0
    )
    daily_limit = int(comment_policy.get("daily_collection_limit_per_platform") or 0)
    if daily_limit > 0:
        platform_count = len([item for item in job.get("platforms") or [] if str(item).strip()])
        target_posts_total = daily_limit * max(1, platform_count)
    else:
        target_posts_total = _collection_target_posts_total(
            keywords=job.get("keywords") or [],
            platforms=job.get("platforms") or [],
            per_keyword_limit=per_keyword_limit,
        )
    posts_count = int(stats.get("posts") or 0)
    unit_counts = _unit_counts_with_event_outcomes(units, events)
    if units:
        finished = (
            unit_counts[CRAWL_UNIT_SUCCEEDED]
            + unit_counts[CRAWL_UNIT_FAILED]
            + unit_counts[CRAWL_UNIT_CANCELLED]
        )
        percent = round((finished / max(unit_counts["total"], 1)) * 100)
    else:
        percent = _fallback_job_percent(str(job.get("status") or JOB_PENDING))
    sample_percent = _sample_progress_percent(
        posts_count=posts_count,
        target_posts_total=target_posts_total,
        job_status=str(job.get("status") or JOB_PENDING),
    )
    total_elapsed_ms = round((perf_counter() - overall_started_at) * 1000, 1)
    logger.info(
        "[perf] job_progress_snapshot job_id=%s get_job_ms=%s units_ms=%s stats_ms=%s events_ms=%s total_ms=%s units=%s events=%s",
        job_id,
        get_job_elapsed_ms,
        units_elapsed_ms,
        stats_elapsed_ms,
        events_elapsed_ms,
        total_elapsed_ms,
        len(units),
        len(events),
    )
    return {
        "percent": sample_percent,
        "sample_percent": sample_percent,
        "step_percent": percent,
        "unit_counts": unit_counts,
        "sample_counts": {
            "posts": posts_count,
            "comments": int(stats.get("comments") or 0),
            "raw_records": int(stats.get("raw_records") or 0),
            "creators": int(stats.get("authors") or stats.get("creators") or 0),
        },
        "target_counts": {"posts": target_posts_total},
        "progress_basis": "samples" if target_posts_total else "steps",
        "job": job,
        "latest_event": events[0] if events else None,
        "events": events,
        "crawler": _active_crawler_snapshot(int(job_id)),
    }


def _unit_counts_with_event_outcomes(units: list[dict], events: list[dict]) -> dict:
    counts = {
        CRAWL_UNIT_PENDING: 0,
        CRAWL_UNIT_RUNNING: 0,
        CRAWL_UNIT_RETRYING: 0,
        CRAWL_UNIT_SUCCEEDED: 0,
        CRAWL_UNIT_FAILED: 0,
        CRAWL_UNIT_CANCELLED: 0,
        "total": len(units),
    }
    outcomes = _platform_outcomes_from_events(events)
    terminal_statuses = {CRAWL_UNIT_SUCCEEDED, CRAWL_UNIT_FAILED, CRAWL_UNIT_CANCELLED}
    for unit in units:
        status = str(unit.get("status") or CRAWL_UNIT_PENDING)
        platform = str(unit.get("platform") or "")
        if status not in terminal_statuses:
            if platform in outcomes["failed"]:
                status = CRAWL_UNIT_FAILED
            elif platform in outcomes["succeeded"]:
                status = CRAWL_UNIT_SUCCEEDED
            elif platform in outcomes["cancelled"]:
                status = CRAWL_UNIT_CANCELLED
        counts[status] = int(counts.get(status, 0)) + 1
    return counts


def _enrich_progress_events(events: list[dict]) -> list[dict]:
    enriched_events = []
    for event in events:
        if event.get("event_type") != "execution_completed_with_platform_failures":
            enriched_events.append(event)
            continue
        stats = _event_stats(event)
        if stats.get("error"):
            enriched_events.append(event)
            continue
        error = _failed_platforms_summary(stats.get("failed_platforms") or [])
        if not error:
            enriched_events.append(event)
            continue
        enriched_event = {**event, "stats_json": {**stats, "error": error}}
        enriched_events.append(enriched_event)
    return enriched_events


def _failed_platforms_summary(failed_platforms: list) -> str:
    parts = []
    for item in failed_platforms:
        if isinstance(item, dict):
            platform = item.get("platform") or "unknown"
            message = item.get("message") or item.get("error_type") or "failed"
        else:
            platform = str(item)
            message = "failed"
        parts.append(f"{platform}: {message}")
    return "; ".join(parts)


def _platform_outcomes_from_events(events: list[dict]) -> dict[str, set[str]]:
    outcomes = {"succeeded": set(), "failed": set(), "cancelled": set()}
    ordered_events = sorted(
        events,
        key=lambda event: (
            str(event.get("created_at") or ""),
            int(event.get("id") or 0),
        ),
        reverse=True,
    )
    decided: set[str] = set()
    for event in ordered_events:
        stats = _event_stats(event)
        if event.get("event_type") == "execution_completed_with_platform_failures":
            for platform in stats.get("succeeded_platforms") or []:
                platform_key = str(platform)
                if platform_key not in decided:
                    outcomes["succeeded"].add(platform_key)
                    decided.add(platform_key)
            for item in stats.get("failed_platforms") or []:
                platform_key = str(item.get("platform") if isinstance(item, dict) else item)
                if platform_key and platform_key not in decided:
                    outcomes["failed"].add(platform_key)
                    decided.add(platform_key)
            continue
        platform = str(event.get("platform") or "")
        if not platform or platform in decided:
            continue
        event_type = str(event.get("event_type") or "")
        if event_type == "platform_execution_failed":
            outcomes["failed"].add(platform)
            decided.add(platform)
        elif event_type in {"crawler_finished", "backfill_completed", "post_crawl_analysis_completed"}:
            outcomes["succeeded"].add(platform)
            decided.add(platform)
        elif event_type in {"execution_cancelled", "crawl_unit_cancelled"}:
            outcomes["cancelled"].add(platform)
            decided.add(platform)
    return outcomes


def _event_stats(event: dict) -> dict:
    stats = event.get("stats_json") or {}
    return stats if isinstance(stats, dict) else {}


def _active_crawler_snapshot(job_id: int | None) -> dict | None:
    if job_id is None:
        return None
    record = _live_research_executions().get(int(job_id))
    if record is None:
        return None
    manager = record.get("crawler_manager")
    if manager is None:
        return None
    status = manager.get_status() if hasattr(manager, "get_status") else {}
    logs = getattr(manager, "logs", None) or []
    latest_log = _serialize_crawler_log(logs[-1]) if logs else None
    return {
        **status,
        "latest_log": latest_log,
        "log_count": len(logs),
    }


def _serialize_crawler_log(log: object) -> dict:
    if hasattr(log, "model_dump"):
        return log.model_dump(mode="json")
    if isinstance(log, dict):
        return log
    return {"message": str(log)}


def _sample_progress_percent(
    *,
    posts_count: int,
    target_posts_total: int,
    job_status: str,
) -> int:
    if target_posts_total > 0:
        if job_status in {JOB_FAILED, JOB_CANCELLED}:
            return min(100, round((posts_count / target_posts_total) * 100))
        return min(100, round((posts_count / target_posts_total) * 100))
    return _fallback_job_percent(job_status)


def _collection_target_posts_total(
    *,
    keywords: list,
    platforms: list,
    per_keyword_limit: int,
) -> int:
    keyword_count = len([item for item in keywords if str(item).strip()])
    platform_count = len([item for item in platforms if str(item).strip()])
    if per_keyword_limit <= 0:
        return 0
    return per_keyword_limit * max(1, keyword_count) * max(1, platform_count)


def _growth_collection_platforms(
    *,
    project_platforms: list,
    requested_platforms: list,
) -> list[str]:
    candidates = requested_platforms or project_platforms
    result: list[str] = []
    for value in candidates:
        platform = str(value or "").strip()
        if platform in GROWTH_COLLECTION_PLATFORMS and platform not in result:
            result.append(platform)
    return result


def _scheduled_refresh_job(job: dict[str, Any]) -> bool:
    if job.get("schedule_enabled"):
        return True
    return "scheduled refresh" in str(job.get("name") or "").lower()


def _job_sort_key(job: dict[str, Any]) -> tuple[str, int]:
    return (
        str(job.get("updated_at") or job.get("next_run_at") or job.get("created_at") or ""),
        int(job.get("id") or 0),
    )


async def _growth_project_automation_snapshot(
    repository: ResearchRepository,
    *,
    project_id: str,
) -> dict[str, Any]:
    jobs = await repository.list_jobs_for_project([project_id])
    scheduled_job = max(
        (job for job in jobs if _scheduled_refresh_job(job)),
        key=_job_sort_key,
        default=None,
    )
    return {
        "enabled": bool(scheduled_job and scheduled_job.get("schedule_enabled")),
        "job_id": int(scheduled_job["id"]) if scheduled_job and scheduled_job.get("id") is not None else None,
        "interval_minutes": (
            int(scheduled_job.get("schedule_interval_minutes") or 0) or None
        )
        if scheduled_job
        else None,
        "next_run_at": scheduled_job.get("next_run_at") if scheduled_job else None,
        "last_scheduled_at": scheduled_job.get("last_scheduled_at") if scheduled_job else None,
        "daemon": get_research_automation_status(),
    }


def _fallback_job_percent(status: str) -> int:
    if status == JOB_COMPLETED:
        return 100
    if status in {JOB_FAILED, JOB_CANCELLED}:
        return 100
    if status == JOB_RUNNING:
        return 30
    if status == JOB_QUEUED:
        return 5
    return 0


def _project_collection_progress_status(
    *,
    running_job_id: int | None,
    queued_jobs: list[dict],
    queue: dict | None = None,
    progress: dict,
) -> str:
    if running_job_id is not None:
        return "running"
    if queued_jobs:
        return "queued"
    job = progress.get("job") or {}
    status = str(job.get("status") or "")
    if _is_orphaned_active_progress(status=status, queue=queue, progress=progress):
        return JOB_FAILED
    if _is_completed_without_samples(status=status, progress=progress):
        return "empty"
    if status in {JOB_COMPLETED, JOB_FAILED, JOB_CANCELLED}:
        return status
    return status or "idle"


def _is_orphaned_active_progress(
    *,
    status: str,
    queue: dict | None,
    progress: dict,
) -> bool:
    if status not in {JOB_RUNNING, JOB_QUEUED}:
        return False
    if _execution_busy():
        return False
    if queue and (queue.get("running_job_id") or queue.get("queue_length")):
        return False
    unit_counts = progress.get("unit_counts") or {}
    latest_event = progress.get("latest_event")
    return not unit_counts.get("total") and latest_event is None


def _is_completed_without_samples(*, status: str, progress: dict) -> bool:
    if status != JOB_COMPLETED:
        return False
    target_posts = int((progress.get("target_counts") or {}).get("posts") or 0)
    posts = int((progress.get("sample_counts") or {}).get("posts") or 0)
    return target_posts > 0 and posts == 0


async def _resolve_growth_project_ai_provider(
    repository: ResearchRepository,
) -> dict:
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
    selected = enabled[0] if enabled else None
    if selected is None:
        raise HTTPException(
            status_code=400,
            detail="AI_GATEWAY_API_KEY is not configured and no enabled AI provider exists",
        )
    provider = await repository.get_ai_provider(selected["id"], include_secret=True)
    if provider is None:
        raise HTTPException(status_code=404, detail="AI provider config not found")
    return provider


def _refresh_interval_minutes(refresh_cadence: str) -> int | None:
    return {
        "daily": 1440,
        "three_days": 4320,
        "weekly": 10080,
    }.get(refresh_cadence)


def _refresh_interval_from_project(project: dict) -> int | None:
    cadence = str(project.get("refresh_cadence") or "off")
    if cadence == "custom_hours":
        return int(project.get("custom_interval_value") or 1) * 60
    if cadence == "custom_days":
        return int(project.get("custom_interval_value") or 1) * 1440
    return _refresh_interval_minutes(cadence)


def _scheduled_project_job_dates() -> tuple[date, date]:
    end_date = date.today()
    start_date = end_date - timedelta(days=DEFAULT_PROJECT_REFRESH_WINDOW_DAYS - 1)
    return start_date, end_date


def _daily_collection_limit_for_growth_project(project_detail: dict) -> int:
    settings = project_detail.get("settings") or project_detail
    raw_limit = settings.get("daily_collection_limit_per_platform")
    try:
        limit = int(raw_limit or DEFAULT_PROJECT_DAILY_COLLECTION_LIMIT_PER_PLATFORM)
    except (TypeError, ValueError):
        limit = DEFAULT_PROJECT_DAILY_COLLECTION_LIMIT_PER_PLATFORM
    return max(1, min(limit, MAX_PROJECT_DAILY_COLLECTION_LIMIT_PER_PLATFORM))


def _comment_policy_for_growth_project(project_detail: dict) -> CommentPolicy:
    settings = project_detail.get("settings") or {}
    enabled = bool(settings.get("comment_collection_enabled", True))
    return CommentPolicy(
        enable_comments=enabled,
        comment_limit_per_post=100 if enabled else None,
        enable_sub_comments=False,
        sub_comment_limit_per_comment=0,
        full_comment_crawl=False,
    )


def _scheduled_comment_policy_for_growth_project(project_detail: dict) -> CommentPolicy:
    policy = _comment_policy_for_growth_project(project_detail)
    daily_limit = _daily_collection_limit_for_growth_project(project_detail)
    policy.max_posts_per_job = daily_limit
    policy.prefer_latest_posts = True
    policy.sort_mode = "latest"
    policy.time_preset = "7d"
    policy.max_results_per_keyword_per_platform = daily_limit
    policy.daily_collection_limit_per_platform = daily_limit
    policy.fill_strategy = "prefer_fill"
    policy.max_extra_pages = 3
    return policy


async def _sync_growth_project_scheduled_job(
    repository: ResearchRepository,
    *,
    project_id: str,
    project_record: dict[str, Any],
    project_name: str,
    platforms: list[str],
    keyword_rows: list[dict[str, Any]],
    comment_collection_enabled: bool,
    start_immediately: bool = False,
) -> dict[str, Any]:
    active_keywords = collect_active_project_keywords(keyword_rows)
    interval_minutes = content_strategy_refresh_interval_minutes(project_record)
    fixed_refresh_time = (
        project_record.get("refresh_time_utc8")
        if str(project_record.get("refresh_cadence") or "") == "daily"
        else None
    )
    jobs = await repository.list_jobs_for_project([project_id])
    scheduled_job = next(
        (
            item
            for item in jobs
            if "scheduled refresh" in str(item.get("name") or "").lower()
            or item.get("schedule_enabled")
        ),
        jobs[0] if jobs else None,
    )
    start_date, end_date = _scheduled_project_job_dates()
    policy = _scheduled_comment_policy_for_growth_project(
        {
            "settings": {
                "comment_collection_enabled": comment_collection_enabled,
                "daily_collection_limit_per_platform": project_record.get(
                    "daily_collection_limit_per_platform"
                ),
            }
        }
    )
    policy.growth_project_key = _growth_project_job_key(int(project_record["id"]))
    policy.refresh_time_utc8 = fixed_refresh_time
    payload = {
        "name": f"{project_name} scheduled refresh",
        "topic": project_id,
        "platforms": platforms,
        "keywords": active_keywords,
        "collection_mode": "search",
        "comment_policy": policy.model_dump(mode="json"),
        "start_date": start_date,
        "end_date": end_date,
        "schedule_enabled": interval_minutes is not None,
        "schedule_interval_minutes": interval_minutes,
    }
    schedule_status = JOB_PENDING if start_immediately else JOB_COMPLETED
    next_run_at = None
    if interval_minutes is not None and not start_immediately:
        next_run_at = next_utc8_daily_run_at(fixed_refresh_time) or (
            datetime.now(timezone.utc) + timedelta(minutes=interval_minutes)
        )

    if scheduled_job is None:
        created = await get_service().create_job(
            ResearchJobCreate(
                name=payload["name"],
                topic=payload["topic"],
                platforms=payload["platforms"],
                keywords=payload["keywords"],
                start_date=payload["start_date"],
                end_date=payload["end_date"],
                collection_mode="search",
                comment_policy=policy,
                schedule_enabled=payload["schedule_enabled"],
                schedule_interval_minutes=payload["schedule_interval_minutes"],
                next_run_at=next_run_at,
            )
        )
        updated = await repository.update_job(
            int(created["id"]),
            {
                "status": schedule_status,
                "next_run_at": next_run_at,
            },
        )
        return updated or created

    current_status = str(scheduled_job.get("status") or "")
    if current_status in {JOB_RUNNING, JOB_QUEUED}:
        schedule_status = current_status
        next_run_at = scheduled_job.get("next_run_at")
    elif current_status == JOB_PENDING and not start_immediately:
        schedule_status = JOB_COMPLETED

    updated = await repository.update_job(
        int(scheduled_job["id"]),
        {
            **payload,
            "status": schedule_status,
            "next_run_at": next_run_at,
        },
    )
    return updated or scheduled_job


async def _pause_growth_project_scheduled_jobs(
    repository: ResearchRepository,
    *,
    project_id: str,
) -> None:
    jobs = await repository.list_jobs_for_project([project_id])
    for job in jobs:
        if not (
            "scheduled refresh" in str(job.get("name") or "").lower()
            or job.get("schedule_enabled")
        ):
            continue
        await repository.update_job(
            int(job["id"]),
            {
                "schedule_enabled": False,
                "schedule_interval_minutes": None,
                "next_run_at": None,
                "status": JOB_COMPLETED,
            },
        )


async def _sync_growth_project_collection_plans(
    repository: ResearchRepository,
    project: dict,
) -> None:
    interval = _refresh_interval_from_project(project)
    platforms = project.get("platforms") or []
    syncer = getattr(repository, "sync_growth_project_collection_plans", None)
    if syncer is not None:
        await syncer(project["id"], platforms=platforms, interval_minutes=interval)
        return
    for platform in platforms:
        await repository.create_growth_project_collection_plan(
            {
                "project_id": project["id"],
                "platform": platform,
                "collection_mode": "search",
                "keyword_scope": "active",
                "enabled": True,
                "schedule_mode": "interval" if interval else "manual",
                "schedule_interval_minutes": interval,
            }
        )


async def _replace_growth_project_keywords(
    repository: ResearchRepository,
    *,
    project_record_id: int,
    keywords: list[dict],
) -> None:
    normalized = _normalize_growth_project_keywords(keywords)
    if not any(item["status"] == "active" and item["keyword_type"] != "excluded" for item in normalized):
        raise HTTPException(
            status_code=400,
            detail="Growth project requires at least one active keyword",
        )
    await repository.delete_growth_project_keywords(project_record_id)
    for item in normalized:
        await repository.create_growth_project_keyword(
            {
                "project_id": project_record_id,
                **item,
            }
        )


def _normalize_growth_project_keywords(keywords: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in keywords:
        keyword = str(item.get("keyword") or "").strip()
        if not keyword:
            continue
        keyword_type = str(item.get("keyword_type") or "core").strip() or "core"
        if keyword_type not in {"core", "expanded", "excluded", "pending"}:
            keyword_type = "expanded"
        status = str(item.get("status") or "active").strip() or "active"
        if keyword_type == "excluded" or status == "excluded":
            keyword_type = "excluded"
            status = "excluded"
        elif status not in {"active", "pending", "inactive"}:
            status = "active"
        source = str(item.get("source") or "manual").strip()[:32] or "manual"
        key = (keyword, keyword_type)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "keyword": keyword,
                "keyword_type": keyword_type,
                "source": source,
                "status": status,
            }
        )
    return normalized


async def _apply_scene_pack_keywords_to_growth_project(
    repository: ResearchRepository,
    *,
    project_record_id: int,
    scene_pack_id: int,
    mode: str,
) -> None:
    if mode == "replace":
        await repository.delete_growth_project_keywords(project_record_id)
    scene_keywords = await repository.list_scene_pack_keywords(
        scene_pack_ids=[scene_pack_id],
        enabled_only=True,
    )
    for keyword in scene_keywords:
        keyword_type, status = _project_keyword_type_and_status(keyword.get("keyword_type"))
        await repository.create_growth_project_keyword(
            {
                "project_id": project_record_id,
                "scene_pack_id": scene_pack_id,
                "keyword": keyword["keyword"],
                "keyword_type": keyword_type,
                "source": "scene_pack",
                "status": status,
            }
        )


def _collection_keywords_from_scene_pack(keywords: list[dict]) -> list[str]:
    collectable_types = {"primary", "secondary", "synonym", "platform_adapted", "core", "expanded"}
    seen: set[str] = set()
    result: list[str] = []
    for item in keywords:
        keyword = str(item.get("keyword") or "").strip()
        keyword_type = str(item.get("keyword_type") or "")
        if not keyword or keyword_type not in collectable_types:
            continue
        if keyword in seen:
            continue
        seen.add(keyword)
        result.append(keyword)
    return result


def _project_keyword_type_and_status(keyword_type: str | None) -> tuple[str, str]:
    mapping = {
        "primary": ("core", "active"),
        "secondary": ("expanded", "active"),
        "synonym": ("expanded", "active"),
        "platform_adapted": ("expanded", "active"),
        "ai_suggested": ("pending", "pending"),
        "negative": ("excluded", "excluded"),
    }
    return mapping.get(str(keyword_type or ""), ("expanded", "active"))


async def _growth_project_record_for_identifier(
    repository: ResearchRepository,
    project_id: str,
) -> dict | None:
    resolver = getattr(repository, "resolve_growth_project_record", None)
    if resolver is not None:
        return await resolver(project_id, include_archived=True)
    if project_id.isdigit():
        return await repository.get_growth_project_record(int(project_id))
    for record in await repository.list_growth_project_records(include_archived=True):
        if _project_slug(record["name"]) == project_id:
            return record
    return None


async def _ensure_growth_project_record_for_identifier(
    repository: ResearchRepository,
    project_id: str,
) -> dict:
    record = await _growth_project_record_for_identifier(repository, project_id)
    if record:
        return record
    project = await get_service().get_growth_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    summary = project["project"]
    return await repository.create_growth_project(
        {
            "name": summary["name"],
            "primary_goal": summary.get("primary_goal") or "topic_discovery",
            "platforms": summary.get("platforms") or [],
            "collection_status": "not_started",
            "sample_status": summary.get("sample_status", {}).get("kind") or "sample_insufficient",
            "recommended_action": summary.get("recommended_action", {}).get("kind") or "start_collection",
            "archived": False,
        }
    )


@router.post("/jobs/{job_id}/execution/plan")
async def preview_research_execution_plan(job_id: int, request: ResearchExecutionRequest):
    require_research_database()
    service = get_service()
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    options = _execution_options_from_request(request)
    try:
        crawler_requests = build_crawler_start_requests(job, options=options)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"job_id": job_id, "steps": execution_plan_to_dict(crawler_requests)}


@router.post("/jobs/{job_id}/execute")
async def execute_research_job(job_id: int, request: ResearchExecutionRequest):
    global _research_execution_job_id, _research_execution_task
    if _research_execution_at_capacity():
        raise HTTPException(status_code=409, detail="Research execution concurrency limit reached")

    salt = os.getenv("RESEARCH_AUTHOR_HASH_SALT")
    if request.backfill_after_crawl and not salt:
        raise HTTPException(
            status_code=400,
            detail="RESEARCH_AUTHOR_HASH_SALT must be configured before execution with backfill",
        )

    require_research_database()
    service = get_service()
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")

    options = _execution_options_from_request(request)
    local_crawler_manager = CrawlerManager()
    task = asyncio.create_task(
        _run_research_execution_background(job=job, options=options, salt=salt, crawler=local_crawler_manager)
    )
    _research_executions[job_id] = {
        "task": task,
        "crawler_manager": local_crawler_manager,
        "started_at": date.today().isoformat(),
    }
    _sync_legacy_execution_pointer()

    return {
        "status": "accepted",
        "job_id": job_id,
        "message": "Research execution started in background",
    }


async def _project_record_for_job(
    repository: ResearchRepository,
    job: dict[str, Any],
) -> dict[str, Any] | None:
    comment_policy = job.get("comment_policy") or {}
    project_key = str(comment_policy.get("growth_project_key") or "")
    if project_key.startswith("growth_project_record_"):
        record_id = project_key.removeprefix("growth_project_record_")
        if record_id.isdigit():
            return await repository.get_growth_project_record(int(record_id))
    topic = str(job.get("topic") or "").strip()
    if topic:
        return await _growth_project_record_for_identifier(repository, topic)
    return None


async def _list_project_posts_for_strategy(
    repository: ResearchRepository,
    *,
    project_id: str,
) -> list[dict[str, Any]]:
    jobs = await repository.list_jobs_for_project([project_id])
    posts: list[dict[str, Any]] = []
    for item in jobs[:8]:
        posts.extend(await repository.list_all_posts(job_id=int(item["id"]), limit=600))
    return posts


async def _sync_growth_project_collection_outcome(
    repository: ResearchRepository,
    *,
    project_record: dict[str, Any] | None,
    job: dict[str, Any],
) -> None:
    if project_record is None:
        return
    status = str(job.get("status") or "")
    payload: dict[str, Any] = {}
    if status == JOB_COMPLETED:
        payload = {
            "collection_status": "completed",
            "last_collected_at": datetime.now(timezone.utc),
            "recommended_action": "review_strategy",
        }
    elif status == JOB_FAILED:
        payload = {
            "collection_status": "failed",
            "recommended_action": "start_collection",
        }
    elif status == JOB_CANCELLED:
        payload = {
            "collection_status": "stopped",
            "recommended_action": "start_collection",
        }
    elif status == JOB_PAUSED_BY_PLATFORM_CONFIG:
        payload = {
            "collection_status": "paused",
            "recommended_action": "start_collection",
        }
    if payload:
        await repository.update_growth_project(int(project_record["id"]), payload)


async def _set_project_content_strategy_refresh_state(
    repository: ResearchRepository,
    project_record_id: int,
    *,
    status: str,
    trigger: str,
    collection_job_id: int | None = None,
    last_error: str | None = None,
    started: bool = False,
    completed: bool = False,
    collection_completed: bool = False,
) -> None:
    state = await load_project_content_strategy_state(repository, project_record_id)
    now = datetime.now(timezone.utc).isoformat()
    scheduled_refresh = state["scheduled_refresh"]
    scheduled_refresh["status"] = status
    scheduled_refresh["trigger"] = trigger
    if collection_job_id is not None:
        scheduled_refresh["last_collection_job_id"] = collection_job_id
    if started:
        scheduled_refresh["last_started_at"] = now
    if collection_completed:
        scheduled_refresh["last_collection_completed_at"] = now
    if completed:
        scheduled_refresh["last_completed_at"] = now
    if last_error is None and status in {"collecting", "ai_analyzing", "completed", "fallback"}:
        scheduled_refresh["last_error"] = None
    elif last_error is not None:
        scheduled_refresh["last_error"] = last_error
    await save_project_content_strategy_state(repository, project_record_id, state)


async def _run_research_execution_background(
    *,
    job: dict,
    options: ResearchExecutionOptions,
    salt: str | None,
    crawler: CrawlerManager | None = None,
    org_id: int | None = None,
):
    global _research_execution_job_id, _research_execution_task
    resolved_org_id = _coerce_org_id(org_id) or _coerce_org_id(job.get("org_id"))
    repository = _repository_for_org(resolved_org_id)
    backfill = (
        ExistingPlatformBackfill(repository, author_hash_salt=salt)
        if options.backfill_after_crawl and salt
        else None
    )
    manager = ResearchExecutionManager(
        crawler_manager=crawler or crawler_manager,
        repository=repository,
        backfill=backfill,
    )
    project_record = await _project_record_for_job(repository, job)
    scheduled_strategy_refresh = bool(project_record and job.get("schedule_enabled"))
    try:
        if scheduled_strategy_refresh and project_record is not None:
            await _set_project_content_strategy_refresh_state(
                repository,
                int(project_record["id"]),
                status="collecting",
                trigger="schedule",
                collection_job_id=int(job["id"]),
                last_error=None,
                started=True,
            )
        await manager.execute(job=job, options=options)
        final_job = await repository.get_job(int(job["id"])) or job
        await _sync_growth_project_collection_outcome(
            repository,
            project_record=project_record,
            job=final_job,
        )
        if scheduled_strategy_refresh and project_record is not None and final_job.get("status") == JOB_COMPLETED:
            await _set_project_content_strategy_refresh_state(
                repository,
                int(project_record["id"]),
                status="ai_analyzing",
                trigger="schedule",
                collection_job_id=int(job["id"]),
                last_error=None,
                collection_completed=True,
            )
            keyword_rows = await repository.list_growth_project_keywords(int(project_record["id"]))
            project_posts = await _list_project_posts_for_strategy(
                repository,
                project_id=_project_slug(str(project_record.get("name") or job.get("topic") or "")),
            )
            project_platforms = [
                str(item).strip()
                for item in (project_record.get("platforms") or [])
                if str(item).strip()
            ]
            platform_scope = project_platforms[0] if len(project_platforms) == 1 else None
            time_range = "7d" if DEFAULT_PROJECT_REFRESH_WINDOW_DAYS <= 7 else "30d"
            filters = normalize_strategy_filters(
                platform=platform_scope,
                time_range=time_range,
                goal="conversion",
                audience="all",
                stage="boost",
            )
            keyword_heat_snapshots = await repository.list_keyword_heat_snapshots(
                platform=platform_scope,
                limit=120,
            )
            content_snapshots = await repository.list_content_tracking_snapshots(
                platform=platform_scope,
                limit=120,
            )
            competitor_compositions = await repository.list_competitor_composition_snapshots(
                platform=platform_scope,
                limit=120,
            )
            base_summary = build_content_strategy_summary(
                filters=filters,
                dashboard={
                    "decision": {},
                    "opportunities": [],
                    "top_opportunities": [],
                    "watchlist": [],
                    "diagnostics": [],
                },
                posts=project_posts,
                keyword_heat_snapshots=keyword_heat_snapshots,
                content_snapshots=content_snapshots,
                competitor_compositions=competitor_compositions,
                ai_insights={"run": None, "hotspots": [], "risk_notes": []},
                ai_topic_ideas=[],
            )
            ai_bundle = await generate_project_content_strategy_ai_bundle(
                repository,
                project_record=project_record,
                keyword_rows=keyword_rows,
                posts=project_posts,
                window_days=DEFAULT_PROJECT_REFRESH_WINDOW_DAYS,
                filters=filters,
                keyword_heat_snapshots=keyword_heat_snapshots,
                content_snapshots=content_snapshots,
                competitor_compositions=competitor_compositions,
                base_summary=base_summary,
            )
            state = await load_project_content_strategy_state(repository, int(project_record["id"]))
            state["ai_insights"] = ai_bundle
            state["scheduled_refresh"].update(
                {
                    "status": ai_bundle.get("status") or "completed",
                    "trigger": "schedule",
                    "last_collection_job_id": int(job["id"]),
                    "last_error": ai_bundle.get("error"),
                }
            )
            state["scheduled_refresh"]["last_completed_at"] = datetime.now(timezone.utc).isoformat()
            await save_project_content_strategy_state(repository, int(project_record["id"]), state)
    finally:
        current = asyncio.current_task()
        if project_record is not None and scheduled_strategy_refresh:
            final_job = await repository.get_job(int(job["id"])) or job
            final_status = str(final_job.get("status") or "")
            if final_status in {JOB_FAILED, JOB_CANCELLED, JOB_PAUSED_BY_PLATFORM_CONFIG}:
                await _set_project_content_strategy_refresh_state(
                    repository,
                    int(project_record["id"]),
                    status="failed" if final_status == JOB_FAILED else "paused",
                    trigger="schedule",
                    collection_job_id=int(job["id"]),
                    last_error=final_status,
                    completed=True,
                )
        if _research_executions.get(int(job["id"]), {}).get("task") is current:
            _research_executions.pop(int(job["id"]), None)
        _sync_legacy_execution_pointer()


@router.get("/charts/kinds")
async def list_chart_kinds():
    return {
        "kinds": [
            "platform_counts",
            "post_trend",
            "comment_trend",
            "keyword_ranking",
            "time_window_ratio",
            "engagement_distribution",
            "top_posts",
            "high_engagement_timeline",
            "sentiment_distribution",
            "stance_distribution",
            "topic_tag_ranking",
            "controversy_points",
            "platform_comparison",
            "crawl_success_failure",
            "missing_field_ratio",
            "parse_failure_reasons",
        ]
    }


@router.get("/jobs/{job_id}/charts/summary")
async def get_research_chart_summary(job_id: int):
    require_research_database()
    repository = ResearchRepository()
    posts = await repository.list_posts(job_id)
    comments = await repository.list_comments(job_id)
    ai_results = await repository.list_ai_results(job_id)
    return build_chart_summary(posts=posts, comments=comments, ai_results=ai_results)


@router.post("/ai/providers")
async def create_ai_provider(request: AIProviderConfigCreate):
    require_research_database()
    repository = ResearchRepository()
    return await repository.create_ai_provider(request.model_dump(mode="python"))


@router.post("/ai/providers/4router/bootstrap")
async def bootstrap_4router_provider():
    require_research_database()
    api_key = os.getenv("FOUR_ROUTER_API_KEY") or os.getenv("FOURROUTER_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="FOUR_ROUTER_API_KEY is not configured in the local environment",
        )
    provider = await ResearchRepository().upsert_ai_provider_by_name(
        {
            "name": "4Router",
            "base_url": "https://4router.net/v1",
            "api_key": api_key,
            "model": os.getenv("FOUR_ROUTER_MODEL", "gpt-5.4-mini"),
            "timeout": 60,
            "max_concurrency": 2,
            "default_params": {"temperature": 0.2, "max_tokens": 1200},
            "enabled": True,
        }
    )
    return {"ok": True, "provider": provider, "api_key_set": True}


@router.post("/ai/providers/gateway/bootstrap")
async def bootstrap_gateway_provider():
    require_research_database()
    api_key = os.getenv("AI_GATEWAY_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="AI_GATEWAY_API_KEY is not configured in the local environment",
        )
    provider = await ResearchRepository().upsert_ai_provider_by_name(
        {
            "name": os.getenv("AI_GATEWAY_NAME", "AI Gateway"),
            "base_url": os.getenv("AI_GATEWAY_BASE_URL", "https://4router.net/v1"),
            "api_key": api_key,
            "model": os.getenv("AI_GATEWAY_MODEL", "gpt-5.4-mini"),
            "timeout": int(os.getenv("AI_GATEWAY_TIMEOUT", "60")),
            "max_concurrency": int(os.getenv("AI_GATEWAY_MAX_CONCURRENCY", "2")),
            "default_params": {
                "temperature": float(os.getenv("AI_GATEWAY_TEMPERATURE", "0.2")),
                "max_tokens": int(os.getenv("AI_GATEWAY_MAX_TOKENS", "1200")),
            },
            "enabled": True,
        }
    )
    return {"ok": True, "provider": provider, "api_key_set": True}


@router.get("/ai/providers")
async def list_ai_providers():
    require_research_database()
    repository = ResearchRepository()
    return {"providers": await repository.list_ai_providers()}


@router.post("/ai/providers/{provider_id}/test")
async def test_ai_provider(provider_id: int):
    require_research_database()
    repository = ResearchRepository()
    provider = await repository.get_ai_provider(provider_id, include_secret=True)
    if provider is None:
        raise HTTPException(status_code=404, detail="AI provider not found")
    client = OpenAICompatibleProvider(
        base_url=provider["base_url"],
        api_key=provider["api_key"],
        model=provider["model"],
        timeout=provider["timeout"],
    )
    try:
        result = await client.test_connection()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider test failed: {exc}") from exc
    return {"ok": True, "provider_id": provider_id, "model": provider["model"], "result": result}


@router.post("/ai/prompts")
async def create_ai_prompt_template(request: AIPromptTemplateCreate):
    require_research_database()
    repository = ResearchRepository()
    return await repository.create_prompt_template(request.model_dump(mode="python"))


@router.get("/ai/prompts")
async def list_ai_prompt_templates():
    require_research_database()
    repository = ResearchRepository()
    return {"prompts": await repository.list_prompt_templates()}


@router.post("/ai/prompts/defaults/bootstrap")
async def bootstrap_default_ai_prompt_templates():
    require_research_database()
    repository = ResearchRepository()
    prompts = []
    for prompt in DEFAULT_AI_PROMPTS:
        prompts.append(await repository.upsert_prompt_template_by_name(prompt))
    return {"ok": True, "created_or_updated": len(prompts), "prompts": prompts}


@router.post("/ai/analysis-jobs")
async def create_ai_analysis_job(request: AIAnalysisJobCreate):
    require_research_database()
    repository = ResearchRepository()
    payload = request.model_dump(mode="python")
    payload["status"] = "pending"
    return await repository.create_ai_analysis_job(payload)


@router.get("/jobs/{job_id}/ai/analysis-jobs")
async def list_research_job_ai_analysis_jobs(job_id: int):
    require_research_database()
    repository = ResearchRepository()
    return {"jobs": await repository.list_ai_analysis_jobs(job_id)}


@router.get("/jobs/{job_id}/ai/status")
async def get_research_job_ai_status(job_id: int):
    require_research_database()
    repository = ResearchRepository()
    job = await repository.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    stats = await repository.get_job_stats(job_id)
    providers = await repository.list_ai_providers()
    prompts = await repository.list_prompt_templates()
    analysis_jobs = await repository.list_ai_analysis_jobs(job_id)
    results = await repository.list_ai_results(job_id)
    enabled_providers = [provider for provider in providers if provider.get("enabled")]
    enabled_prompts = [prompt for prompt in prompts if prompt.get("enabled")]
    diagnostics = []
    if not enabled_providers:
        diagnostics.append(
            {
                "code": "missing_provider",
                "message": "No enabled AI provider is configured. Bootstrap an AI gateway provider first.",
            }
        )
    if not enabled_prompts:
        diagnostics.append(
            {
                "code": "missing_prompt",
                "message": "No enabled AI prompt template is configured. Bootstrap default prompts first.",
            }
        )
    if not stats["posts"] and not stats["comments"]:
        diagnostics.append(
            {
                "code": "missing_targets",
                "message": "The selected research job has no posts or comments to analyze.",
            }
        )
    return {
        "job": job,
        "stats": stats,
        "providers": providers,
        "prompts": prompts,
        "analysis_jobs": analysis_jobs,
        "results_count": len(results),
        "can_run": bool(enabled_providers and enabled_prompts and (stats["posts"] or stats["comments"])),
        "diagnostics": diagnostics,
    }


@router.post("/ai/analysis-jobs/{analysis_job_id}/run")
async def run_ai_analysis_job(analysis_job_id: int):
    require_research_database()
    repository = ResearchRepository()
    job = await repository.get_ai_analysis_job(analysis_job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="AI analysis job not found")
    existing = AI_ANALYSIS_TASKS.get(analysis_job_id)
    existing_task = existing.get("task") if existing else None
    if existing_task and not existing_task.done():
        return {
            "status": "accepted",
            "analysis_job_id": analysis_job_id,
            "message": "AI analysis job is already running",
        }
    runner = AIAnalysisRunner(repository)
    task = asyncio.create_task(runner.run(analysis_job_id))
    now = date.today().isoformat()
    AI_ANALYSIS_TASKS[analysis_job_id] = {
        "task": task,
        "status": "running",
        "research_job_id": job["research_job_id"],
        "created_at": now,
        "updated_at": now,
        "message": "AI analysis running",
    }

    def _mark_ai_task_done(done_task: asyncio.Task, job_id: int = analysis_job_id) -> None:
        record = AI_ANALYSIS_TASKS.get(job_id)
        if not record:
            return
        if done_task.cancelled():
            status = "cancelled"
            message = "AI analysis cancelled"
        else:
            exc = done_task.exception()
            status = "failed" if exc else "completed"
            message = str(exc) if exc else "AI analysis completed"
        record["status"] = status
        record["updated_at"] = date.today().isoformat()
        record["message"] = message

    task.add_done_callback(_mark_ai_task_done)
    return {
        "status": "accepted",
        "analysis_job_id": analysis_job_id,
        "message": "AI analysis job started in background",
    }


@router.post("/ai/analysis-jobs/{analysis_job_id}/results")
async def create_ai_analysis_result(
    analysis_job_id: int, request: AIAnalysisResultCreate
):
    require_research_database()
    repository = ResearchRepository()
    return await repository.create_ai_analysis_result(
        analysis_job_id=analysis_job_id,
        payload=request.model_dump(mode="python"),
    )


@router.get("/jobs/{job_id}/ai/results")
async def list_research_job_ai_results(job_id: int):
    require_research_database()
    repository = ResearchRepository()
    return {"results": await repository.list_ai_results(job_id)}


@router.post("/jobs/{job_id}/export")
async def export_research_job(job_id: int):
    require_research_database()
    repository = ResearchRepository()
    job = await repository.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    posts = await repository.list_posts(job_id)
    comments = await repository.list_comments(job_id)
    authors = await repository.list_authors(job_id)
    ai_results = await repository.list_ai_results(job_id)
    raw_records = await repository.list_raw_records(job_id)
    chart_summary = build_chart_summary(posts=posts, comments=comments, ai_results=ai_results)
    exporter = ResearchExporter()
    result = exporter.export_job(
        job_id=job_id,
        job_summary=job,
        posts=posts,
        comments=comments,
        authors=authors,
        ai_results=ai_results,
        raw_records=raw_records,
        charts=[],
        chart_summary=chart_summary,
    )
    result["files_url"] = f"/api/research/exports/{job_id}/files"
    return result


@router.get("/exports/{job_id}/files")
async def list_research_export_files(job_id: int):
    export_dir = _resolve_export_dir(job_id)
    if not export_dir.exists():
        raise HTTPException(status_code=404, detail="Export directory not found")
    files = []
    for path in sorted(item for item in export_dir.rglob("*") if item.is_file()):
        relative_path = path.relative_to(export_dir).as_posix()
        files.append(
            {
                "path": relative_path,
                "size": path.stat().st_size,
                "download_url": (
                    f"/api/research/exports/{job_id}/download/{quote(relative_path)}"
                ),
            }
        )
    return {"job_id": job_id, "files": files}


@router.get("/exports/{job_id}/download/{file_path:path}")
async def download_research_export_file(job_id: int, file_path: str):
    export_dir = _resolve_export_dir(job_id)
    target = (export_dir / file_path).resolve()
    try:
        target.relative_to(export_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid export path") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Export file not found")
    return FileResponse(target, filename=target.name)


@router.get("/execution/status")
async def get_research_execution_status():
    running_job_ids = _running_research_job_ids()
    active_job_id = running_job_ids[0] if running_job_ids else None
    crawler_status = _active_crawler_snapshot(active_job_id) or crawler_manager.get_status()
    return {
        **crawler_status,
        "research_execution_running": bool(running_job_ids),
        "research_execution_job_id": active_job_id,
        "research_execution_job_ids": running_job_ids,
        "research_execution_concurrency": get_research_execution_concurrency(),
    }


@router.post("/execution/stop")
async def stop_research_execution():
    stopped_jobs = []
    stopped_crawler = False
    for job_id in _running_research_job_ids():
        result = await cancel_active_research_execution_job(job_id)
        if result["status"] == "stopping":
            stopped_jobs.append(job_id)
            stopped_crawler = bool(result.get("crawler_stopped")) or stopped_crawler
    if stopped_jobs:
        return {
            "status": "stopping",
            "job_id": stopped_jobs[0],
            "job_ids": stopped_jobs,
            "crawler_stopped": stopped_crawler,
        }
    return {"status": "idle", "crawler_stopped": stopped_crawler}


@router.post("/jobs/{job_id}/backfill/weibo")
async def backfill_weibo_existing_data(job_id: int, request: ExistingDataBackfillRequest):
    salt = os.getenv("RESEARCH_AUTHOR_HASH_SALT")
    if not salt:
        raise HTTPException(
            status_code=400,
            detail="RESEARCH_AUTHOR_HASH_SALT must be configured before backfill",
        )
    require_research_database()
    runner = ExistingPlatformBackfill(ResearchRepository(), author_hash_salt=salt)
    return await runner.backfill_weibo(
        job_id=job_id,
        keywords=request.keywords,
        target_ids=request.target_ids,
        creator_ids=request.creator_ids,
        limit=request.limit,
    )


@router.post("/jobs/{job_id}/backfill/zhihu")
async def backfill_zhihu_existing_data(job_id: int, request: ExistingDataBackfillRequest):
    salt = os.getenv("RESEARCH_AUTHOR_HASH_SALT")
    if not salt:
        raise HTTPException(
            status_code=400,
            detail="RESEARCH_AUTHOR_HASH_SALT must be configured before backfill",
        )
    require_research_database()
    runner = ExistingPlatformBackfill(ResearchRepository(), author_hash_salt=salt)
    return await runner.backfill_zhihu(
        job_id=job_id,
        keywords=request.keywords,
        target_ids=request.target_ids,
        creator_ids=request.creator_ids,
        limit=request.limit,
    )


@router.post("/jobs/{job_id}/backfill/{platform}")
async def backfill_existing_platform_data(
    job_id: int, platform: str, request: ExistingDataBackfillRequest
):
    if platform not in BACKFILL_RESEARCH_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unsupported backfill platform: {platform}")
    salt = os.getenv("RESEARCH_AUTHOR_HASH_SALT")
    if not salt:
        raise HTTPException(
            status_code=400,
            detail="RESEARCH_AUTHOR_HASH_SALT must be configured before backfill",
        )
    require_research_database()
    runner = ExistingPlatformBackfill(ResearchRepository(), author_hash_salt=salt)
    return await runner.backfill_platform(
        platform,
        job_id=job_id,
        keywords=request.keywords,
        target_ids=request.target_ids,
        creator_ids=request.creator_ids,
        limit=request.limit,
    )


def _resolve_export_dir(job_id: int) -> Path:
    return (EXPORT_BASE_DIR / f"research_job_{job_id}").resolve()
