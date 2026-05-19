import hashlib
import json
from typing import Any

from sqlalchemy import select

from database.db_session import get_session
from research.models import (
    CrawlEvent,
    RawRecord,
    ResearchAuthor,
    ResearchComment,
    ResearchJob,
    ResearchPost,
)


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

    async def update_job(self, job_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        async with get_session() as session:
            job = await session.get(ResearchJob, job_id)
            if job is None:
                return None
            for key, value in payload.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            await session.flush()
            await session.refresh(job)
            return self._job_to_dict(job)

    async def create_event(
        self,
        *,
        job_id: int,
        platform: str | None,
        event_type: str,
        message: str,
        stats: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with get_session() as session:
            event = CrawlEvent(
                job_id=job_id,
                platform=platform,
                event_type=event_type,
                message=message,
                stats_json=stats or {},
            )
            session.add(event)
            await session.flush()
            await session.refresh(event)
            return {
                "id": event.id,
                "job_id": event.job_id,
                "platform": event.platform,
                "event_type": event.event_type,
                "message": event.message,
                "stats_json": event.stats_json,
                "created_at": event.created_at,
            }

    async def create_raw_record(
        self,
        *,
        job_id: int,
        platform: str,
        source_type: str,
        source_id: str | None,
        source_url: str | None,
        payload: dict[str, Any],
        parser_version: str = "research-v1",
    ) -> dict[str, Any]:
        payload_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        async with get_session() as session:
            raw_record = RawRecord(
                job_id=job_id,
                platform=platform,
                source_type=source_type,
                source_id=source_id,
                source_url=source_url,
                payload_hash=payload_hash,
                payload_json=payload,
                parser_version=parser_version,
            )
            session.add(raw_record)
            await session.flush()
            await session.refresh(raw_record)
            return {
                "id": raw_record.id,
                "payload_hash": raw_record.payload_hash,
                "fetched_at": raw_record.fetched_at,
            }

    async def upsert_author(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = select(ResearchAuthor).where(
                ResearchAuthor.job_id == payload["job_id"],
                ResearchAuthor.platform == payload["platform"],
                ResearchAuthor.author_hash == payload["author_hash"],
            )
            result = await session.execute(stmt)
            author = result.scalar_one_or_none()
            if author is None:
                author = ResearchAuthor(**payload)
                session.add(author)
            else:
                for key, value in payload.items():
                    if hasattr(author, key):
                        setattr(author, key, value)
            await session.flush()
            await session.refresh(author)
            return {"id": author.id, "author_hash": author.author_hash}

    async def upsert_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = select(ResearchPost).where(
                ResearchPost.job_id == payload["job_id"],
                ResearchPost.platform == payload["platform"],
                ResearchPost.platform_post_id == payload["platform_post_id"],
            )
            result = await session.execute(stmt)
            post = result.scalar_one_or_none()
            if post is None:
                post = ResearchPost(**payload)
                session.add(post)
            else:
                for key, value in payload.items():
                    if hasattr(post, key):
                        setattr(post, key, value)
            await session.flush()
            await session.refresh(post)
            return {"id": post.id, "platform_post_id": post.platform_post_id}

    async def upsert_comment(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = select(ResearchComment).where(
                ResearchComment.job_id == payload["job_id"],
                ResearchComment.platform == payload["platform"],
                ResearchComment.platform_comment_id == payload["platform_comment_id"],
            )
            result = await session.execute(stmt)
            comment = result.scalar_one_or_none()
            if comment is None:
                comment = ResearchComment(**payload)
                session.add(comment)
            else:
                for key, value in payload.items():
                    if hasattr(comment, key):
                        setattr(comment, key, value)
            await session.flush()
            await session.refresh(comment)
            return {"id": comment.id, "platform_comment_id": comment.platform_comment_id}

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
