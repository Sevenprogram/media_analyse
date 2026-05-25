from fastapi import APIRouter, Depends, HTTPException

from api.deps.auth import require_current_user
from api.routers.research import require_research_database
from research.repository import ResearchRepository

router = APIRouter(
    prefix="/accounts",
    tags=["accounts"],
    dependencies=[Depends(require_current_user)],
)


@router.get("/profiles")
async def list_account_profiles(
    platform: str | None = None,
    role: str | None = None,
    vertical_id: int | None = None,
    scene_pack_id: int | None = None,
):
    require_research_database()
    return {
        "profiles": await ResearchRepository().list_account_profiles(
            platform=platform,
            role=role,
            vertical_id=vertical_id,
            scene_pack_id=scene_pack_id,
        )
    }


@router.get("/profiles/{profile_id}")
async def get_account_profile(profile_id: int):
    require_research_database()
    item = await ResearchRepository().get_account_profile(profile_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Account profile not found")
    return item


@router.get("/profiles/{profile_id}/roles")
async def list_account_profile_roles(profile_id: int):
    require_research_database()
    return {"roles": await ResearchRepository().list_account_roles(profile_id=profile_id)}


@router.post("/profiles/{profile_id}/roles")
async def add_account_profile_role(profile_id: int, payload: dict):
    require_research_database()
    if await ResearchRepository().get_account_profile(profile_id) is None:
        raise HTTPException(status_code=404, detail="Account profile not found")
    payload = {**payload, "account_profile_id": profile_id}
    return await ResearchRepository().upsert_account_role(payload)
