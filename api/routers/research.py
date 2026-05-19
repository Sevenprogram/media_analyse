import os

from fastapi import APIRouter, HTTPException

from research.backfill import ExistingPlatformBackfill
from research.execution import (
    ResearchExecutionManager,
    ResearchExecutionOptions,
    build_crawler_start_requests,
    execution_plan_to_dict,
)
from research.repository import ResearchRepository
from research.schemas import (
    ExistingDataBackfillRequest,
    ResearchExecutionRequest,
    ResearchJobCreate,
)
from research.schemas import ResearchJobUpdate
from research.service import ResearchJobService
from api.services.crawler_manager import crawler_manager

router = APIRouter(prefix="/research", tags=["research"])


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

    repository = ResearchRepository()
    backfill = (
        ExistingPlatformBackfill(repository, author_hash_salt=salt)
        if request.backfill_after_crawl and salt
        else None
    )
    manager = ResearchExecutionManager(
        crawler_manager=crawler_manager,
        repository=repository,
        backfill=backfill,
    )
    try:
        manager.start_background(job=job, options=_execution_options_from_request(request))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "status": "accepted",
        "job_id": job_id,
        "message": "Research execution started in background",
    }


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
