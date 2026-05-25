from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from api.deps.auth import get_current_user_context

router = APIRouter(tags=["orgs"])


@router.get("/me")
async def get_me(
    context: Annotated[dict[str, Any], Depends(get_current_user_context)],
):
    return context


@router.get("/orgs/current")
async def get_current_org(
    context: Annotated[dict[str, Any], Depends(get_current_user_context)],
):
    return {
        "organization": context["organization"],
        "membership": context["membership"],
    }


@router.get("/orgs")
async def list_current_orgs(
    context: Annotated[dict[str, Any], Depends(get_current_user_context)],
):
    return {
        "organizations": [
            {
                "organization": context["organization"],
                "membership": context["membership"],
            }
        ]
    }
