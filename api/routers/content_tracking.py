import asyncio
import os
from datetime import date, datetime, timezone, timedelta
from math import ceil
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps.auth import require_current_user
from api.routers.research import (
    cancel_active_research_execution_job,
    require_research_database,
    schedule_and_execute_research_job,
    wait_for_research_job_status,
)
from research.content_tracking import (
    analyze_content_tracking,
    apply_tracker_ai_enhancement,
    apply_tracker_ai_sample_selection,
    build_tracker_analysis_snapshot,
    build_tracker_ai_enhancement_prompt,
    build_content_keyword_ai_prompt,
    build_content_tracking_ai_prompt,
    build_tracker_sample_selection_ai_prompt,
    build_tracker_keyword_suggestion_ai_prompt,
    extract_content_keywords,
    mark_tracker_sample_selection,
    normalize_content_keyword_ai_output,
    normalize_content_tracking_ai_output,
    normalize_tracker_ai_enhancement_output,
    normalize_tracker_keyword_suggestion_ai_output,
    normalize_tracker_sample_selection_ai_output,
    search_similar_content,
)
from research.content_fingerprint import analyze_posts_for_tracking
from research.ai_provider import OpenAICompatibleProvider
from research.repository import ResearchRepository
from research.enums import JOB_CANCELLED
from research.schemas import (
    ContentTrackingAIAnalysisRequest,
    ContentKeywordExtractionRequest,
    ContentTrackerCollectionRequest,
    ContentTrackerCreate,
    ContentTrackerUpdate,
    SimilarContentSearchRequest,
)

router = APIRouter(
    prefix="/content-tracking",
    tags=["content-tracking"],
    dependencies=[Depends(require_current_user)],
)

REALTIME_CONTENT_PLATFORMS = {"xhs", "dy"}
DEFAULT_REALTIME_COLLECTION_WINDOW_DAYS = 3
DEFAULT_TRACKER_COLLECTION_PLATFORMS = ["xhs", "dy"]
COLLECTION_PROGRESS_POLL_SECONDS = 1.2
COLLECTION_LOG_MAX_LENGTH = 180
TRACKER_ANALYSIS_ACTIVE_STATUSES = {"queued", "running"}
TRACKER_ANALYSIS_PROGRESS_STEPS: dict[str, tuple[str, int]] = {
    "queued": ("已创建分析任务", 8),
    "loading_posts": ("正在加载内容池", 24),
    "scoring_candidates": ("正在筛选候选样本", 48),
    "refining_samples": ("正在优化分析结果", 68),
    "saving_results": ("正在保存分析结果", 88),
    "completed": ("分析完成", 100),
    "failed": ("分析失败", 100),
}
PLATFORM_LABELS = {
    "xhs": "小红书",
    "dy": "抖音",
    "ks": "快手",
    "bilibili": "B站",
    "wb": "微博",
    "zhihu": "知乎",
    "tieba": "贴吧",
}


def _platform_label(platform: str | None) -> str:
    if not platform:
        return "平台"
    return PLATFORM_LABELS.get(platform, platform)


def _collection_platforms_label(platforms: list[str]) -> str:
    return "、".join(_platform_label(item) for item in platforms) or "未配置平台"


def _collection_keywords_label(keywords: list[str], limit: int = 3) -> str:
    values = [item for item in keywords if item]
    if not values:
        return "未配置关键词"
    head = "、".join(values[:limit])
    if len(values) > limit:
        return f"{head} 等 {len(values)} 个关键词"
    return head


def _compact_collection_log(message: str | None) -> str:
    text = " ".join(str(message or "").split())
    if len(text) <= COLLECTION_LOG_MAX_LENGTH:
        return text
    return f"{text[: COLLECTION_LOG_MAX_LENGTH - 1]}…"


def _set_collection_latest_log(
    summary: dict[str, Any],
    message: str,
    *,
    stage: str | None = None,
) -> dict[str, Any]:
    compacted = _compact_collection_log(message)
    if stage:
        summary["latest_stage"] = stage
    summary["latest_log"] = compacted
    summary["latest_log_at"] = _now_utc().isoformat()
    return summary


def _initial_collection_summary(tracker: dict[str, Any]) -> dict[str, Any]:
    summary = {"tracker_name": tracker.get("name")}
    return _set_collection_latest_log(summary, "任务已创建，等待开始采集", stage="queued")


async def _ensure_growth_project_exists(
    repository: ResearchRepository,
    project_id: int | None,
) -> dict[str, Any] | None:
    if project_id is None:
        return None
    project = await repository.get_growth_project_record(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    return project


def _resolve_realtime_platforms(platforms: list[str]) -> list[str]:
    selected = [item for item in platforms if item]
    if not selected:
        return ["xhs", "dy"]

    unsupported = sorted(set(selected) - REALTIME_CONTENT_PLATFORMS)
    if unsupported:
        raise HTTPException(
            status_code=400,
            detail="实时搜索暂只支持小红书和抖音",
        )
    return selected


def _content_realtime_comment_policy(
    request: SimilarContentSearchRequest,
    platforms: list[str],
) -> dict[str, Any]:
    total_limit = max(1, int(request.limit or 50))
    per_platform_limit = max(1, ceil(total_limit / max(1, len(platforms))))
    return {
        "enable_comments": False,
        "enable_sub_comments": False,
        "max_posts_per_job": per_platform_limit,
        "content_tracking_total_limit": total_limit,
        "prefer_latest_posts": request.prefer_latest_posts,
    }


def _realtime_collection_window(collection_window_days: int = DEFAULT_REALTIME_COLLECTION_WINDOW_DAYS) -> tuple[date, date]:
    end_date = date.today()
    days = max(1, min(30, int(collection_window_days or DEFAULT_REALTIME_COLLECTION_WINDOW_DAYS)))
    start_date = end_date - timedelta(days=days - 1)
    return start_date, end_date


class ContentTrackingRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    vertical_id: int | None = Field(default=None, ge=1)
    platform: str | None = None
    limit: int = Field(default=30, ge=1, le=100)


class TrackerKeywordSuggestionRequest(BaseModel):
    name: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=1000)
    platforms: list[str] = Field(default_factory=list)
    included_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_tracker_collection_platforms(
    tracker: dict[str, Any],
    requested: list[str] | None,
) -> list[str]:
    selected = [item for item in (requested or tracker.get("platforms") or []) if item]
    if not selected:
        selected = list(DEFAULT_TRACKER_COLLECTION_PLATFORMS)
    return list(dict.fromkeys(selected))


def _build_tracker_collection_comment_policy(
    tracker: dict[str, Any],
    *,
    platform_count: int,
    limit_per_platform: int,
) -> dict[str, Any]:
    policy = dict(tracker.get("comment_policy") or {})
    policy["max_posts_per_job"] = max(1, int(limit_per_platform))
    policy["content_tracking_total_limit"] = max(1, int(limit_per_platform)) * max(1, int(platform_count))
    return policy


def _tracker_analysis_input_summary(
    tracker: dict[str, Any],
    *,
    post_pool_size: int | None = None,
    window_days: int | None = None,
) -> dict[str, Any]:
    summary = {
        "platforms": sorted(item for item in (tracker.get("platforms") or []) if item),
        "included_keywords": [item for item in (tracker.get("included_keywords") or []) if item],
        "excluded_keywords": [item for item in (tracker.get("excluded_keywords") or []) if item],
    }
    if window_days is not None:
        summary["window_days"] = int(window_days)
    if post_pool_size is not None:
        summary["post_pool_size"] = int(post_pool_size)
    return summary


def _build_tracker_analysis_progress(stage: str, message: str) -> dict[str, Any]:
    label, percent = TRACKER_ANALYSIS_PROGRESS_STEPS.get(
        stage,
        (stage or "分析中", 0),
    )
    return {
        "stage": stage,
        "label": label,
        "percent": percent,
        "message": message,
        "updated_at": _now_utc().isoformat(),
    }


async def _update_tracker_analysis_progress(
    repository: ResearchRepository,
    run_id: int,
    *,
    status: str,
    stage: str,
    message: str,
    input_summary: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
    error_message: str | None = None,
    completed_at: datetime | None = None,
) -> dict[str, Any] | None:
    next_summary = dict(summary or {})
    next_summary["progress"] = _build_tracker_analysis_progress(stage, message)
    payload: dict[str, Any] = {
        "status": status,
        "summary": next_summary,
    }
    if input_summary is not None:
        payload["input_summary"] = input_summary
    if error_message is not None:
        payload["error_message"] = error_message
    if completed_at is not None:
        payload["completed_at"] = completed_at
    return await repository.update_content_tracker_analysis_run(run_id, payload)


async def _create_tracker_analysis_run_record(
    repository: ResearchRepository,
    tracker: dict[str, Any],
    *,
    analysis_version: str = "v1",
    window_days: int = 7,
    queued_message: str = "已创建分析任务，等待后台开始执行。",
) -> tuple[dict[str, Any], dict[str, Any]]:
    run = await repository.create_content_tracker_analysis_run(
        {
            "tracker_id": tracker["id"],
            "status": "queued",
            "analysis_version": analysis_version,
            "window_days": window_days,
            "started_at": _now_utc(),
            "input_summary": _tracker_analysis_input_summary(
                tracker,
                window_days=window_days,
            ),
            "summary": {
                "progress": _build_tracker_analysis_progress("queued", queued_message),
            },
        }
    )
    tracker_with_run = await repository.set_content_tracker_latest_run(
        tracker_id=tracker["id"],
        run_id=run["id"],
    )
    return run, tracker_with_run or tracker


async def _get_active_tracker_analysis_run(
    repository: ResearchRepository,
    tracker: dict[str, Any],
) -> dict[str, Any] | None:
    run_id = tracker.get("latest_analysis_run_id")
    if not run_id:
        return None
    run = await repository.get_content_tracker_analysis_run(int(run_id))
    if run is None:
        return None
    if int(run.get("tracker_id") or 0) != int(tracker["id"]):
        return None
    status = str(run.get("status") or "").strip().lower()
    if status not in TRACKER_ANALYSIS_ACTIVE_STATUSES:
        return None
    return run


async def _persist_tracker_analysis_snapshot(
    repository: ResearchRepository,
    tracker: dict[str, Any],
    *,
    existing_run_id: int | None = None,
    analysis_version: str = "v1",
    window_days: int = 7,
) -> dict[str, Any]:
    run = None
    if existing_run_id is None:
        run, tracker = await _create_tracker_analysis_run_record(
            repository,
            tracker,
            analysis_version=analysis_version,
            window_days=window_days,
            queued_message="分析任务已创建，准备读取内容池。",
        )
        existing_run_id = int(run["id"])
    else:
        run = await repository.get_content_tracker_analysis_run(existing_run_id)
        if run is None:
            raise RuntimeError("Tracker analysis run not found")

    await _update_tracker_analysis_progress(
        repository,
        existing_run_id,
        status="running",
        stage="loading_posts",
        message="正在读取最新内容池。",
        input_summary=_tracker_analysis_input_summary(
            tracker,
            window_days=window_days,
        ),
    )
    posts = await repository.list_all_posts(limit=2000)
    await _update_tracker_analysis_progress(
        repository,
        existing_run_id,
        status="running",
        stage="scoring_candidates",
        message=f"已读取 {len(posts)} 条内容，正在筛选候选样本。",
        input_summary=_tracker_analysis_input_summary(
            tracker,
            window_days=window_days,
            post_pool_size=len(posts),
        ),
    )
    analysis_bundle = build_tracker_analysis_snapshot(
        tracker=tracker,
        posts=posts,
        analysis_version=analysis_version,
        window_days=window_days,
    )
    candidate_rows = analysis_bundle.get("candidate_rows") or []
    await _update_tracker_analysis_progress(
        repository,
        existing_run_id,
        status="running",
        stage="refining_samples",
        message=f"已筛出 {len(candidate_rows)} 条候选内容，正在优化分析结果。",
        input_summary=_tracker_analysis_input_summary(
            tracker,
            window_days=window_days,
            post_pool_size=len(posts),
        ),
        summary=analysis_bundle["run"].get("summary") or {},
    )
    analysis_bundle = await _maybe_refine_tracker_samples_with_ai(
        repository=repository,
        tracker=tracker,
        analysis_bundle=analysis_bundle,
    )
    await _update_tracker_analysis_progress(
        repository,
        existing_run_id,
        status="running",
        stage="saving_results",
        message="正在写入分析快照与候选样本。",
        input_summary=analysis_bundle["run"].get("input_summary") or {},
        summary=analysis_bundle["run"].get("summary") or {},
    )
    try:
        await repository.replace_content_tracker_candidate_samples(
            run_id=existing_run_id,
            tracker_id=tracker["id"],
            candidates=analysis_bundle["candidate_rows"],
        )
        snapshot = await repository.create_content_tracker_analysis_snapshot(
            {
                "tracker_id": tracker["id"],
                "run_id": existing_run_id,
                "snapshot_date": date.today(),
                "status": "ready",
                "overview": analysis_bundle["overview"],
                "trends": analysis_bundle["trends"],
                "keywords": analysis_bundle["keywords"],
                "patterns": analysis_bundle["patterns"],
                "creators": analysis_bundle["creators"],
                "samples": analysis_bundle["samples"],
                "risks": analysis_bundle["risks"],
                "decisions": analysis_bundle["decisions"],
                "meta": analysis_bundle["meta"],
            }
        )
        legacy_snapshot = await repository.create_content_tracking_snapshot(
            analysis_bundle["legacy_snapshot"]
        )
        tracker = await repository.set_content_tracker_latest_analysis(
            tracker_id=tracker["id"],
            run_id=existing_run_id,
            snapshot_id=snapshot["id"],
        )
        final_summary = dict(analysis_bundle["run"].get("summary") or {})
        final_summary["progress"] = _build_tracker_analysis_progress(
            "completed",
            "本次分析已完成，结果已刷新。",
        )
        run = await repository.update_content_tracker_analysis_run(
            existing_run_id,
            {
                **analysis_bundle["run"],
                "status": "completed",
                "completed_at": _now_utc(),
                "summary": final_summary,
            },
        )
    except Exception as exc:
        run = await _update_tracker_analysis_progress(
            repository,
            existing_run_id,
            status="failed",
            stage="failed",
            message=f"分析失败：{exc}",
            error_message=str(exc),
            completed_at=_now_utc(),
        )
        raise
    return {
        "tracker": tracker or analysis_bundle["tracker"],
        "overview": analysis_bundle["overview"],
        "trends": analysis_bundle["trends"],
        "keywords": analysis_bundle["keywords"],
        "patterns": analysis_bundle["patterns"],
        "creators": analysis_bundle["creators"],
        "samples": analysis_bundle["samples"],
        "risks": analysis_bundle["risks"],
        "decisions": analysis_bundle["decisions"],
        "meta": analysis_bundle["meta"],
        "run": run or await repository.get_content_tracker_analysis_run(existing_run_id),
        "snapshot": snapshot,
        "legacy_snapshot": legacy_snapshot,
        "legacy_analysis": analysis_bundle["legacy_analysis"],
    }


async def _maybe_refine_tracker_samples_with_ai(
    *,
    repository: ResearchRepository,
    tracker: dict[str, Any],
    analysis_bundle: dict[str, Any],
) -> dict[str, Any]:
    candidates = analysis_bundle.get("candidate_rows") or []
    if not candidates:
        mark_tracker_sample_selection(
            analysis_bundle,
            source="local_ranker",
            reason="no_current_candidates",
        )
        return analysis_bundle

    try:
        provider_config = await _resolve_content_ai_provider(
            repository,
            provider_config_id=None,
        )
    except Exception as exc:
        mark_tracker_sample_selection(
            analysis_bundle,
            source="local_ranker",
            reason="ai_provider_unavailable",
            error=str(exc),
        )
        return analysis_bundle

    try:
        provider = OpenAICompatibleProvider(
            base_url=provider_config["base_url"],
            api_key=provider_config["api_key"],
            model=provider_config["model"],
            timeout=provider_config.get("timeout") or 60,
        )
        raw_output = await provider.complete_json(
            prompt=build_tracker_ai_enhancement_prompt(
                analysis_bundle=analysis_bundle,
                candidates=candidates,
                candidate_limit=80,
            ),
            params={
                "temperature": 0.1,
                "max_tokens": 2600,
                **(provider_config.get("default_params") or {}),
            },
        )
        allowed_keys = {
            f"{item.get('platform')}:{item.get('platform_post_id')}"
            for item in candidates
            if item.get("platform") and item.get("platform_post_id")
        }
        enhancement = normalize_tracker_ai_enhancement_output(
            raw_output,
            allowed_sample_keys=allowed_keys,
        )
        selection = enhancement.get("sample_selection") or {}
        if not any(selection.values()):
            mark_tracker_sample_selection(
                analysis_bundle,
                source="local_ranker",
                reason="ai_returned_no_valid_samples",
                provider=provider_config,
            )
        return apply_tracker_ai_enhancement(
            analysis_bundle,
            enhancement,
            source="ai_gateway",
            provider=provider_config,
        )
    except Exception as exc:
        mark_tracker_sample_selection(
            analysis_bundle,
            source="local_ranker",
            reason="ai_selection_failed",
            provider=provider_config,
            error=str(exc),
        )
        return analysis_bundle


async def _run_tracker_analysis_task(
    tracker_id: int,
    run_id: int,
    *,
    analysis_version: str = "v1",
    window_days: int = 7,
) -> None:
    repository = ResearchRepository()
    try:
        tracker = await repository.get_content_tracker(tracker_id)
        if tracker is None:
            raise RuntimeError("Content tracker not found")
        await _persist_tracker_analysis_snapshot(
            repository,
            tracker,
            existing_run_id=run_id,
            analysis_version=analysis_version,
            window_days=window_days,
        )
    except Exception as exc:
        try:
            await _update_tracker_analysis_progress(
                repository,
                run_id,
                status="failed",
                stage="failed",
                message=f"分析失败：{exc}",
                error_message=str(exc),
                completed_at=_now_utc(),
            )
        except Exception:
            pass


async def _execute_tracker_collection_job(job_id: int) -> dict[str, Any]:
    execution = await schedule_and_execute_research_job(
        job_id,
        background=False,
        force_schedule=True,
    )
    job = await ResearchRepository().get_job(job_id)
    return {
        "execution": execution,
        "job": job,
    }


def _format_collection_event_log(event: dict[str, Any] | None) -> str | None:
    if not event:
        return None
    event_type = str(event.get("event_type") or "")
    platform = _platform_label(event.get("platform"))
    stats = event.get("stats_json") or {}
    if not isinstance(stats, dict):
        stats = {}

    if event_type == "execution_started":
        return "采集任务已启动，正在调度平台采集"
    if event_type == "crawler_started":
        return f"正在采集{platform}：已启动搜索"
    if event_type == "crawler_heartbeat":
        sample_counts = stats.get("sample_counts") or {}
        if not isinstance(sample_counts, dict):
            sample_counts = {}
        parts = [f"正在采集{platform}"]
        elapsed_seconds = stats.get("elapsed_seconds")
        if elapsed_seconds is not None:
            parts.append(f"已运行 {int(elapsed_seconds)} 秒")
        posts = int(sample_counts.get("posts") or 0)
        comments = int(sample_counts.get("comments") or 0)
        raw_records = int(sample_counts.get("raw_records") or 0)
        if posts or comments or raw_records:
            parts.append(f"已入库 {posts} 条内容")
        latest_log = _compact_collection_log(stats.get("latest_log"))
        if latest_log:
            parts.append(f"最新输出：{latest_log}")
        return "，".join(parts)
    if event_type == "crawler_finished":
        return f"{platform}采集完成，正在入库和整理"
    if event_type == "backfill_completed":
        posts = int(stats.get("posts") or stats.get("post_count") or 0)
        return f"{platform}入库完成{f'，新增 {posts} 条内容' if posts else ''}"
    if event_type == "post_crawl_analysis_completed":
        return f"{platform}采集后处理完成"
    if event_type == "execution_completed":
        return "平台采集完成，准备刷新分析结果"
    if event_type == "execution_completed_with_platform_failures":
        return "部分平台采集完成，存在平台失败，准备刷新可用结果"
    if event_type in {"platform_execution_failed", "execution_failed"}:
        message = _compact_collection_log(event.get("message"))
        return f"采集失败：{message}" if message else "采集失败"
    message = _compact_collection_log(event.get("message"))
    return message or None


async def _refresh_collection_job_progress(
    repository: ResearchRepository,
    collection_run_id: int,
    job_id: int,
    summary: dict[str, Any],
) -> None:
    events = await repository.list_events(job_id=job_id, limit=1)
    message = _format_collection_event_log(events[0] if events else None)
    if not message or message == summary.get("latest_log"):
        return
    _set_collection_latest_log(summary, message, stage="collecting")
    try:
        summary["job_stats"] = await repository.get_job_stats(job_id)
    except Exception:
        pass
    await repository.update_collection_run(
        collection_run_id,
        {
            "phase": "collecting",
            "summary": summary,
        },
    )


async def _execute_tracker_collection_job_with_progress(
    repository: ResearchRepository,
    collection_run_id: int,
    job_id: int,
    summary: dict[str, Any],
) -> dict[str, Any]:
    execution_task = asyncio.create_task(_execute_tracker_collection_job(job_id))
    try:
        while True:
            done, _ = await asyncio.wait(
                {execution_task},
                timeout=COLLECTION_PROGRESS_POLL_SECONDS,
            )
            try:
                await _refresh_collection_job_progress(
                    repository,
                    collection_run_id,
                    job_id,
                    summary,
                )
            except Exception:
                pass
            if done:
                return await execution_task
    except Exception:
        if not execution_task.done():
            execution_task.cancel()
        try:
            await _refresh_collection_job_progress(
                repository,
                collection_run_id,
                job_id,
                summary,
            )
        except Exception:
            pass
        raise


async def _run_tracker_collection_task(
    collection_run_id: int,
    tracker_id: int,
    request: ContentTrackerCollectionRequest,
    *,
    analyze_after: bool,
) -> None:
    repository = ResearchRepository()
    summary: dict[str, Any] = {}
    try:
        tracker = await repository.get_content_tracker(tracker_id)
        if tracker is None:
            _set_collection_latest_log(
                summary,
                "采集任务失败：Content tracker not found",
                stage="failed",
            )
            await repository.update_collection_run(
                collection_run_id,
                {
                    "status": "failed",
                    "phase": "failed",
                    "completed_at": _now_utc(),
                    "summary": summary,
                    "error": {"message": "Content tracker not found"},
                },
            )
            return

        summary = _initial_collection_summary(tracker)
        _set_collection_latest_log(summary, "正在准备采集配置", stage="preparing")
        await repository.update_collection_run(
            collection_run_id,
            {
                "status": "running",
                "phase": "preparing",
                "started_at": _now_utc(),
                "summary": summary,
            },
        )
        platforms = _resolve_tracker_collection_platforms(tracker, request.platforms)
        keywords = (
            list(request.keywords)
            if request.keywords is not None
            else list(tracker.get("included_keywords") or [])
        )
        summary.update(
            {
                "platforms": platforms,
                "keywords": keywords,
                "lookback_days": request.lookback_days,
                "limit_per_platform": request.limit_per_platform,
            }
        )
        _set_collection_latest_log(
            summary,
            (
                f"正在准备采集：{_collection_platforms_label(platforms)} / "
                f"关键词 {_collection_keywords_label(keywords)}"
            ),
            stage="preparing",
        )
        if not keywords:
            _set_collection_latest_log(summary, "采集任务失败：至少需要一个搜索关键词", stage="failed")
            await repository.update_collection_run(
                collection_run_id,
                {
                    "status": "failed",
                    "phase": "failed",
                    "completed_at": _now_utc(),
                    "summary": summary,
                    "error": {"message": "采集任务需要至少一个搜索关键词"},
                },
            )
            return
        end_date = date.today()
        start_date = end_date - timedelta(days=max(1, int(request.lookback_days)) - 1)
        job = await repository.create_job(
            {
                "name": f"tracker collect - {tracker['name']}",
                "topic": f"content_tracker:{tracker_id}",
                "platforms": platforms,
                "collection_mode": "search",
                "keywords": keywords,
                "target_ids": [],
                "creator_ids": [],
                "start_date": start_date,
                "end_date": end_date,
                "status": "pending",
                "comment_policy": _build_tracker_collection_comment_policy(
                    tracker,
                    platform_count=len(platforms),
                    limit_per_platform=request.limit_per_platform,
                ),
                "raw_record_mode": "minimal",
                "anonymize_authors": True,
            }
        )
        summary["job_id"] = job["id"]
        _set_collection_latest_log(
            summary,
            (
                f"正在采集{_collection_platforms_label(platforms)}："
                f"关键词 {_collection_keywords_label(keywords)}，"
                f"单平台上限 {request.limit_per_platform} 条"
            ),
            stage="collecting",
        )
        await repository.update_collection_run(
            collection_run_id,
            {
                "phase": "collecting",
                "job_id": job["id"],
                "summary": summary,
            },
        )
        execution_result = await _execute_tracker_collection_job_with_progress(
            repository,
            collection_run_id,
            job["id"],
            summary,
        )
        collected_posts = await repository.list_all_posts(
            job_id=job["id"],
            limit=max(1, request.limit_per_platform * max(1, len(platforms)) * 2),
        )
        summary.update(
            {
                "platforms": platforms,
                "job_id": job["id"],
                "job_status": (execution_result.get("job") or {}).get("status"),
                "collected_post_count": len(collected_posts),
                "keywords": keywords,
                "lookback_days": request.lookback_days,
                "limit_per_platform": request.limit_per_platform,
            }
        )
        _set_collection_latest_log(
            summary,
            (
                f"采集完成 {len(collected_posts)} 条，正在刷新分析结果"
                if analyze_after
                else f"采集完成 {len(collected_posts)} 条"
            ),
            stage="analyzing" if analyze_after else "completed",
        )
        update_payload: dict[str, Any] = {
            "status": "succeeded",
            "phase": "completed",
            "completed_at": _now_utc(),
            "summary": summary,
            "error": {},
        }
        if analyze_after:
            await repository.update_collection_run(
                collection_run_id,
                {
                    "phase": "analyzing",
                    "summary": summary,
                },
            )
            analysis_result = await _persist_tracker_analysis_snapshot(repository, tracker)
            summary["analysis_run_id"] = analysis_result["run"]["id"]
            summary["analysis_snapshot_id"] = analysis_result["snapshot"]["id"]
            summary["analysis_status"] = analysis_result["run"]["status"]
            _set_collection_latest_log(
                summary,
                f"采集完成 {len(collected_posts)} 条，分析已更新",
                stage="completed",
            )
            update_payload["analysis_run_id"] = analysis_result["run"]["id"]
        await repository.update_collection_run(collection_run_id, update_payload)
    except Exception as exc:
        _set_collection_latest_log(
            summary,
            f"采集任务失败：{str(exc)}",
            stage="failed",
        )
        await repository.update_collection_run(
            collection_run_id,
            {
                "status": "failed",
                "phase": "failed",
                "completed_at": _now_utc(),
                "summary": summary,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            },
        )


@router.post("/analyze")
async def analyze_tracked_content(request: ContentTrackingRequest):
    require_research_database()
    repository = ResearchRepository()
    posts = await repository.list_all_posts(platform=request.platform, limit=500)
    comments = await repository.list_all_comments(platform=request.platform, limit=500)
    tags = await repository.list_entity_tags(
        vertical_id=request.vertical_id,
        platform=request.platform,
    )
    tag_definitions = await repository.list_tag_definitions(
        vertical_id=request.vertical_id,
        enabled_only=True,
    )
    result = analyze_content_tracking(
        query=request.query,
        posts=posts,
        comments=comments,
        entity_tags=tags,
        tag_definitions=tag_definitions,
        limit=request.limit,
    )
    result["fingerprints"] = analyze_posts_for_tracking(result.get("content") or [])
    return result


@router.post("/extract-keywords")
async def extract_keywords(request: ContentKeywordExtractionRequest):
    require_research_database()
    repository = ResearchRepository()
    text = " ".join([request.title or "", request.text])
    if request.use_ai:
        try:
            provider_config = await _resolve_content_ai_provider(
                repository,
                provider_config_id=request.provider_config_id,
            )
            provider = OpenAICompatibleProvider(
                base_url=provider_config["base_url"],
                api_key=provider_config["api_key"],
                model=provider_config["model"],
                timeout=provider_config.get("timeout") or 60,
            )
            raw_output = await provider.complete_json(
                prompt=build_content_keyword_ai_prompt(
                    title=request.title,
                    text=request.text,
                    platform=request.platform,
                ),
                params={
                    "temperature": 0.15,
                    "max_tokens": 1200,
                    **(provider_config.get("default_params") or {}),
                },
            )
            keywords = normalize_content_keyword_ai_output(raw_output)
            if keywords:
                return {
                    "keywords": keywords,
                    "source": "ai",
                    "provider": {
                        "name": provider_config.get("name") or "AI Gateway",
                        "model": provider_config["model"],
                    },
                }
        except Exception as exc:
            fallback_reason = str(exc)
        else:
            fallback_reason = "AI returned no keywords"

    scene_keywords = await repository.list_scene_pack_keywords(
        scene_pack_ids=request.scene_pack_ids or None,
        enabled_only=True,
    )
    keywords = extract_content_keywords(
        text=text,
        scene_keywords=scene_keywords,
    )
    return {
        "keywords": keywords,
        "source": "local_fallback" if request.use_ai else "local",
        **({"fallback_reason": fallback_reason} if request.use_ai else {}),
    }


@router.post("/tracker-keyword-suggestions")
async def suggest_tracker_keywords(request: TrackerKeywordSuggestionRequest):
    require_research_database()
    repository = ResearchRepository()
    if not request.name.strip() and not request.description.strip() and not request.included_keywords:
        raise HTTPException(
            status_code=400,
            detail="Tracker name, description, or existing keywords are required",
        )
    provider_config = await _resolve_content_ai_provider(
        repository,
        provider_config_id=None,
    )
    provider = OpenAICompatibleProvider(
        base_url=provider_config["base_url"],
        api_key=provider_config["api_key"],
        model=provider_config["model"],
        timeout=provider_config.get("timeout") or 60,
    )
    try:
        raw_output = await provider.complete_json(
            prompt=build_tracker_keyword_suggestion_ai_prompt(
                name=request.name,
                description=request.description,
                platforms=request.platforms,
                included_keywords=request.included_keywords,
                excluded_keywords=request.excluded_keywords,
            ),
            params={
                "temperature": 0.15,
                "max_tokens": 1400,
                **(provider_config.get("default_params") or {}),
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI tracker keyword suggestion failed: {exc}") from exc
    return {
        "suggestions": normalize_tracker_keyword_suggestion_ai_output(raw_output),
        "provider": {
            "name": provider_config.get("name") or "AI Gateway",
            "model": provider_config["model"],
        },
    }


@router.post("/search-similar")
async def search_similar(request: SimilarContentSearchRequest):
    require_research_database()
    if request.realtime:
        return await _search_similar_with_realtime(request)

    repository = ResearchRepository()
    candidates = await _local_similar_candidates(repository, request)
    return {"candidates": candidates}


async def _local_similar_candidates(
    repository: ResearchRepository,
    request: SimilarContentSearchRequest,
    *,
    job_id: int | None = None,
    evidence_source: str | None = None,
) -> list[dict[str, Any]]:
    platform = request.platforms[0] if len(request.platforms) == 1 else None
    list_kwargs: dict[str, Any] = {"platform": platform, "limit": 500}
    if job_id is not None:
        list_kwargs["job_id"] = job_id
    posts = await repository.list_all_posts(**list_kwargs)
    candidates = search_similar_content(
        keywords=request.keywords,
        posts=posts,
        limit=request.limit,
    )
    if evidence_source:
        for candidate in candidates:
            evidence = candidate.setdefault("evidence", {})
            evidence["source"] = evidence_source
    return candidates


async def _search_similar_with_realtime(request: SimilarContentSearchRequest) -> dict[str, Any]:
    realtime_platforms = _resolve_realtime_platforms(request.platforms)
    repository = ResearchRepository()
    start_date, end_date = _realtime_collection_window(request.collection_window_days)
    job = await repository.create_job(
        {
            "name": f"content realtime discovery - {' '.join(request.keywords)}",
            "topic": "content_realtime_discovery",
            "platforms": realtime_platforms,
            "collection_mode": "search",
            "keywords": request.keywords,
            "target_ids": [],
            "creator_ids": [],
            "start_date": start_date,
            "end_date": end_date,
            "status": "pending",
            "comment_policy": _content_realtime_comment_policy(request, realtime_platforms),
            "raw_record_mode": "minimal",
            "anonymize_authors": True,
        }
    )

    execution = await schedule_and_execute_research_job(
        job["id"],
        background=True,
        force_schedule=True,
    )
    if execution.get("status") == "busy":
        raise HTTPException(
            status_code=409,
            detail=execution.get("message") or "A research execution is already running",
        )

    completed_job = await wait_for_research_job_status(job["id"])
    if completed_job is None:
        raise HTTPException(status_code=404, detail="Content discovery job not found")

    candidates = await _local_similar_candidates(
        repository,
        request,
        job_id=job["id"],
        evidence_source="realtime_imported",
    )
    return {
        "realtime": {
            "enabled": True,
            "job_id": job["id"],
            "platforms": realtime_platforms,
            "status": completed_job.get("status"),
            "matched_count": len(candidates),
            "start_date": str(start_date),
            "end_date": str(end_date),
            "errors": [],
        },
        "candidates": candidates,
    }


@router.post("/ai-analysis")
async def analyze_content_with_ai(request: ContentTrackingAIAnalysisRequest):
    require_research_database()
    repository = ResearchRepository()
    provider_config = await _resolve_content_ai_provider(
        repository,
        provider_config_id=request.provider_config_id,
    )
    provider = OpenAICompatibleProvider(
        base_url=provider_config["base_url"],
        api_key=provider_config["api_key"],
        model=provider_config["model"],
        timeout=provider_config.get("timeout") or 60,
    )
    prompt = build_content_tracking_ai_prompt(
        title=request.title,
        text=request.text,
        platform=request.platform,
        keywords=request.keywords,
        candidates=request.candidates,
        comments=request.comments,
    )
    try:
        raw_output = await provider.complete_json(
            prompt=prompt,
            params={
                "temperature": 0.2,
                "max_tokens": 1800,
                **(provider_config.get("default_params") or {}),
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI content analysis failed: {exc}") from exc
    return {
        "provider": {
            "name": provider_config.get("name") or "AI Gateway",
            "model": provider_config["model"],
        },
        "analysis": normalize_content_tracking_ai_output(raw_output),
        "raw": raw_output,
    }


@router.post("/trackers")
async def create_tracker(request: ContentTrackerCreate):
    require_research_database()
    repository = ResearchRepository()
    payload = request.model_dump(mode="python")
    await _ensure_growth_project_exists(repository, payload.get("project_id"))
    tracker = await repository.create_content_tracker(payload)
    return tracker


@router.get("/trackers")
async def list_trackers(
    enabled_only: bool = False,
    project_id: int | None = None,
):
    require_research_database()
    repository = ResearchRepository()
    await _ensure_growth_project_exists(repository, project_id)
    return {
        "trackers": await repository.list_content_trackers(
            enabled_only=enabled_only,
            project_id=project_id,
        )
    }


@router.patch("/trackers/{tracker_id}")
async def update_tracker(tracker_id: int, request: ContentTrackerUpdate):
    require_research_database()
    repository = ResearchRepository()
    payload = request.model_dump(mode="python", exclude_unset=True)
    if "project_id" in payload:
        await _ensure_growth_project_exists(repository, payload.get("project_id"))
    tracker = await repository.update_content_tracker(
        tracker_id,
        payload,
    )
    if tracker is None:
        raise HTTPException(status_code=404, detail="Content tracker not found")
    return tracker


@router.delete("/trackers/{tracker_id}")
async def delete_tracker(tracker_id: int):
    require_research_database()
    repository = ResearchRepository()
    tracker = await repository.update_content_tracker(
        tracker_id,
        {"enabled": False},
    )
    if tracker is None:
        raise HTTPException(status_code=404, detail="Content tracker not found")
    return {
        "status": "disabled",
        "tracker": tracker,
    }


@router.get("/trackers/{tracker_id}/collection-runs")
async def list_tracker_collection_runs(
    tracker_id: int,
    limit: int = 5,
):
    require_research_database()
    repository = ResearchRepository()
    tracker = await repository.get_content_tracker(tracker_id)
    if tracker is None:
        raise HTTPException(status_code=404, detail="Content tracker not found")
    runs = await repository.list_collection_runs(
        target_type="content_tracker",
        target_id=tracker_id,
        run_type="content_tracker",
        limit=max(1, min(limit, 20)),
    )
    return {"tracker": tracker, "runs": runs}


@router.post("/trackers/{tracker_id}/analysis")
async def analyze_tracker(tracker_id: int):
    require_research_database()
    repository = ResearchRepository()
    tracker = await repository.get_content_tracker(tracker_id)
    if tracker is None:
        raise HTTPException(status_code=404, detail="Content tracker not found")
    active_run = await _get_active_tracker_analysis_run(repository, tracker)
    if active_run is not None:
        return {
            "tracker": tracker,
            "run": active_run,
        }
    run, tracker_with_run = await _create_tracker_analysis_run_record(repository, tracker)
    asyncio.create_task(
        _run_tracker_analysis_task(
            tracker["id"],
            run["id"],
        )
    )
    return {
        "tracker": tracker_with_run,
        "run": run,
    }


@router.post("/trackers/{tracker_id}/collect")
async def collect_tracker_content(
    tracker_id: int,
    request: ContentTrackerCollectionRequest,
):
    require_research_database()
    repository = ResearchRepository()
    tracker = await repository.get_content_tracker(tracker_id)
    if tracker is None:
        raise HTTPException(status_code=404, detail="Content tracker not found")
    collection_run = await repository.create_collection_run(
        {
            "run_type": "content_tracker",
            "target_type": "content_tracker",
            "target_id": tracker_id,
            "mode": "collect_only",
            "trigger_source": request.trigger_source,
            "status": "queued",
            "phase": "queued",
            "request_payload": request.model_dump(mode="python"),
            "summary": _initial_collection_summary(tracker),
        }
    )
    asyncio.create_task(
        _run_tracker_collection_task(
            collection_run["id"],
            tracker_id,
            request,
            analyze_after=False,
        )
    )
    return {"tracker": tracker, "run": collection_run}


@router.post("/trackers/{tracker_id}/collect-and-analyze")
async def collect_and_analyze_tracker_content(
    tracker_id: int,
    request: ContentTrackerCollectionRequest,
):
    require_research_database()
    repository = ResearchRepository()
    tracker = await repository.get_content_tracker(tracker_id)
    if tracker is None:
        raise HTTPException(status_code=404, detail="Content tracker not found")
    collection_run = await repository.create_collection_run(
        {
            "run_type": "content_tracker",
            "target_type": "content_tracker",
            "target_id": tracker_id,
            "mode": "collect_and_analyze",
            "trigger_source": request.trigger_source,
            "status": "queued",
            "phase": "queued",
            "request_payload": request.model_dump(mode="python"),
            "summary": _initial_collection_summary(tracker),
        }
    )
    asyncio.create_task(
        _run_tracker_collection_task(
            collection_run["id"],
            tracker_id,
            request,
            analyze_after=True,
        )
    )
    return {"tracker": tracker, "run": collection_run}


async def _enrich_snapshot_sample_metadata(
    repository: ResearchRepository,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    run_id = snapshot.get("run_id")
    if not run_id:
        return snapshot
    candidates = await repository.list_content_tracker_candidate_samples(
        run_id=int(run_id),
        limit=500,
    )
    author_names = {
        (item.get("platform"), item.get("platform_post_id")): item.get("author_name")
        for item in candidates
        if item.get("author_name")
    }
    urls = {
        (item.get("platform"), item.get("platform_post_id")): item.get("url")
        for item in candidates
        if item.get("url")
    }
    if not author_names and not urls:
        return snapshot

    samples = dict(snapshot.get("samples") or {})
    for key in ("representative_samples", "hot_samples", "early_signal_samples", "all_samples"):
        rows = samples.get(key)
        if not isinstance(rows, list):
            continue
        enriched_rows = []
        for row in rows:
            if not isinstance(row, dict):
                enriched_rows.append(row)
                continue
            enriched = dict(row)
            lookup_key = (enriched.get("platform"), enriched.get("platform_post_id"))
            if not enriched.get("author_name") and author_names.get(lookup_key):
                enriched["author_name"] = author_names[lookup_key]
            if not enriched.get("url") and urls.get(lookup_key):
                enriched["url"] = urls[lookup_key]
            enriched_rows.append(enriched)
        samples[key] = enriched_rows

    enriched_snapshot = dict(snapshot)
    enriched_snapshot["samples"] = samples
    return enriched_snapshot


@router.get("/trackers/{tracker_id}/analysis")
async def get_latest_tracker_analysis(tracker_id: int):
    require_research_database()
    repository = ResearchRepository()
    tracker = await repository.get_content_tracker(tracker_id)
    if tracker is None:
        raise HTTPException(status_code=404, detail="Content tracker not found")
    snapshot = await repository.get_latest_content_tracker_analysis_snapshot(tracker_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Tracker analysis snapshot not found")
    run = await repository.get_content_tracker_analysis_run(snapshot["run_id"])
    snapshot = await _enrich_snapshot_sample_metadata(repository, snapshot)
    return {
        "tracker": tracker,
        "run": run,
        "snapshot": snapshot,
    }


@router.get("/trackers/{tracker_id}/analysis/history")
async def get_tracker_analysis_history(tracker_id: int, limit: int = 20):
    require_research_database()
    repository = ResearchRepository()
    tracker = await repository.get_content_tracker(tracker_id)
    if tracker is None:
        raise HTTPException(status_code=404, detail="Content tracker not found")
    return {
        "tracker": tracker,
        "snapshots": await repository.list_content_tracker_analysis_snapshots(
            tracker_id=tracker_id,
            limit=max(1, min(limit, 100)),
        ),
    }


@router.get("/analysis-runs/{run_id}")
async def get_tracker_analysis_run(run_id: int):
    require_research_database()
    repository = ResearchRepository()
    run = await repository.get_content_tracker_analysis_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Tracker analysis run not found")
    candidates = await repository.list_content_tracker_candidate_samples(run_id=run_id, limit=50)
    return {
        "run": run,
        "candidates": candidates,
    }


@router.get("/collection-runs/{run_id}")
async def get_tracker_collection_run(run_id: int):
    require_research_database()
    repository = ResearchRepository()
    run = await repository.get_collection_run(run_id)
    if run is None or run.get("target_type") != "content_tracker":
        raise HTTPException(status_code=404, detail="Collection run not found")
    tracker = await repository.get_content_tracker(int(run["target_id"]))
    return {"run": run, "tracker": tracker}


@router.post("/realtime-discovery")
async def start_realtime_content_discovery(request: SimilarContentSearchRequest):
    require_research_database()
    if not request.realtime:
        return {"status": "skipped", "reason": "realtime search switch is off"}
    realtime_platforms = _resolve_realtime_platforms(request.platforms)
    repository = ResearchRepository()
    start_date, end_date = _realtime_collection_window(request.collection_window_days)
    job = await repository.create_job(
        {
            "name": f"content realtime discovery - {' '.join(request.keywords)}",
            "topic": "content_realtime_discovery",
            "platforms": realtime_platforms,
            "collection_mode": "search",
            "keywords": request.keywords,
            "target_ids": [],
            "creator_ids": [],
            "start_date": start_date,
            "end_date": end_date,
            "status": "pending",
            "comment_policy": _content_realtime_comment_policy(request, realtime_platforms),
            "raw_record_mode": "minimal",
            "anonymize_authors": True,
        }
    )
    execution = await schedule_and_execute_research_job(
        job["id"],
        background=True,
        force_schedule=True,
    )
    if execution.get("status") == "busy":
        await repository.update_job(job["id"], {"status": JOB_CANCELLED})
        return {
            "status": "busy",
            "job_id": None,
            "busy_job_id": execution.get("job_id"),
            "message": execution.get("message") or "A research execution is already running",
            "execution": execution,
        }
    return {
        "status": execution["status"],
        "job_id": job["id"],
        "execution": execution,
        "start_date": str(start_date),
        "end_date": str(end_date),
    }


@router.post("/realtime-jobs/{job_id}/cancel")
async def cancel_realtime_content_discovery(job_id: int):
    require_research_database()
    repository = ResearchRepository()
    job = await repository.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Content discovery job not found")
    if job.get("topic") != "content_realtime_discovery":
        raise HTTPException(status_code=400, detail="Only content tracking realtime jobs can be cancelled here")

    active = await cancel_active_research_execution_job(job_id)
    if active["status"] == "stopping":
        return {
            "status": "stopping",
            "job_id": job_id,
            "crawler_stopped": active.get("crawler_stopped", False),
        }

    updated = await repository.update_job(job_id, {"status": JOB_CANCELLED})
    return {
        "status": "cancelled",
        "job_id": job_id,
        "job": updated,
        "crawler_stopped": False,
    }


@router.get("/discovery/{job_id}/status")
async def get_content_discovery_status(job_id: int):
    require_research_database()
    job = await ResearchRepository().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Content discovery job not found")
    return {"job_id": job_id, "status": job["status"]}


@router.post("/discovery/{job_id}/wait-refresh")
async def wait_content_discovery_and_refresh(job_id: int):
    require_research_database()
    job = await wait_for_research_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Content discovery job not found")
    repository = ResearchRepository()
    total_limit = int((job.get("comment_policy") or {}).get("content_tracking_total_limit") or 50)
    posts = await repository.list_all_posts(job_id=job_id, limit=max(1, total_limit))
    candidates = search_similar_content(keywords=job.get("keywords") or [], posts=posts, limit=max(1, total_limit))
    return {
        "job_id": job_id,
        "status": job["status"],
        "start_date": str(job["start_date"]),
        "end_date": str(job["end_date"]),
        "refreshed": True,
        "candidates": candidates,
    }


async def _resolve_content_ai_provider(
    repository: ResearchRepository,
    *,
    provider_config_id: int | None,
) -> dict[str, Any]:
    if provider_config_id:
        provider = await repository.get_ai_provider(provider_config_id, include_secret=True)
        if provider is None:
            raise HTTPException(status_code=404, detail="AI provider config not found")
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
