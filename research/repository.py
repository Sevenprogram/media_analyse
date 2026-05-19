from typing import Any

from sqlalchemy import select

from database.db_session import get_session
from research.models import ResearchJob


class ResearchRepository:
    async def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            job = ResearchJob(**payload)
            session.add(job)
            await session.flush()
            await session.refresh(job)
            return self._job_to_dict(job)

    async def list_jobs(self) -> list[dict[str, Any]]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchJob).order_by(ResearchJob.created_at.desc())
            )
            return [self._job_to_dict(job) for job in result.scalars().all()]

    async def get_job(self, job_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            job = await session.get(ResearchJob, job_id)
            if job is None:
                return None
            return self._job_to_dict(job)

    def _job_to_dict(self, job: ResearchJob) -> dict[str, Any]:
        return {
            "id": job.id,
            "name": job.name,
            "topic": job.topic,
            "platforms": job.platforms,
            "keywords": job.keywords,
            "start_date": job.start_date,
            "end_date": job.end_date,
            "status": job.status,
            "comment_policy": job.comment_policy,
            "raw_record_mode": job.raw_record_mode,
            "anonymize_authors": job.anonymize_authors,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }
