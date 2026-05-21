import os
import asyncio
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
    ExistingDataBackfillRequest,
    GlobalDefaultsUpsert,
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
EXPORT_BASE_DIR = Path("exports")
GLOBAL_DEFAULTS_KEY = "research_defaults"


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


async def schedule_and_execute_research_job(
    job_id: int,
    *,
    background: bool = True,
    force_schedule: bool = True,
) -> dict:
    global _research_execution_job_id, _research_execution_task
    require_research_database()
    if _research_execution_task and not _research_execution_task.done():
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
