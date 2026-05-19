from typing import Any, Protocol

from research.enums import JOB_PENDING
from research.schemas import ResearchJobCreate, ResearchJobUpdate


class JobRepository(Protocol):
    async def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def list_jobs(self) -> list[dict[str, Any]]:
        ...

    async def get_job(self, job_id: int) -> dict[str, Any] | None:
        ...

    async def update_job(self, job_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
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

    async def update_job(
        self, job_id: int, request: ResearchJobUpdate
    ) -> dict[str, Any] | None:
        payload = request.model_dump(exclude_unset=True, mode="python")
        if "comment_policy" in payload and request.comment_policy is not None:
            payload["comment_policy"] = request.comment_policy.model_dump(mode="json")
        if not payload:
            return await self.repository.get_job(job_id)

        existing = await self.repository.get_job(job_id)
        if existing is None:
            return None
        start_date = payload.get("start_date", existing["start_date"])
        end_date = payload.get("end_date", existing["end_date"])
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        return await self.repository.update_job(job_id, payload)
