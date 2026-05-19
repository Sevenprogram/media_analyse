import os
import asyncio

from fastapi import APIRouter, HTTPException

from research.ai_analysis import AIAnalysisRunner
from research.backfill import ExistingPlatformBackfill
from research.execution import (
    ResearchExecutionManager,
    ResearchExecutionOptions,
    build_crawler_start_requests,
    execution_plan_to_dict,
)
from research.exporter import ResearchExporter
from research.charts import build_chart_summary
from research.repository import ResearchRepository
from research.schemas import (
    AIAnalysisJobCreate,
    AIAnalysisResultCreate,
    AIProviderConfigCreate,
    AIPromptTemplateCreate,
    ExistingDataBackfillRequest,
    ResearchExecutionRequest,
    ResearchJobCreate,
)
from research.schemas import ResearchJobUpdate
from research.service import ResearchJobService
from api.services.crawler_manager import crawler_manager

router = APIRouter(prefix="/research", tags=["research"])
_research_execution_task: asyncio.Task | None = None


def get_service() -> ResearchJobService:
    return ResearchJobService(ResearchRepository())


@router.get("/health")
async def research_health():
    return {"status": "ok", "module": "research"}


@router.post("/jobs")
async def create_research_job(request: ResearchJobCreate):
    service = get_service()
    return await service.create_job(request)


@router.get("/jobs")
async def list_research_jobs():
    service = get_service()
    return {"jobs": await service.list_jobs()}


@router.get("/jobs/{job_id}")
async def get_research_job(job_id: int):
    service = get_service()
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job


@router.get("/jobs/{job_id}/events")
async def list_research_job_events(job_id: int, limit: int = 200):
    repository = ResearchRepository()
    return {"events": await repository.list_events(job_id=job_id, limit=limit)}


@router.get("/jobs/{job_id}/stats")
async def get_research_job_stats(job_id: int):
    repository = ResearchRepository()
    return await repository.get_job_stats(job_id)


@router.patch("/jobs/{job_id}")
async def update_research_job(job_id: int, request: ResearchJobUpdate):
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
    return {
        "platforms": [
            {"value": "wb", "label": "Weibo"},
            {"value": "zhihu", "label": "Zhihu"},
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
    global _research_execution_task
    if _research_execution_task and not _research_execution_task.done():
        raise HTTPException(status_code=409, detail="A research execution is already running")

    salt = os.getenv("RESEARCH_AUTHOR_HASH_SALT")
    if request.backfill_after_crawl and not salt:
        raise HTTPException(
            status_code=400,
            detail="RESEARCH_AUTHOR_HASH_SALT must be configured before execution with backfill",
        )

    service = get_service()
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")

    options = _execution_options_from_request(request)
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
    await manager.execute(job=job, options=options)


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
    repository = ResearchRepository()
    posts = await repository.list_posts(job_id)
    comments = await repository.list_comments(job_id)
    ai_results = await repository.list_ai_results(job_id)
    return build_chart_summary(posts=posts, comments=comments, ai_results=ai_results)


@router.post("/ai/providers")
async def create_ai_provider(request: AIProviderConfigCreate):
    repository = ResearchRepository()
    return await repository.create_ai_provider(request.model_dump(mode="python"))


@router.get("/ai/providers")
async def list_ai_providers():
    repository = ResearchRepository()
    return {"providers": await repository.list_ai_providers()}


@router.post("/ai/prompts")
async def create_ai_prompt_template(request: AIPromptTemplateCreate):
    repository = ResearchRepository()
    return await repository.create_prompt_template(request.model_dump(mode="python"))


@router.get("/ai/prompts")
async def list_ai_prompt_templates():
    repository = ResearchRepository()
    return {"prompts": await repository.list_prompt_templates()}


@router.post("/ai/analysis-jobs")
async def create_ai_analysis_job(request: AIAnalysisJobCreate):
    repository = ResearchRepository()
    payload = request.model_dump(mode="python")
    payload["status"] = "pending"
    return await repository.create_ai_analysis_job(payload)


@router.get("/jobs/{job_id}/ai/analysis-jobs")
async def list_research_job_ai_analysis_jobs(job_id: int):
    repository = ResearchRepository()
    return {"jobs": await repository.list_ai_analysis_jobs(job_id)}


@router.post("/ai/analysis-jobs/{analysis_job_id}/run")
async def run_ai_analysis_job(analysis_job_id: int):
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
    repository = ResearchRepository()
    return await repository.create_ai_analysis_result(
        analysis_job_id=analysis_job_id,
        payload=request.model_dump(mode="python"),
    )


@router.get("/jobs/{job_id}/ai/results")
async def list_research_job_ai_results(job_id: int):
    repository = ResearchRepository()
    return {"results": await repository.list_ai_results(job_id)}


@router.post("/jobs/{job_id}/export")
async def export_research_job(job_id: int):
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
    return exporter.export_job(
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


@router.get("/execution/status")
async def get_research_execution_status():
    crawler_status = crawler_manager.get_status()
    return {
        **crawler_status,
        "research_execution_running": bool(
            _research_execution_task and not _research_execution_task.done()
        ),
    }


@router.post("/execution/stop")
async def stop_research_execution():
    global _research_execution_task
    stopped_crawler = await crawler_manager.stop()
    if _research_execution_task and not _research_execution_task.done():
        _research_execution_task.cancel()
        _research_execution_task = None
        return {"status": "stopped", "crawler_stopped": stopped_crawler}
    return {"status": "idle", "crawler_stopped": stopped_crawler}


@router.post("/jobs/{job_id}/backfill/weibo")
async def backfill_weibo_existing_data(job_id: int, request: ExistingDataBackfillRequest):
    salt = os.getenv("RESEARCH_AUTHOR_HASH_SALT")
    if not salt:
        raise HTTPException(
            status_code=400,
            detail="RESEARCH_AUTHOR_HASH_SALT must be configured before backfill",
        )
    runner = ExistingPlatformBackfill(ResearchRepository(), author_hash_salt=salt)
    return await runner.backfill_weibo(job_id=job_id, keywords=request.keywords, limit=request.limit)


@router.post("/jobs/{job_id}/backfill/zhihu")
async def backfill_zhihu_existing_data(job_id: int, request: ExistingDataBackfillRequest):
    salt = os.getenv("RESEARCH_AUTHOR_HASH_SALT")
    if not salt:
        raise HTTPException(
            status_code=400,
            detail="RESEARCH_AUTHOR_HASH_SALT must be configured before backfill",
        )
    runner = ExistingPlatformBackfill(ResearchRepository(), author_hash_salt=salt)
    return await runner.backfill_zhihu(job_id=job_id, keywords=request.keywords, limit=request.limit)
