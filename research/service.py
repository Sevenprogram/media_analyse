from typing import Any, Protocol

from research.enums import JOB_PENDING
from research.schemas import ResearchJobCreate


class JobRepository(Protocol):
    async def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def list_jobs(self) -> list[dict[str, Any]]:
        ...

    async def get_job(self, job_id: int) -> dict[str, Any] | None:
        ...


class ResearchJobService:
    def __init__(self, repository: JobRepository):
        self.repository = repository

    async def create_job(self, request: ResearchJobCreate) -> dict[str, Any]:
        payload = request.model_dump(mode="python")
        payload["comment_policy"] = request.comment_policy.model_dump(mode="json")
        payload["status"] = JOB_PENDING
        return await self.repository.create_job(payload)

    async def list_jobs(self) -> list[dict[str, Any]]:
        return await self.repository.list_jobs()

    async def get_job(self, job_id: int) -> dict[str, Any] | None:
        return await self.repository.get_job(job_id)
