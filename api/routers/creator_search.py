from datetime import date

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

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

router = APIRouter(prefix="/creator-search", tags=["creator-search"])


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
