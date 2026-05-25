from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.services.background_task_center import BackgroundTaskCenter
from api.routers.research import (
    get_research_execution_concurrency,
    set_research_execution_concurrency,
)


router = APIRouter(prefix="/background-tasks", tags=["background-tasks"])


class ConcurrencyUpdate(BaseModel):
    max_concurrent: int = Field(ge=1, le=16)


@router.get("")
async def list_background_tasks():
    return await BackgroundTaskCenter().list_tasks()


@router.get("/settings")
async def get_background_task_settings():
    return {"research_execution": get_research_execution_concurrency()}


@router.put("/settings/research-execution-concurrency")
async def update_research_execution_concurrency(request: ConcurrencyUpdate):
    return {"research_execution": set_research_execution_concurrency(request.max_concurrent)}


@router.post("/{task_id:path}/cancel")
async def cancel_background_task(task_id: str):
    return await BackgroundTaskCenter().cancel(task_id)


@router.delete("/{task_id:path}")
async def delete_background_task(task_id: str):
    return await BackgroundTaskCenter().delete(task_id)
