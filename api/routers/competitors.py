from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.routers.research import require_research_database
from research.competitors import CompetitorService, build_competitor_composition_snapshot
from research.repository import ResearchRepository
from research.schemas import CompetitorAccountCreate, CompetitorAccountUpdate

router = APIRouter(prefix="/competitors", tags=["competitors"])


class CompetitorCompositionRequest(BaseModel):
    snapshot_date: str
    platform: str
    posts: list[dict] = Field(default_factory=list)
    entity_tags: list[dict] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class CompetitorCompositionRebuildRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    snapshot_date: str | None = None


@router.post("")
async def create_competitor_account(request: CompetitorAccountCreate):
    require_research_database()
    try:
        return await CompetitorService(ResearchRepository()).create_competitor(
            request.model_dump(mode="python")
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
async def list_competitor_accounts(enabled_only: bool = False):
    require_research_database()
    return {
        "competitors": await ResearchRepository().list_competitor_accounts(
            enabled_only=enabled_only
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
