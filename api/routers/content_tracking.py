from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.routers.research import (
    require_research_database,
    schedule_and_execute_research_job,
    wait_for_research_job_status,
)
from research.content_tracking import (
    analyze_content_tracking,
    build_tracker_analysis,
    extract_content_keywords,
    search_similar_content,
)
from research.repository import ResearchRepository
from research.schemas import (
    ContentKeywordExtractionRequest,
    ContentTrackerCreate,
    SimilarContentSearchRequest,
)

router = APIRouter(prefix="/content-tracking", tags=["content-tracking"])


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
    return analyze_content_tracking(
        query=request.query,
        posts=posts,
        comments=comments,
        entity_tags=tags,
        tag_definitions=tag_definitions,
        limit=request.limit,
    )


@router.post("/extract-keywords")
async def extract_keywords(request: ContentKeywordExtractionRequest):
    require_research_database()
    repository = ResearchRepository()
    scene_keywords = await repository.list_scene_pack_keywords(
        scene_pack_ids=request.scene_pack_ids or None,
        enabled_only=True,
    )
    text = " ".join([request.title or "", request.text])
    return {
        "keywords": extract_content_keywords(
            text=text,
            scene_keywords=scene_keywords,
        )
    }


@router.post("/search-similar")
async def search_similar(request: SimilarContentSearchRequest):
    require_research_database()
    repository = ResearchRepository()
    platform = request.platforms[0] if len(request.platforms) == 1 else None
    posts = await repository.list_all_posts(platform=platform, limit=500)
    candidates = search_similar_content(
        keywords=request.keywords,
        posts=posts,
        limit=request.limit,
    )
    return {"candidates": candidates}


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
    if not request.platforms:
        raise HTTPException(
            status_code=400,
            detail="Realtime content discovery requires selected or global default platforms",
        )
    repository = ResearchRepository()
    job = await repository.create_job(
        {
            "name": f"content realtime discovery - {' '.join(request.keywords)}",
            "topic": "content_realtime_discovery",
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
        background=True,
        force_schedule=True,
    )
    return {"status": execution["status"], "job_id": job["id"], "execution": execution}


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
    posts = await repository.list_all_posts(job_id=job_id, limit=500)
    candidates = search_similar_content(keywords=job.get("keywords") or [], posts=posts, limit=50)
    return {
        "job_id": job_id,
        "status": job["status"],
        "refreshed": True,
        "candidates": candidates,
    }


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
