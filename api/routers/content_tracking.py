import os
from datetime import date, timedelta
from math import ceil
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.routers.research import (
    cancel_active_research_execution_job,
    require_research_database,
    schedule_and_execute_research_job,
    wait_for_research_job_status,
)
from research.content_tracking import (
    analyze_content_tracking,
    build_tracker_analysis,
    build_content_keyword_ai_prompt,
    build_content_tracking_ai_prompt,
    extract_content_keywords,
    normalize_content_keyword_ai_output,
    normalize_content_tracking_ai_output,
    search_similar_content,
)
from research.content_fingerprint import analyze_posts_for_tracking
from research.ai_provider import OpenAICompatibleProvider
from research.repository import ResearchRepository
from research.enums import JOB_CANCELLED
from research.schemas import (
    ContentTrackingAIAnalysisRequest,
    ContentKeywordExtractionRequest,
    ContentTrackerCreate,
    SimilarContentSearchRequest,
)

router = APIRouter(prefix="/content-tracking", tags=["content-tracking"])

REALTIME_CONTENT_PLATFORMS = {"xhs", "dy"}
DEFAULT_REALTIME_COLLECTION_WINDOW_DAYS = 3


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
    tracker = await ResearchRepository().create_content_tracker(
        request.model_dump(mode="python")
    )
    return tracker


@router.get("/trackers")
async def list_trackers(enabled_only: bool = False):
    require_research_database()
    return {
        "trackers": await ResearchRepository().list_content_trackers(
            enabled_only=enabled_only,
        )
    }


@router.post("/trackers/{tracker_id}/analysis")
async def analyze_tracker(tracker_id: int):
    require_research_database()
    repository = ResearchRepository()
    tracker = await repository.get_content_tracker(tracker_id)
    if tracker is None:
        raise HTTPException(status_code=404, detail="Content tracker not found")
    platform = tracker["platforms"][0] if len(tracker.get("platforms") or []) == 1 else None
    posts = await repository.list_all_posts(platform=platform, limit=500)
    candidates = search_similar_content(
        keywords=tracker.get("included_keywords") or [],
        posts=posts,
        limit=50,
    )
    analysis = build_tracker_analysis(tracker=tracker, candidates=candidates)
    snapshot = await repository.create_content_tracking_snapshot(
        _tracker_snapshot_payload(tracker, analysis, candidates)
    )
    return {**analysis, "snapshot": snapshot}


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


def _tracker_snapshot_payload(
    tracker: dict,
    analysis: dict,
    candidates: list[dict],
) -> dict:
    from collections import Counter

    keyword_distribution = {
        item["name"]: item["value"]
        for item in analysis.get("summary", {}).get("top_keywords", [])
    }
    content_type_distribution = Counter(
        (item.get("content_type") or "unknown") for item in candidates
    )
    publish_time_distribution = Counter()
    hot_count = 0
    for item in candidates:
        publish_time = item.get("publish_time")
        hour = getattr(publish_time, "hour", None)
        if hour is not None:
            publish_time_distribution[str(hour)] += 1
        engagement = item.get("engagement") or {}
        total = sum(
            int(engagement.get(key) or 0)
            for key in ("liked_count", "like_count", "comment_count", "comments_count", "share_count")
        )
        if total >= 100:
            hot_count += 1
    return {
        "tracker_id": tracker["id"],
        "snapshot_date": date.today(),
        "platform": tracker["platforms"][0] if len(tracker.get("platforms") or []) == 1 else None,
        "keyword_distribution": keyword_distribution,
        "tag_distribution": {},
        "content_type_distribution": dict(content_type_distribution),
        "publish_time_distribution": dict(publish_time_distribution),
        "hot_post_rate": round(hot_count / max(1, len(candidates)), 4),
        "total_content_count": len(candidates),
        "evidence": {"hot_content": analysis.get("hot_content", [])[:10]},
    }
