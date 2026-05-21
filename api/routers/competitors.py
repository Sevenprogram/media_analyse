import asyncio
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import config
from api.schemas import SaveDataOptionEnum
from api.routers.research import require_research_database
from research.competitors import CompetitorService, build_competitor_composition_snapshot
from research.competitor_public_flow import (
    DEFAULT_LATEST_LIMIT,
    DEFAULT_MONITOR_INTERVAL_MINUTES,
    build_competitor_public_flow_snapshot,
    create_competitor_fetch_now_job,
    create_competitor_monitor_jobs,
)
from research.competitor_recommendations import recommend_suspected_competitors
from research.enums import CRAWL_UNIT_SUCCEEDED
from research.repository import ResearchRepository
from research.scheduler import ResearchScheduler
from research.worker import run_worker_once
from research.schemas import CompetitorAccountCreate, CompetitorAccountUpdate
from research.tikhub_creator_metrics import enrich_creator_metrics_from_tikhub

router = APIRouter(prefix="/competitors", tags=["competitors"])
_fetch_now_tasks: dict[str, dict] = {}


class CompetitorCompositionRequest(BaseModel):
    snapshot_date: str
    platform: str
    posts: list[dict] = Field(default_factory=list)
    entity_tags: list[dict] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class CompetitorCompositionRebuildRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    snapshot_date: str | None = None


class CompetitorPublicFlowRebuildRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    snapshot_date: str | None = None
    latest_limit: int = Field(default=DEFAULT_LATEST_LIMIT, ge=1, le=200)


class CompetitorMonitorSyncRequest(BaseModel):
    interval_minutes: int = Field(default=DEFAULT_MONITOR_INTERVAL_MINUTES, ge=30)
    latest_limit: int = Field(default=DEFAULT_LATEST_LIMIT, ge=1, le=200)


class CompetitorFetchNowRequest(BaseModel):
    latest_limit: int = Field(default=DEFAULT_LATEST_LIMIT, ge=1, le=200)
    days_back: int | None = Field(default=7, ge=1, le=365)
    max_attempts: int = Field(default=4, ge=1, le=10)
    execute_now: bool = True
    headless: bool = True


class CompetitorFromUrlRequest(BaseModel):
    platform: str
    profile_url: str
    display_name: str | None = None
    vertical_id: int | None = Field(default=None, ge=1)
    notes: str | None = None


class CompetitorFromCandidateRequest(BaseModel):
    platform: str
    creator_id: str = Field(min_length=1)
    display_name: str | None = None
    profile_url: str | None = None
    vertical_id: int | None = Field(default=None, ge=1)
    notes: str | None = None


@router.post("")
async def create_competitor_account(request: CompetitorAccountCreate):
    require_research_database()
    repository = ResearchRepository()
    try:
        return await CompetitorService(repository).create_competitor(
            await _payload_with_display_name(repository, request.model_dump(mode="python"))
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/from-url")
async def create_competitor_from_url(request: CompetitorFromUrlRequest):
    require_research_database()
    repository = ResearchRepository()
    creator_id = _creator_id_from_profile_url(request.platform, request.profile_url)
    if not creator_id:
        raise HTTPException(status_code=400, detail="Unable to parse creator id from profile_url")
    try:
        payload = await _payload_with_display_name(
            repository,
            {
                "platform": request.platform,
                "creator_id": creator_id,
                "display_name": request.display_name,
                "profile_url": request.profile_url,
                "vertical_id": request.vertical_id,
                "enabled": True,
                "notes": request.notes,
            },
        )
        return await CompetitorService(repository).create_competitor(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/from-candidate")
async def create_competitor_from_candidate(request: CompetitorFromCandidateRequest):
    require_research_database()
    repository = ResearchRepository()
    try:
        payload = await _payload_with_display_name(
            repository,
            {
                "platform": request.platform,
                "creator_id": request.creator_id,
                "display_name": request.display_name,
                "profile_url": request.profile_url,
                "vertical_id": request.vertical_id,
                "enabled": True,
                "notes": request.notes or "suspected_competitor_confirmed",
            },
        )
        return await CompetitorService(repository).create_competitor(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
async def list_competitor_accounts(enabled_only: bool = False):
    require_research_database()
    repository = ResearchRepository()
    competitors = await repository.list_competitor_accounts(enabled_only=enabled_only)
    return {
        "competitors": await _enrich_competitors_with_display_names(repository, competitors)
    }


@router.get("/recommendations")
async def list_suspected_competitor_recommendations(
    platform: str | None = None,
    vertical_id: int | None = None,
    limit: int = 20,
    min_score: float = 65.0,
):
    require_research_database()
    repository = ResearchRepository()
    candidates = await repository.list_creator_candidates(
        platform=platform,
        vertical_id=vertical_id,
    )
    enriched = []
    for candidate in candidates:
        item = dict(candidate)
        if hasattr(repository, "get_creator_profile"):
            profile = await repository.get_creator_profile(candidate["platform"], candidate["creator_id"])
            if profile:
                item.update({key: value for key, value in profile.items() if value not in (None, "")})
        enriched.append(item)
    return {
        "recommendations": recommend_suspected_competitors(
            candidates=enriched,
            existing_competitors=await repository.list_competitor_accounts(enabled_only=False),
            limit=limit,
            min_score=min_score,
        )
    }


@router.get("/public-flow/latest")
async def list_latest_competitor_public_flow_snapshots(limit: int = 50):
    require_research_database()
    return {
        "snapshots": await ResearchRepository().list_competitor_composition_snapshots(
            limit=limit,
        )
    }


@router.patch("/{competitor_id}")
async def update_competitor_account(competitor_id: int, request: CompetitorAccountUpdate):
    require_research_database()
    result = await ResearchRepository().update_competitor_account(
        competitor_id,
        request.model_dump(mode="python", exclude_unset=True),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    return result


@router.post("/{competitor_id}/refresh-profile")
async def refresh_competitor_profile(competitor_id: int):
    require_research_database()
    repository = ResearchRepository()
    competitor = await repository.get_competitor_account(competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    display_name, diagnostics = await _lookup_competitor_display_name_with_diagnostics(repository, competitor)
    if not display_name:
        return {
            "updated": False,
            "competitor": competitor,
            "diagnostics": diagnostics,
            "message": "未获取到昵称。请确认后端进程能读取 TIKHUB_API_KEY，或手动填写昵称。",
        }
    updated = await repository.update_competitor_account(
        competitor_id,
        {"display_name": display_name},
    )
    return {
        "updated": True,
        "competitor": updated or {**competitor, "display_name": display_name},
        "diagnostics": diagnostics,
        "message": f"已更新昵称：{display_name}",
    }


@router.delete("/{competitor_id}")
async def delete_competitor_account(competitor_id: int):
    require_research_database()
    result = await ResearchRepository().update_competitor_account(
        competitor_id,
        {"enabled": False},
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    return {"deleted": True, "competitor": result}


@router.get("/{competitor_id}/daily-snapshots")
async def list_competitor_daily_snapshots(competitor_id: int):
    require_research_database()
    return {
        "snapshots": await ResearchRepository().list_competitor_snapshots(competitor_id)
    }


@router.get("/{competitor_id}/composition")
async def list_competitor_composition_snapshots(competitor_id: int):
    require_research_database()
    return {
        "snapshots": await ResearchRepository().list_competitor_composition_snapshots(
            competitor_id=competitor_id,
            limit=50,
        )
    }


@router.post("/monitor-jobs/sync")
async def sync_competitor_monitor_jobs(request: CompetitorMonitorSyncRequest):
    require_research_database()
    return await create_competitor_monitor_jobs(
        ResearchRepository(),
        interval_minutes=request.interval_minutes,
        latest_limit=request.latest_limit,
    )


@router.get("/fetch-tasks")
async def list_fetch_now_tasks(limit: int = 20):
    tasks = sorted(
        _fetch_now_tasks.values(),
        key=lambda task: task.get("started_at") or "",
        reverse=True,
    )
    return {"tasks": tasks[: max(1, min(limit, 100))]}


@router.get("/fetch-tasks/{task_id}")
async def get_fetch_now_task(task_id: str):
    task = _fetch_now_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Fetch task not found")
    return task


@router.post("/{competitor_id}/fetch-now")
async def fetch_competitor_now(competitor_id: int, request: CompetitorFetchNowRequest):
    require_research_database()
    if request.execute_now:
        task = _create_fetch_now_task(competitor_id)
        asyncio.create_task(_run_fetch_now_task(task["task_id"], competitor_id, request))
        return task
    return await _run_fetch_now_inline(competitor_id, request)


def _create_fetch_now_task(competitor_id: int) -> dict:
    task_id = uuid4().hex
    task = {
        "task_id": task_id,
        "competitor_id": competitor_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "message": "已创建即时采集任务，等待后端执行。",
        "logs": [],
        "result": None,
        "error": None,
        "started_at": _now_iso(),
        "finished_at": None,
    }
    _fetch_now_tasks[task_id] = task
    _trim_fetch_now_tasks()
    return task


async def _run_fetch_now_task(task_id: str, competitor_id: int, request: CompetitorFetchNowRequest) -> None:
    try:
        result = await _run_fetch_now_inline(
            competitor_id,
            request,
            progress=lambda stage, progress, message: _update_fetch_task(task_id, stage, progress, message),
        )
        _finish_fetch_task(task_id, result)
    except Exception as exc:
        _fail_fetch_task(task_id, exc)


async def _run_fetch_now_inline(
    competitor_id: int,
    request: CompetitorFetchNowRequest,
    progress=None,
) -> dict:
    repository = ResearchRepository()
    _emit_progress(progress, "loading_competitor", 5, "正在读取友商账号。")
    competitor = await repository.get_competitor_account(competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    _emit_progress(progress, "profile", 10, "正在补全账号昵称。")
    competitor = await _ensure_competitor_display_name(repository, competitor)
    _emit_progress(progress, "creating_job", 18, "正在创建即时采集任务。")
    job = await create_competitor_fetch_now_job(
        repository,
        competitor,
        latest_limit=request.latest_limit,
        days_back=request.days_back,
    )
    _emit_progress(progress, "scheduling", 28, "正在调度采集单元。")
    schedule = await ResearchScheduler(repository).schedule_job(
        job["id"],
        max_attempts=request.max_attempts,
        force=True,
    )
    worker_result = None
    if request.execute_now:
        _emit_progress(progress, "crawling", 40, "正在启动爬虫并采集主页最新内容。")
        worker_result = await run_worker_once(
            worker_id=f"fetch-now-competitor-{competitor_id}",
            save_option=SaveDataOptionEnum(config.SAVE_DATA_OPTION),
            headless=request.headless,
            job_id=job["id"],
        )
        _raise_if_worker_did_not_collect(worker_result)
        _emit_progress(progress, "worker_finished", 78, f"爬虫执行结束：{worker_result.get('status') if isinstance(worker_result, dict) else 'unknown'}。")
    else:
        _emit_progress(progress, "queued", 70, "已排队，等待常驻 worker 执行。")
    _emit_progress(progress, "rebuilding_snapshot", 88, "正在重建公开流量快照。")
    snapshot = await _rebuild_public_flow_snapshot_for_competitor(
        repository,
        competitor_id=competitor_id,
        keywords=[],
        snapshot_date=None,
        latest_limit=request.latest_limit,
        days_back=request.days_back,
    )
    return {
        "competitor": competitor,
        "job": job,
        "schedule": schedule,
        "worker": worker_result,
        "snapshot": snapshot,
        "worker_hint": None
        if request.execute_now
        else "Run scripts/run_ops_monitor.py or keep the ops monitor daemon running to execute the queued crawl unit.",
    }


def _raise_if_worker_did_not_collect(worker_result: dict | None) -> None:
    if not isinstance(worker_result, dict):
        raise RuntimeError("即时采集没有返回 worker 结果，请检查后端 worker 日志。")
    status = worker_result.get("status")
    if status == CRAWL_UNIT_SUCCEEDED:
        return
    if status == "idle":
        raise RuntimeError("即时采集没有领取到采集单元，可能是调度未写入或数据库连接不一致。")
    detail = worker_result.get("error") or worker_result.get("last_error") or "请检查后端 worker 日志。"
    raise RuntimeError(f"即时采集未成功，worker 状态：{status or 'unknown'}，原因：{detail}")


def _emit_progress(progress, stage: str, value: int, message: str) -> None:
    if progress:
        progress(stage, value, message)


def _update_fetch_task(task_id: str, stage: str, progress: int, message: str) -> None:
    task = _fetch_now_tasks.get(task_id)
    if not task:
        return
    task["status"] = "running"
    task["stage"] = stage
    task["progress"] = progress
    task["message"] = message
    task["logs"].append({"time": _now_iso(), "stage": stage, "message": message})
    task["logs"] = task["logs"][-20:]


def _finish_fetch_task(task_id: str, result: dict) -> None:
    task = _fetch_now_tasks.get(task_id)
    if not task:
        return
    snapshot = result.get("snapshot") or {}
    evidence = snapshot.get("evidence") if isinstance(snapshot, dict) else {}
    public_flow = evidence.get("public_flow") if isinstance(evidence, dict) else {}
    post_count = public_flow.get("deduped_post_count", 0) if isinstance(public_flow, dict) else 0
    total_flow = snapshot.get("total_flow_count", 0) if isinstance(snapshot, dict) else 0
    message = (
        f"采集完成，已采到 {post_count} 条公开内容，当前快照公开互动 {total_flow}。"
        if post_count
        else "采集流程执行完成，但本次没有采到公开内容；请检查账号主页 URL、登录状态、平台限制或爬虫日志。"
    )
    task.update(
        {
            "status": "completed",
            "stage": "completed",
            "progress": 100,
            "message": message,
            "result": result,
            "finished_at": _now_iso(),
        }
    )
    task["logs"].append({"time": _now_iso(), "stage": "completed", "message": task["message"]})


def _fail_fetch_task(task_id: str, exc: Exception) -> None:
    task = _fetch_now_tasks.get(task_id)
    if not task:
        return
    message = str(exc)
    task.update(
        {
            "status": "failed",
            "stage": "failed",
            "progress": 100,
            "message": message,
            "error": {"type": type(exc).__name__, "message": message},
            "finished_at": _now_iso(),
        }
    )
    task["logs"].append({"time": _now_iso(), "stage": "failed", "message": message})


def _trim_fetch_now_tasks(max_tasks: int = 100) -> None:
    if len(_fetch_now_tasks) <= max_tasks:
        return
    for key in list(_fetch_now_tasks)[: len(_fetch_now_tasks) - max_tasks]:
        _fetch_now_tasks.pop(key, None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/{competitor_id}/composition")
async def create_competitor_composition_snapshot(
    competitor_id: int,
    request: CompetitorCompositionRequest,
):
    require_research_database()
    from datetime import date

    snapshot = build_competitor_composition_snapshot(
        competitor_account_id=competitor_id,
        snapshot_date=date.fromisoformat(request.snapshot_date),
        platform=request.platform,
        posts=request.posts,
        entity_tags=request.entity_tags,
        keywords=request.keywords,
    )
    return await ResearchRepository().upsert_competitor_composition_snapshot(snapshot)


@router.post("/{competitor_id}/composition/rebuild")
async def rebuild_competitor_composition_snapshot(
    competitor_id: int,
    request: CompetitorCompositionRebuildRequest,
):
    require_research_database()
    from datetime import date

    repository = ResearchRepository()
    competitor = await repository.get_competitor_account(competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    competitor = await _ensure_competitor_display_name(repository, competitor)
    posts = await repository.list_posts_by_creator(
        platform=competitor["platform"],
        creator_id=competitor["creator_id"],
        limit=500,
    )
    tags = await repository.list_entity_tags(
        entity_type="creator",
        entity_id=competitor["creator_id"],
        platform=competitor["platform"],
        vertical_id=competitor.get("vertical_id"),
    )
    keywords = request.keywords
    if not keywords:
        scene_keywords = await repository.list_scene_pack_keywords(enabled_only=True)
        keywords = [
            item["keyword"]
            for item in scene_keywords
            if item.get("keyword_type") != "negative"
            and (item.get("platform") is None or item.get("platform") == competitor["platform"])
        ][:50]
    snapshot = build_competitor_composition_snapshot(
        competitor_account_id=competitor_id,
        snapshot_date=date.fromisoformat(request.snapshot_date) if request.snapshot_date else date.today(),
        platform=competitor["platform"],
        posts=posts,
        entity_tags=tags,
        keywords=keywords,
    )
    return await repository.upsert_competitor_composition_snapshot(snapshot)


@router.post("/{competitor_id}/public-flow/rebuild")
async def rebuild_competitor_public_flow_snapshot(
    competitor_id: int,
    request: CompetitorPublicFlowRebuildRequest,
):
    require_research_database()
    repository = ResearchRepository()
    return await _rebuild_public_flow_snapshot_for_competitor(
        repository,
        competitor_id=competitor_id,
        keywords=request.keywords,
        snapshot_date=request.snapshot_date,
        latest_limit=request.latest_limit,
    )


@router.post("/composition/rebuild-all")
async def rebuild_all_competitor_composition_snapshots(request: CompetitorCompositionRebuildRequest):
    require_research_database()
    repository = ResearchRepository()
    competitors = await repository.list_competitor_accounts(enabled_only=True)
    rebuilt = []
    for competitor in competitors:
        rebuilt.append(
            await rebuild_competitor_composition_snapshot(
                competitor["id"],
                request,
            )
        )
    return {"rebuilt_count": len(rebuilt), "snapshots": rebuilt}


@router.post("/public-flow/rebuild-all")
async def rebuild_all_competitor_public_flow_snapshots(request: CompetitorPublicFlowRebuildRequest):
    require_research_database()
    repository = ResearchRepository()
    competitors = await repository.list_competitor_accounts(enabled_only=True)
    rebuilt = []
    for competitor in competitors:
        rebuilt.append(
            await _rebuild_public_flow_snapshot_for_competitor(
                repository,
                competitor_id=competitor["id"],
                keywords=request.keywords,
                snapshot_date=request.snapshot_date,
                latest_limit=request.latest_limit,
            )
        )
    return {"rebuilt_count": len(rebuilt), "snapshots": rebuilt}


async def _rebuild_public_flow_snapshot_for_competitor(
    repository: ResearchRepository,
    *,
    competitor_id: int,
    keywords: list[str],
    snapshot_date: str | None,
    latest_limit: int,
    days_back: int | None = None,
) -> dict:
    competitor = await repository.get_competitor_account(competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    posts = await repository.list_posts_by_creator(
        platform=competitor["platform"],
        creator_id=competitor["creator_id"],
        limit=latest_limit * 2,
    )
    posts = _filter_posts_by_days(posts, days_back)
    tags = await repository.list_entity_tags(
        entity_type="creator",
        entity_id=competitor["creator_id"],
        platform=competitor["platform"],
        vertical_id=competitor.get("vertical_id"),
    )
    effective_keywords = keywords
    if not effective_keywords:
        scene_keywords = await repository.list_scene_pack_keywords(enabled_only=True)
        effective_keywords = [
            item["keyword"]
            for item in scene_keywords
            if item.get("keyword_type") != "negative"
            and (item.get("platform") is None or item.get("platform") == competitor["platform"])
        ][:50]
    previous_snapshots = await repository.list_competitor_composition_snapshots(
        competitor_id=competitor_id,
        limit=8,
    )
    snapshot = build_competitor_public_flow_snapshot(
        competitor=competitor,
        posts=posts,
        keywords=effective_keywords,
        entity_tags=tags,
        previous_snapshots=previous_snapshots,
        snapshot_date=date.fromisoformat(snapshot_date) if snapshot_date else date.today(),
        latest_limit=latest_limit,
    )
    snapshot["evidence"] = {
        **(snapshot.get("evidence") or {}),
        "time_window": {
            "days_back": days_back,
            "label": f"近 {days_back} 天" if days_back else "最新内容",
        },
    }
    return await repository.upsert_competitor_composition_snapshot(snapshot)


def _filter_posts_by_days(posts: list[dict], days_back: int | None) -> list[dict]:
    if not days_back:
        return posts
    start_at = datetime.combine(date.today() - timedelta(days=days_back - 1), time.min)
    result = []
    for post in posts:
        publish_time = _post_publish_datetime(post.get("publish_time"))
        if publish_time is None or publish_time >= start_at:
            result.append(post)
    return result


def _post_publish_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


async def _payload_with_display_name(repository: ResearchRepository, payload: dict) -> dict:
    if payload.get("display_name"):
        return payload
    display_name = await _lookup_competitor_display_name(repository, payload)
    if display_name:
        return {**payload, "display_name": display_name}
    return payload


async def _enrich_competitors_with_display_names(repository: ResearchRepository, competitors: list[dict]) -> list[dict]:
    enriched = []
    for competitor in competitors:
        enriched.append(await _ensure_competitor_display_name(repository, competitor))
    return enriched


async def _ensure_competitor_display_name(repository: ResearchRepository, competitor: dict) -> dict:
    if competitor.get("display_name"):
        return competitor
    display_name = await _lookup_competitor_display_name(repository, competitor)
    if not display_name:
        return competitor
    updated = await repository.update_competitor_account(
        competitor["id"],
        {"display_name": display_name},
    )
    return updated or {**competitor, "display_name": display_name}


async def _lookup_competitor_display_name(repository: ResearchRepository, payload: dict) -> str | None:
    display_name, _diagnostics = await _lookup_competitor_display_name_with_diagnostics(repository, payload)
    return display_name


async def _lookup_competitor_display_name_with_diagnostics(
    repository: ResearchRepository,
    payload: dict,
) -> tuple[str | None, dict]:
    platform = payload.get("platform")
    creator_id = payload.get("creator_id")
    diagnostics = {
        "platform": platform,
        "creator_id": creator_id,
        "has_profile_url": bool(payload.get("profile_url")),
        "has_tikhub_api_key": bool(getattr(config, "TIKHUB_API_KEY", "")),
        "enable_tikhub": bool(getattr(config, "ENABLE_TIKHUB", False)),
        "local_profile": "not_checked",
        "tikhub": "not_checked",
        "candidate_pool": "not_checked",
        "account_profile": "not_checked",
    }
    if not platform or not creator_id:
        diagnostics["reason"] = "missing_platform_or_creator_id"
        return None, diagnostics

    if hasattr(repository, "get_creator_profile"):
        profile = await repository.get_creator_profile(platform, creator_id)
        name = _public_display_name(profile, creator_id)
        if name:
            diagnostics["local_profile"] = "hit"
            return name, diagnostics
        diagnostics["local_profile"] = "miss"

    if _tikhub_profile_lookup_enabled() and payload.get("profile_url"):
        name, tikhub_status = await _lookup_display_name_from_tikhub(repository, payload)
        diagnostics["tikhub"] = tikhub_status
        if name:
            return name, diagnostics
    else:
        missing = []
        if not _tikhub_profile_lookup_enabled():
            missing.append("api_key")
        if not payload.get("profile_url"):
            missing.append("profile_url")
        diagnostics["tikhub"] = f"skipped_missing_{'_and_'.join(missing)}"

    if hasattr(repository, "list_creator_candidates"):
        candidates = await repository.list_creator_candidates(platform=platform)
        for candidate in candidates:
            if candidate.get("creator_id") == creator_id:
                name = _public_display_name(candidate, creator_id)
                if name:
                    diagnostics["candidate_pool"] = "hit"
                    return name, diagnostics
        diagnostics["candidate_pool"] = "miss"

    if hasattr(repository, "list_account_profiles"):
        profiles = await repository.list_account_profiles(platform=platform)
        for profile in profiles:
            if profile.get("account_id") == creator_id:
                name = _public_display_name(profile, creator_id)
                if name:
                    diagnostics["account_profile"] = "hit"
                    return name, diagnostics
        diagnostics["account_profile"] = "miss"
    return None, diagnostics


def _tikhub_profile_lookup_enabled() -> bool:
    return bool(getattr(config, "ENABLE_TIKHUB", False) or getattr(config, "TIKHUB_API_KEY", ""))


async def _lookup_display_name_from_tikhub(repository: ResearchRepository, payload: dict) -> tuple[str | None, str]:
    try:
        result = await enrich_creator_metrics_from_tikhub(repository, [payload])
    except Exception as exc:
        return None, f"error:{type(exc).__name__}:{str(exc)[:120]}"
    for item in result.get("enriched") or []:
        name = _public_display_name(item, payload.get("creator_id"))
        if name:
            return name, "hit"
    failed = result.get("failed") or []
    if failed:
        error = failed[0].get("error") if isinstance(failed[0], dict) else failed[0]
        return None, f"failed:{str(error)[:160]}"
    return None, "miss"


def _public_display_name(item: dict | None, creator_id: str | None) -> str | None:
    if not item:
        return None
    for key in ("display_name", "nickname", "nick_name", "name"):
        value = str(item.get(key) or "").strip()
        if value and value != str(creator_id or ""):
            return value
    return None


def _creator_id_from_profile_url(platform: str, profile_url: str) -> str | None:
    from urllib.parse import urlparse

    path = urlparse(profile_url).path.strip("/")
    parts = [part for part in path.split("/") if part]
    if platform == "xhs" and "profile" in parts:
        index = parts.index("profile")
        if index + 1 < len(parts):
            return parts[index + 1]
    if platform == "dy" and parts:
        if parts[0] == "user" and len(parts) > 1:
            return parts[1]
        return parts[-1]
    return parts[-1] if parts else None
