import asyncio
import os
from datetime import date
from pathlib import Path
from urllib.parse import quote

import config
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError

from api.schemas import SaveDataOptionEnum
from research.ai_analysis import AIAnalysisRunner
from research.ai_provider import OpenAICompatibleProvider
from research.backfill import ExistingPlatformBackfill
from research.execution import (
    ResearchExecutionManager,
    ResearchExecutionOptions,
    build_crawler_start_requests,
    execution_plan_to_dict,
)
from research.exporter import ResearchExporter
from research.charts import build_chart_summary
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
from research.scheduler import ResearchScheduler
from research.schemas import (
    AIAnalysisJobCreate,
    AIAnalysisResultCreate,
    AIProviderConfigCreate,
    AIPromptTemplateCreate,
    AuthProfileCreate,
    AuthProfileUpdate,
    CommentPolicy,
    ExistingDataBackfillRequest,
    GlobalDefaultsUpsert,
    GrowthProjectCreate,
    GrowthProjectUpdate,
    KeywordSetCreate,
    KeywordSetUpdate,
    PlatformCapabilityUpsert,
    PlatformRateLimitUpsert,
    ResearchExecutionRequest,
    ResearchJobCreate,
)
from research.schemas import ResearchJobUpdate
from research.service import ResearchJobService
from research.setup_status import build_research_setup_status
from research.validation import build_validation_checklist
from api.services.crawler_manager import crawler_manager

router = APIRouter(prefix="/research", tags=["research"])
_research_execution_task: asyncio.Task | None = None
_research_execution_job_id: int | None = None
_research_execution_queue: list[dict] = []
_research_queue_worker_task: asyncio.Task | None = None
EXPORT_BASE_DIR = Path("exports")
GLOBAL_DEFAULTS_KEY = "research_defaults"
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


def _execution_busy() -> bool:
    current = asyncio.current_task()
    return bool(
        _research_execution_task
        and not _research_execution_task.done()
        and _research_execution_task is not current
    )


async def schedule_and_execute_research_job(
    job_id: int,
    *,
    background: bool = True,
    force_schedule: bool = True,
) -> dict:
    global _research_execution_job_id, _research_execution_task
    require_research_database()
    if _execution_busy():
        return {
            "status": "busy",
            "job_id": _research_execution_job_id,
            "message": "A research execution is already running",
        }
    repository = ResearchRepository()
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
    _research_execution_job_id = job_id
    if background:
        _research_execution_task = asyncio.create_task(
            _run_research_execution_background(job=job, options=options, salt=salt)
        )
        return {"status": "accepted", "job_id": job_id, "schedule": schedule}
    _research_execution_task = asyncio.current_task()
    try:
        await _run_research_execution_background(job=job, options=options, salt=salt)
    finally:
        _research_execution_task = None
        _research_execution_job_id = None
    return {"status": "completed", "job_id": job_id, "schedule": schedule}


async def enqueue_research_collection_job(job_id: int, *, project_id: str | None = None) -> dict:
    global _research_queue_worker_task
    require_research_database()
    queued = {
        "job_id": job_id,
        "project_id": project_id,
        "enqueued_at": date.today().isoformat(),
    }
    if not any(item["job_id"] == job_id for item in _research_execution_queue):
        _research_execution_queue.append(queued)
        await ResearchRepository().update_job(job_id, {"status": JOB_QUEUED})
    if _research_queue_worker_task is None or _research_queue_worker_task.done():
        _research_queue_worker_task = asyncio.create_task(_run_research_execution_queue())
    return {
        "status": "queued",
        "job_id": job_id,
        "queue_position": _queue_position(job_id),
        "queue": _collection_queue_snapshot(),
    }


async def _run_research_execution_queue() -> None:
    while _research_execution_queue:
        if _execution_busy():
            await asyncio.sleep(1)
            continue
        queued = _research_execution_queue.pop(0)
        job_id = int(queued["job_id"])
        repository = ResearchRepository()
        await repository.update_job(job_id, {"status": JOB_RUNNING})
        try:
            await schedule_and_execute_research_job(job_id, background=False)
        except Exception as exc:
            await repository.update_job(job_id, {"status": JOB_FAILED})
            await repository.create_event(
                job_id=job_id,
                platform=None,
                event_type="queue_execution_failed",
                message=str(exc),
                stats={"project_id": queued.get("project_id")},
            )


def _collection_queue_snapshot() -> dict:
    return {
        "running_job_id": _research_execution_job_id if _execution_busy() else None,
        "queued_jobs": [
            {
                "job_id": item["job_id"],
                "project_id": item.get("project_id"),
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
    job = await service.create_job(
        ResearchJobCreate(
            name=f"{request.name} initial collection",
            topic=project_id,
            platforms=request_platforms,
            keywords=request_keywords,
            start_date=date.today(),
            end_date=date.today(),
            collection_mode="search",
            comment_policy=CommentPolicy(
                enable_comments=enable_comments,
                comment_limit_per_post=100 if enable_comments else None,
                enable_sub_comments=request.collection_depth == "deep",
                sub_comment_limit_per_comment=20 if request.collection_depth == "deep" else 0,
                full_comment_crawl=False,
            ),
            schedule_enabled=request.refresh_cadence != "off",
            schedule_interval_minutes=_refresh_interval_minutes(request.refresh_cadence),
        )
    )
    if project_record is not None:
        await repository.update_growth_project(
            project_record["id"],
            {
                "collection_status": "queued",
                "recommended_action": "wait_for_collection",
            },
        )
    if request.start_immediately:
        await enqueue_research_collection_job(job["id"], project_id=project_id)
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
    project = await service.get_growth_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    return project


@router.patch("/growth-projects/{project_id}")
async def update_growth_project(project_id: str, request: GrowthProjectUpdate):
    require_research_database()
    repository = ResearchRepository()
    record = await _ensure_growth_project_record_for_identifier(repository, project_id)
    payload = request.model_dump(mode="python", exclude_unset=True)
    if not payload:
        return {"project": record}
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
    project = await repository.update_growth_project(record["id"], payload)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    if "platforms" in payload or "refresh_cadence" in payload or "custom_interval_value" in payload:
        await _sync_growth_project_collection_plans(repository, project)
    return {"project": project}


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


@router.get("/growth-projects/{project_id}/collection-plans")
async def list_growth_project_collection_plans(project_id: int):
    require_research_database()
    repository = ResearchRepository()
    project = await repository.get_growth_project_record(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    return {"collection_plans": await repository.list_growth_project_collection_plans(project_id)}


@router.post("/growth-projects/{project_id}/collection/start")
async def start_growth_project_collection(project_id: str):
    return await run_growth_project_collection_now(project_id)


@router.post("/growth-projects/{project_id}/collection/run-now")
async def run_growth_project_collection_now(project_id: str):
    require_research_database()
    service = get_service()
    repository = ResearchRepository()
    project = await service.get_growth_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    summary = project["project"]
    keywords = [item["keyword"] for item in project.get("keywords", []) if item.get("keyword")]
    if not keywords:
        raise HTTPException(status_code=400, detail="Growth project has no keywords to collect")
    job = await service.create_job(
        ResearchJobCreate(
            name=f"{summary['name']} collection {date.today().isoformat()}",
            topic=project_id,
            platforms=summary["platforms"],
            keywords=keywords,
            start_date=date.today(),
            end_date=date.today(),
            collection_mode="search",
            comment_policy=_comment_policy_for_growth_project(project),
        )
    )
    record = await _growth_project_record_for_identifier(repository, project_id)
    if record:
        await repository.update_growth_project(
            record["id"],
            {"collection_status": "queued", "recommended_action": "wait_for_collection"},
        )
        await repository.update_growth_project_collection_plans(record["id"], {"enabled": True})
    queue = await enqueue_research_collection_job(int(job["id"]), project_id=project_id)
    return {"status": "queued", "job": job, **queue}


@router.get("/growth-projects/{project_id}/collection/progress")
async def get_growth_project_collection_progress(project_id: str):
    require_research_database()
    service = get_service()
    project = await service.get_growth_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    records = project.get("collection_records", [])
    job_ids = [int(record["id"]) for record in records if record.get("id") is not None]
    queued_for_project = [
        item for item in _collection_queue_snapshot()["queued_jobs"]
        if item.get("project_id") == project_id
    ]
    running_job_id = _research_execution_job_id if _research_execution_job_id in job_ids else None
    current_job_id = running_job_id or (queued_for_project[0]["job_id"] if queued_for_project else (job_ids[0] if job_ids else None))
    progress = await _job_progress_snapshot(current_job_id) if current_job_id else _empty_progress()
    return {
        "project_id": project_id,
        "status": _project_collection_progress_status(
            running_job_id=running_job_id,
            queued_jobs=queued_for_project,
            progress=progress,
        ),
        "current_job_id": current_job_id,
        "running_job_id": running_job_id,
        "queued_jobs": queued_for_project,
        "queue": _collection_queue_snapshot(),
        "progress": progress,
    }


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
    return {"status": "paused", "project_id": project_id}


@router.post("/growth-projects/{project_id}/collection/stop-current-run")
async def stop_growth_project_current_run(project_id: str):
    require_research_database()
    service = get_service()
    repository = ResearchRepository()
    project = await service.get_growth_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    stopped = []
    for record in project.get("collection_records", []):
        if record.get("status") in {"pending", "queued", "running"}:
            updated = await repository.update_job(int(record["id"]), {"status": "cancelled"})
            if updated:
                stopped.append(updated)
    project_record = await _growth_project_record_for_identifier(repository, project_id)
    if project_record:
        await repository.update_growth_project(
            project_record["id"],
            {"collection_status": "stopped", "recommended_action": "start_collection"},
        )
    return {"status": "stopped", "project_id": project_id, "jobs": stopped}


@router.post("/growth-projects/{project_id}/archive")
async def archive_growth_project(project_id: str):
    require_research_database()
    repository = ResearchRepository()
    record = await _growth_project_record_for_identifier(repository, project_id)
    if record:
        project = await repository.update_growth_project(record["id"], {"archived": True})
        return {"status": "archived", "project": project}
    return {"status": "archived", "project_id": project_id}


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
async def list_research_job_posts(job_id: int, limit: int = 200):
    require_research_database()
    repository = ResearchRepository()
    return {"posts": await repository.list_posts(job_id, limit=limit)}


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


def _empty_progress() -> dict:
    return {
        "percent": 0,
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
        "job": None,
        "latest_event": None,
    }


async def _job_progress_snapshot(job_id: int | None) -> dict:
    if job_id is None:
        return _empty_progress()
    repository = ResearchRepository()
    job = await repository.get_job(int(job_id))
    if job is None:
        return _empty_progress()
    units = await repository.list_crawl_units(int(job_id))
    stats = await repository.get_job_stats(int(job_id))
    events = await repository.list_events(int(job_id), limit=1)
    unit_counts = {
        CRAWL_UNIT_PENDING: 0,
        CRAWL_UNIT_RUNNING: 0,
        CRAWL_UNIT_RETRYING: 0,
        CRAWL_UNIT_SUCCEEDED: 0,
        CRAWL_UNIT_FAILED: 0,
        CRAWL_UNIT_CANCELLED: 0,
        "total": len(units),
    }
    for unit in units:
        status = str(unit.get("status") or CRAWL_UNIT_PENDING)
        unit_counts[status] = int(unit_counts.get(status, 0)) + 1
    if units:
        finished = (
            unit_counts[CRAWL_UNIT_SUCCEEDED]
            + unit_counts[CRAWL_UNIT_FAILED]
            + unit_counts[CRAWL_UNIT_CANCELLED]
        )
        percent = round((finished / max(unit_counts["total"], 1)) * 100)
    else:
        percent = _fallback_job_percent(str(job.get("status") or JOB_PENDING))
    return {
        "percent": percent,
        "unit_counts": unit_counts,
        "sample_counts": {
            "posts": int(stats.get("posts") or 0),
            "comments": int(stats.get("comments") or 0),
            "raw_records": int(stats.get("raw_records") or 0),
            "creators": int(stats.get("authors") or stats.get("creators") or 0),
        },
        "job": job,
        "latest_event": events[0] if events else None,
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
    progress: dict,
) -> str:
    if running_job_id is not None:
        return "running"
    if queued_jobs:
        return "queued"
    job = progress.get("job") or {}
    status = str(job.get("status") or "")
    if status in {JOB_COMPLETED, JOB_FAILED, JOB_CANCELLED}:
        return status
    return status or "idle"


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


async def _sync_growth_project_collection_plans(
    repository: ResearchRepository,
    project: dict,
) -> None:
    interval = _refresh_interval_from_project(project)
    platforms = project.get("platforms") or []
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
    if _research_execution_task and not _research_execution_task.done():
        raise HTTPException(status_code=409, detail="A research execution is already running")

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
    _research_execution_job_id = job_id
    _research_execution_task = asyncio.create_task(
        _run_research_execution_background(job=job, options=options, salt=salt)
    )

    return {
        "status": "accepted",
        "job_id": job_id,
        "message": "Research execution started in background",
    }


async def _run_research_execution_background(
    *,
    job: dict,
    options: ResearchExecutionOptions,
    salt: str | None,
):
    global _research_execution_job_id, _research_execution_task
    repository = ResearchRepository()
    backfill = (
        ExistingPlatformBackfill(repository, author_hash_salt=salt)
        if options.backfill_after_crawl and salt
        else None
    )
    manager = ResearchExecutionManager(
        crawler_manager=crawler_manager,
        repository=repository,
        backfill=backfill,
    )
    try:
        await manager.execute(job=job, options=options)
    finally:
        if asyncio.current_task() is _research_execution_task:
            _research_execution_task = None
            _research_execution_job_id = None


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
    runner = AIAnalysisRunner(repository)
    asyncio.create_task(runner.run(analysis_job_id))
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
    crawler_status = crawler_manager.get_status()
    running = bool(_research_execution_task and not _research_execution_task.done())
    return {
        **crawler_status,
        "research_execution_running": running,
        "research_execution_job_id": _research_execution_job_id if running else None,
    }


@router.post("/execution/stop")
async def stop_research_execution():
    global _research_execution_task
    stopped_crawler = await crawler_manager.stop()
    if _research_execution_task and not _research_execution_task.done():
        _research_execution_task.cancel()
        return {
            "status": "stopping",
            "job_id": _research_execution_job_id,
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
