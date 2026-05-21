from fastapi import APIRouter, HTTPException, Response

from api.routers.research import require_research_database
from research.growth_ai import expand_keywords_with_provider
from research.keyword_library import export_scene_pack_keywords_csv
from research.repository import ResearchRepository
from research.schemas import (
    AIKeywordExpansionRequest,
    ScenePackCreate,
    ScenePackKeywordCreate,
)

router = APIRouter(prefix="/keyword-library", tags=["keyword-library"])


@router.post("/scene-packs")
async def create_scene_pack(request: ScenePackCreate):
    require_research_database()
    return await ResearchRepository().create_scene_pack(request.model_dump(mode="python"))


@router.get("/scene-packs")
async def list_scene_packs(vertical_id: int | None = None, enabled_only: bool = False):
    require_research_database()
    scene_packs = await ResearchRepository().list_scene_packs(
        vertical_id=vertical_id,
        enabled_only=enabled_only,
    )
    return {"scene_packs": scene_packs}


@router.post("/keywords")
async def create_scene_pack_keyword(request: ScenePackKeywordCreate):
    require_research_database()
    return await ResearchRepository().create_scene_pack_keyword(
        request.model_dump(mode="python")
    )


@router.get("/keywords")
async def list_scene_pack_keywords(
    scene_pack_id: int | None = None,
    enabled_only: bool = False,
):
    require_research_database()
    ids = [scene_pack_id] if scene_pack_id else None
    keywords = await ResearchRepository().list_scene_pack_keywords(
        scene_pack_ids=ids,
        enabled_only=enabled_only,
    )
    return {"keywords": keywords}


@router.get("/keywords/export")
async def export_keywords(scene_pack_id: int | None = None):
    require_research_database()
    ids = [scene_pack_id] if scene_pack_id else None
    items = await ResearchRepository().list_scene_pack_keywords(scene_pack_ids=ids)
    return Response(
        content=export_scene_pack_keywords_csv(items),
        media_type="text/csv; charset=utf-8",
    )


@router.post("/ai/expand")
async def ai_expand_keywords(request: AIKeywordExpansionRequest):
    require_research_database()
    repository = ResearchRepository()
    provider = None
    if request.provider_config_id:
        provider = await repository.get_ai_provider(
            request.provider_config_id,
            include_secret=True,
        )
    if provider is None:
        raise HTTPException(status_code=404, detail="AI provider config not found")

    suggestions = await expand_keywords_with_provider(
        provider,
        request.model_dump(mode="python"),
    )
    return await repository.create_ai_keyword_suggestion_session(
        {
            "vertical_id": request.vertical_id,
            "scene_pack_id": request.scene_pack_id,
            "seed_keywords": [request.input_text],
            "audience_context": request.input_text,
            "provider_config_id": request.provider_config_id,
            "status": "completed",
            "suggestions": suggestions,
        }
    )


@router.post("/ai/suggestions")
async def create_ai_keyword_suggestion(payload: dict):
    require_research_database()
    return await ResearchRepository().create_ai_keyword_suggestion_session(
        {
            "vertical_id": payload.get("vertical_id"),
            "scene_pack_id": payload.get("scene_pack_id"),
            "seed_keywords": [payload.get("input_text")]
            if payload.get("input_text")
            else payload.get("seed_keywords", []),
            "audience_context": payload.get("input_text") or payload.get("audience_context"),
            "provider_config_id": payload.get("provider_config_id"),
            "status": "pending",
            "suggestions": [
                payload["suggested_payload"]
                if "suggested_payload" in payload
                else payload.get("suggestion", {})
            ],
        }
    )


@router.get("/ai/suggestions")
async def list_ai_keyword_suggestions(
    status: str | None = None,
    vertical_id: int | None = None,
    scene_pack_id: int | None = None,
):
    require_research_database()
    return {
        "suggestions": await ResearchRepository().list_ai_keyword_suggestion_sessions(
            status=status,
            vertical_id=vertical_id,
            scene_pack_id=scene_pack_id,
        )
    }


@router.post("/ai/suggestions/{suggestion_id}/approve")
async def approve_ai_keyword_suggestion(suggestion_id: int):
    require_research_database()
    result = await ResearchRepository().approve_ai_keyword_suggestion_session(suggestion_id)
    if result is None:
        raise HTTPException(status_code=404, detail="AI keyword suggestion not found")
    return result


@router.post("/ai/suggestions/{suggestion_id}/reject")
async def reject_ai_keyword_suggestion(suggestion_id: int, payload: dict | None = None):
    require_research_database()
    result = await ResearchRepository().reject_ai_keyword_suggestion_session(
        suggestion_id,
        reason=(payload or {}).get("reason"),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="AI keyword suggestion not found")
    return result
