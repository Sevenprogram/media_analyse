import asyncio
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from api.deps.auth import require_platform_admin
from api.routers.research import require_research_database
from research.bootstrap_defaults import bootstrap_default_research_config
from research.competitors import calculate_keyword_opportunities
from research.creator_search import rebuild_creator_profiles
from research.repository import ResearchRepository
from research.schemas import (
    PlatformCapabilityUpsert,
    CreatorProfileRebuildRequest,
    SideNavConfigUpsert,
    TagDefinitionCreate,
    TagDefinitionImportRequest,
    TagDefinitionUpdate,
    TagGroupCreate,
    TagGroupUpdate,
    TaggingRunRequest,
    VerticalCreate,
    VerticalUpdate,
)
from research.tagging import tag_research_job
from research.ui_navigation import SIDE_NAV_CONFIG_KEY, normalize_side_nav_config

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_platform_admin)])
_creator_profile_rebuild_jobs: dict[str, dict] = {}


@router.post("/bootstrap/defaults")
async def bootstrap_defaults():
    require_research_database()
    return await bootstrap_default_research_config(ResearchRepository())


@router.get("/platform-capabilities")
async def list_platform_capabilities():
    require_research_database()
    return {"capabilities": await ResearchRepository().list_platform_capabilities()}


@router.put("/platform-capabilities/{platform}")
async def upsert_platform_capability(platform: str, request: PlatformCapabilityUpsert):
    require_research_database()
    payload = request.model_dump(mode="python")
    payload["platform"] = platform
    validated = PlatformCapabilityUpsert(**payload)
    return await ResearchRepository().upsert_platform_capability(
        validated.model_dump(mode="python")
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


@router.put("/ui/side-nav-config")
async def upsert_side_nav_config(request: SideNavConfigUpsert):
    require_research_database()
    repository = ResearchRepository()
    normalized = normalize_side_nav_config(request.model_dump(mode="python"))
    return await repository.upsert_global_setting(SIDE_NAV_CONFIG_KEY, normalized)


@router.get("/verticals")
async def list_verticals(enabled_only: bool = False):
    require_research_database()
    return {"verticals": await ResearchRepository().list_verticals(enabled_only=enabled_only)}


@router.post("/verticals")
async def create_vertical(request: VerticalCreate):
    require_research_database()
    return await ResearchRepository().create_vertical(request.model_dump(mode="python"))


@router.patch("/verticals/{vertical_id}")
async def update_vertical(vertical_id: int, request: VerticalUpdate):
    require_research_database()
    result = await ResearchRepository().update_vertical(
        vertical_id,
        request.model_dump(mode="python", exclude_unset=True),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Vertical not found")
    return result


@router.get("/tag-groups")
async def list_tag_groups(vertical_id: int | None = None, enabled_only: bool = False):
    require_research_database()
    return {
        "tag_groups": await ResearchRepository().list_tag_groups(
            vertical_id=vertical_id,
            enabled_only=enabled_only,
        )
    }


@router.post("/tag-groups")
async def create_tag_group(request: TagGroupCreate):
    require_research_database()
    return await ResearchRepository().create_tag_group(request.model_dump(mode="python"))


@router.patch("/tag-groups/{group_id}")
async def update_tag_group(group_id: int, request: TagGroupUpdate):
    require_research_database()
    result = await ResearchRepository().update_tag_group(
        group_id,
        request.model_dump(mode="python", exclude_unset=True),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Tag group not found")
    return result


@router.get("/tag-definitions")
async def list_tag_definitions(vertical_id: int | None = None, enabled_only: bool = False):
    require_research_database()
    return {
        "tag_definitions": await ResearchRepository().list_tag_definitions(
            vertical_id=vertical_id,
            enabled_only=enabled_only,
        )
    }


@router.post("/tag-definitions")
async def create_tag_definition(request: TagDefinitionCreate):
    require_research_database()
    return await ResearchRepository().create_tag_definition(request.model_dump(mode="python"))


@router.patch("/tag-definitions/{tag_id}")
async def update_tag_definition(tag_id: int, request: TagDefinitionUpdate):
    require_research_database()
    result = await ResearchRepository().update_tag_definition(
        tag_id,
        request.model_dump(mode="python", exclude_unset=True),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Tag definition not found")
    return result


@router.post("/tag-definitions/import")
async def import_tag_definitions(request: TagDefinitionImportRequest):
    require_research_database()
    repository = ResearchRepository()
    imported = []
    verticals = {item["code"]: item for item in await repository.list_verticals()}
    for item in request.items:
        payload = item.model_dump(mode="python")
        vertical = verticals.get(payload["vertical_code"])
        if vertical is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown vertical_code: {payload['vertical_code']}",
            )
        group = await repository.upsert_tag_group_by_name(
            {
                "vertical_id": vertical["id"],
                "name": payload["group_name"],
                "description": None,
                "sort_order": 100,
                "enabled": True,
            }
        )
        imported.append(
            await repository.upsert_tag_definition_by_name(
                {
                    "vertical_id": vertical["id"],
                    "group_id": group["id"],
                    "tag_name": payload["tag_name"],
                    "keywords": payload["keywords"],
                    "synonyms": payload["synonyms"],
                    "negative_keywords": payload["negative_keywords"],
                    "ai_prompt_hint": payload["ai_prompt_hint"],
                    "weight": payload["weight"],
                    "enabled": payload["enabled"],
                }
            )
        )
    return {"imported": imported, "count": len(imported)}


@router.get("/tag-definitions/export")
async def export_tag_definitions(vertical_id: int | None = None, enabled_only: bool = False):
    require_research_database()
    repository = ResearchRepository()
    verticals = {item["id"]: item for item in await repository.list_verticals()}
    groups = {item["id"]: item for item in await repository.list_tag_groups()}
    tags = await repository.list_tag_definitions(
        vertical_id=vertical_id,
        enabled_only=enabled_only,
    )
    return {
        "items": [
            {
                "vertical_code": verticals.get(tag["vertical_id"], {}).get("code"),
                "vertical_name": verticals.get(tag["vertical_id"], {}).get("name"),
                "group_name": groups.get(tag["group_id"], {}).get("name"),
                "tag_name": tag["tag_name"],
                "keywords": tag["keywords"],
                "synonyms": tag["synonyms"],
                "negative_keywords": tag["negative_keywords"],
                "ai_prompt_hint": tag["ai_prompt_hint"],
                "weight": tag["weight"],
                "enabled": tag["enabled"],
            }
            for tag in tags
        ],
        "count": len(tags),
    }


@router.post("/tagging/jobs/{job_id}/run")
async def run_tagging_for_job(job_id: int, request: TaggingRunRequest):
    require_research_database()
    return await tag_research_job(
        ResearchRepository(),
        job_id=job_id,
        vertical_id=request.vertical_id,
        analysis_version=request.analysis_version,
        use_ai=request.use_ai,
    )


@router.post("/tagging/rebuild")
async def rebuild_tagging(request: TaggingRunRequest):
    require_research_database()
    return await tag_research_job(
        ResearchRepository(),
        job_id=None,
        vertical_id=request.vertical_id,
        analysis_version=request.analysis_version,
        use_ai=request.use_ai,
    )


@router.get("/tagging/status")
async def get_tagging_status(vertical_id: int | None = None):
    require_research_database()
    repository = ResearchRepository()
    try:
        tags = await repository.list_entity_tags(vertical_id=vertical_id)
    except SQLAlchemyError:
        return {
            "entity_tag_count": 0,
            "by_entity_type": {},
            "by_source": {},
            "database_available": False,
        }
    return {
        "entity_tag_count": len(tags),
        "by_entity_type": _count_by(tags, "entity_type"),
        "by_source": _count_by(tags, "source"),
        "database_available": True,
    }


@router.post("/creator-profiles/rebuild")
async def rebuild_profiles(request: CreatorProfileRebuildRequest):
    require_research_database()
    return await rebuild_creator_profiles(
        ResearchRepository(),
        job_id=request.job_id,
        platform=request.platform,
        creator_id=request.creator_id,
        analysis_version=request.analysis_version,
    )


@router.post("/creator-profiles/rebuild/start")
async def start_rebuild_profiles(request: CreatorProfileRebuildRequest):
    require_research_database()
    job_id = uuid4().hex
    _creator_profile_rebuild_jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "total": 0,
        "processed": 0,
        "rebuilt_count": 0,
        "current_creator_id": None,
        "platform": request.platform,
        "error": None,
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": None,
    }
    asyncio.create_task(_run_creator_profile_rebuild(job_id, request))
    return _creator_profile_rebuild_jobs[job_id]


@router.get("/creator-profiles/rebuild/status/{job_id}")
async def get_rebuild_profiles_status(job_id: str):
    status = _creator_profile_rebuild_jobs.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Creator profile rebuild job not found")
    return status


async def _run_creator_profile_rebuild(job_id: str, request: CreatorProfileRebuildRequest):
    def update_progress(progress: dict):
        current = _creator_profile_rebuild_jobs[job_id]
        current.update(progress)
        total = int(current.get("total") or 0)
        processed = int(current.get("processed") or 0)
        current["percent"] = round((processed / total) * 100, 1) if total else 0
        current["updated_at"] = datetime.utcnow().isoformat()

    try:
        update_progress({"status": "running"})
        result = await rebuild_creator_profiles(
            ResearchRepository(),
            job_id=request.job_id,
            platform=request.platform,
            creator_id=request.creator_id,
            analysis_version=request.analysis_version,
            progress_callback=update_progress,
        )
        update_progress(
            {
                "status": "completed",
                "processed": result["rebuilt_count"],
                "rebuilt_count": result["rebuilt_count"],
                "percent": 100,
                "result": result,
                "finished_at": datetime.utcnow().isoformat(),
            }
        )
    except Exception as exc:
        update_progress(
            {
                "status": "failed",
                "error": str(exc),
                "finished_at": datetime.utcnow().isoformat(),
            }
        )


async def _build_competitor_snapshot(repository: ResearchRepository, competitor_id: int):
    competitors = await repository.list_competitor_accounts()
    competitor = next((item for item in competitors if int(item["id"]) == competitor_id), None)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    from datetime import date
    from research.competitors import CompetitorService

    posts = await repository.list_posts_by_creator(
        platform=competitor["platform"],
        creator_id=competitor["creator_id"],
    )
    tags = await repository.list_entity_tags(
        platform=competitor["platform"],
        vertical_id=competitor.get("vertical_id"),
    )
    return await CompetitorService(repository).build_daily_snapshot(
        platform=competitor["platform"],
        creator_id=competitor["creator_id"],
        snapshot_date=date.today(),
        posts=posts,
        entity_tags=tags,
    )


@router.post("/competitors/{competitor_id}/build-snapshot")
async def build_competitor_snapshot(competitor_id: int):
    require_research_database()
    return await _build_competitor_snapshot(ResearchRepository(), competitor_id)


@router.post("/keyword-opportunities/rebuild")
async def rebuild_keyword_opportunities(vertical_id: int, platform: str | None = None):
    require_research_database()
    from datetime import date

    repository = ResearchRepository()
    if platform:
        capability = await repository.get_platform_capability(platform)
        if capability and (not capability["enabled"] or not capability["keyword_heat_enabled"]):
            raise HTTPException(status_code=400, detail="Platform keyword heat analysis is disabled")
    tags = await repository.list_tag_definitions(vertical_id=vertical_id, enabled_only=True)
    entity_tags = await repository.list_entity_tags(vertical_id=vertical_id, platform=platform)
    profiles = await repository.list_creator_profiles(platforms=[platform] if platform else None)
    snapshots = await repository.list_creator_daily_snapshots(platform=platform)
    opportunities = calculate_keyword_opportunities(
        vertical_id=vertical_id,
        tag_definitions=tags,
        entity_tags=entity_tags,
        creator_profiles=profiles,
        snapshots=snapshots,
        platform=platform,
    )
    saved = [
        await repository.create_keyword_opportunity_snapshot(
            {
                "vertical_id": item["vertical_id"],
                "platform": item["platform"],
                "tag_id": item["tag_id"],
                "snapshot_date": date.today(),
                "heat_score": item["heat_score"],
                "growth_score": item["growth_score"],
                "competition_score": item["competition_score"],
                "supply_gap_score": item["supply_gap_score"],
                "platform_signal": item["platform_signal"],
                "evidence_json": item["evidence"],
            }
        )
        for item in opportunities
    ]
    return {"rebuilt_count": len(saved), "opportunities": saved}


def _count_by(items: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return counts
