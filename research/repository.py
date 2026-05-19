import hashlib
import json
from typing import Any

from sqlalchemy import func, select

from database.db_session import get_session
from research.models import (
    AIAnalysisJob,
    AIAnalysisResult,
    AIProviderConfig,
    AIPromptTemplate,
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

    async def update_job_status(self, job_id: int, status: str) -> dict[str, Any] | None:
        return await self.update_job(job_id, {"status": status})

    async def list_events(self, job_id: int, limit: int = 200) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = (
                select(CrawlEvent)
                .where(CrawlEvent.job_id == job_id)
                .order_by(CrawlEvent.created_at.desc(), CrawlEvent.id.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [
                {
                    "id": event.id,
                    "job_id": event.job_id,
                    "platform": event.platform,
                    "event_type": event.event_type,
                    "message": event.message,
                    "stats_json": event.stats_json,
                    "created_at": event.created_at,
                }
                for event in result.scalars().all()
            ]

    async def get_job_stats(self, job_id: int) -> dict[str, Any]:
        async with get_session() as session:
            post_count = await self._count(session, ResearchPost, job_id)
            comment_count = await self._count(session, ResearchComment, job_id)
            author_count = await self._count(session, ResearchAuthor, job_id)
            raw_record_count = await self._count(session, RawRecord, job_id)
            return {
                "posts": post_count,
                "comments": comment_count,
                "authors": author_count,
                "raw_records": raw_record_count,
                "by_platform": {
                    "posts": await self._count_by_platform(session, ResearchPost, job_id),
                    "comments": await self._count_by_platform(session, ResearchComment, job_id),
                },
            }

    async def list_posts(self, job_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchPost).where(ResearchPost.job_id == job_id)
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [self._post_to_dict(item) for item in result.scalars().all()]

    async def list_comments(self, job_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchComment).where(ResearchComment.job_id == job_id)
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [self._comment_to_dict(item) for item in result.scalars().all()]

    async def list_authors(self, job_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchAuthor).where(ResearchAuthor.job_id == job_id)
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [self._author_to_dict(item) for item in result.scalars().all()]

    async def list_raw_records(self, job_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(RawRecord).where(RawRecord.job_id == job_id)
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [self._raw_record_to_dict(item) for item in result.scalars().all()]

    async def create_ai_provider(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider_payload = {
            "name": payload["name"],
            "base_url": payload["base_url"],
            "api_key_encrypted": payload["api_key"],
            "model": payload["model"],
            "timeout": payload["timeout"],
            "max_concurrency": payload["max_concurrency"],
            "default_params_json": payload.get("default_params", {}),
            "enabled": payload["enabled"],
        }
        async with get_session() as session:
            provider = AIProviderConfig(**provider_payload)
            session.add(provider)
            await session.flush()
            await session.refresh(provider)
            return self._ai_provider_to_dict(provider)

    async def list_ai_providers(self) -> list[dict[str, Any]]:
        async with get_session() as session:
            result = await session.execute(select(AIProviderConfig).order_by(AIProviderConfig.id.desc()))
            return [self._ai_provider_to_dict(item) for item in result.scalars().all()]

    async def get_ai_provider(self, provider_id: int, *, include_secret: bool = False) -> dict[str, Any] | None:
        async with get_session() as session:
            provider = await session.get(AIProviderConfig, provider_id)
            if provider is None:
                return None
            result = self._ai_provider_to_dict(provider)
            if include_secret:
                result["api_key"] = provider.api_key_encrypted
            return result

    async def create_prompt_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt_payload = {
            "name": payload["name"],
            "task_type": payload["task_type"],
            "platform": payload["platform"],
            "prompt_text": payload["prompt_text"],
            "output_schema_json": payload.get("output_schema", {}),
            "version": payload["version"],
            "enabled": payload["enabled"],
        }
        async with get_session() as session:
            prompt = AIPromptTemplate(**prompt_payload)
            session.add(prompt)
            await session.flush()
            await session.refresh(prompt)
            return self._prompt_template_to_dict(prompt)

    async def list_prompt_templates(self) -> list[dict[str, Any]]:
        async with get_session() as session:
            result = await session.execute(select(AIPromptTemplate).order_by(AIPromptTemplate.id.desc()))
            return [self._prompt_template_to_dict(item) for item in result.scalars().all()]

    async def get_prompt_template(self, prompt_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            prompt = await session.get(AIPromptTemplate, prompt_id)
            if prompt is None:
                return None
            return self._prompt_template_to_dict(prompt)

    async def create_ai_analysis_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            job = AIAnalysisJob(**payload)
            session.add(job)
            await session.flush()
            await session.refresh(job)
            return self._ai_analysis_job_to_dict(job)

    async def get_ai_analysis_job(self, analysis_job_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            job = await session.get(AIAnalysisJob, analysis_job_id)
            if job is None:
                return None
            return self._ai_analysis_job_to_dict(job)

    async def list_ai_analysis_jobs(self, research_job_id: int | None = None) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(AIAnalysisJob)
            if research_job_id is not None:
                stmt = stmt.where(AIAnalysisJob.research_job_id == research_job_id)
            result = await session.execute(stmt.order_by(AIAnalysisJob.created_at.desc()))
            return [self._ai_analysis_job_to_dict(item) for item in result.scalars().all()]

    async def update_ai_analysis_job_status(
        self, analysis_job_id: int, status: str
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            job = await session.get(AIAnalysisJob, analysis_job_id)
            if job is None:
                return None
            job.status = status
            await session.flush()
            await session.refresh(job)
            return self._ai_analysis_job_to_dict(job)

    async def create_ai_analysis_result(
        self,
        *,
        analysis_job_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        async with get_session() as session:
            result = AIAnalysisResult(
                analysis_job_id=analysis_job_id,
                target_type=payload["target_type"],
                target_id=payload["target_id"],
                result_json=payload["result"],
                model=payload["model"],
                prompt_version=payload["prompt_version"],
            )
            session.add(result)
            await session.flush()
            await session.refresh(result)
            return self._ai_result_to_dict(result)

    async def list_ai_results(self, job_id: int | None = None) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(AIAnalysisResult)
            if job_id is not None:
                stmt = stmt.join(AIAnalysisJob, AIAnalysisResult.analysis_job_id == AIAnalysisJob.id).where(
                    AIAnalysisJob.research_job_id == job_id
                )
            result = await session.execute(stmt.order_by(AIAnalysisResult.created_at.desc()))
            return [self._ai_result_to_dict(item) for item in result.scalars().all()]

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

    async def _count(self, session, model, job_id: int) -> int:
        result = await session.execute(select(func.count()).select_from(model).where(model.job_id == job_id))
        return int(result.scalar() or 0)

    async def _count_by_platform(self, session, model, job_id: int) -> dict[str, int]:
        result = await session.execute(
            select(model.platform, func.count()).where(model.job_id == job_id).group_by(model.platform)
        )
        return {platform: int(count) for platform, count in result.all()}

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

    def _post_to_dict(self, post: ResearchPost) -> dict[str, Any]:
        return {
            "id": post.id,
            "job_id": post.job_id,
            "platform": post.platform,
            "platform_post_id": post.platform_post_id,
            "author_hash": post.author_hash,
            "title": post.title,
            "content": post.content,
            "url": post.url,
            "publish_time": post.publish_time,
            "engagement_json": post.engagement_json or {},
            "raw_record_id": post.raw_record_id,
            "created_at": post.created_at,
        }

    def _comment_to_dict(self, comment: ResearchComment) -> dict[str, Any]:
        return {
            "id": comment.id,
            "job_id": comment.job_id,
            "platform": comment.platform,
            "platform_comment_id": comment.platform_comment_id,
            "platform_post_id": comment.platform_post_id,
            "parent_comment_id": comment.parent_comment_id,
            "author_hash": comment.author_hash,
            "content": comment.content,
            "publish_time": comment.publish_time,
            "like_count": comment.like_count,
            "raw_record_id": comment.raw_record_id,
            "created_at": comment.created_at,
        }

    def _author_to_dict(self, author: ResearchAuthor) -> dict[str, Any]:
        return {
            "id": author.id,
            "job_id": author.job_id,
            "platform": author.platform,
            "author_hash": author.author_hash,
            "display_name_hash": author.display_name_hash,
            "profile_url_hash": author.profile_url_hash,
            "metrics_json": author.metrics_json or {},
            "created_at": author.created_at,
        }

    def _raw_record_to_dict(self, raw_record: RawRecord) -> dict[str, Any]:
        return {
            "id": raw_record.id,
            "job_id": raw_record.job_id,
            "platform": raw_record.platform,
            "source_type": raw_record.source_type,
            "source_id": raw_record.source_id,
            "source_url": raw_record.source_url,
            "payload_hash": raw_record.payload_hash,
            "payload_json": raw_record.payload_json or {},
            "fetched_at": raw_record.fetched_at,
            "parser_version": raw_record.parser_version,
        }

    def _ai_provider_to_dict(self, provider: AIProviderConfig) -> dict[str, Any]:
        return {
            "id": provider.id,
            "name": provider.name,
            "base_url": provider.base_url,
            "model": provider.model,
            "timeout": provider.timeout,
            "max_concurrency": provider.max_concurrency,
            "default_params": provider.default_params_json or {},
            "enabled": provider.enabled,
            "api_key_set": bool(provider.api_key_encrypted),
            "created_at": provider.created_at,
        }

    def _prompt_template_to_dict(self, prompt: AIPromptTemplate) -> dict[str, Any]:
        return {
            "id": prompt.id,
            "name": prompt.name,
            "task_type": prompt.task_type,
            "platform": prompt.platform,
            "prompt_text": prompt.prompt_text,
            "output_schema": prompt.output_schema_json or {},
            "version": prompt.version,
            "enabled": prompt.enabled,
            "created_at": prompt.created_at,
        }

    def _ai_analysis_job_to_dict(self, job: AIAnalysisJob) -> dict[str, Any]:
        return {
            "id": job.id,
            "research_job_id": job.research_job_id,
            "task_type": job.task_type,
            "scope": job.scope or {},
            "status": job.status,
            "provider_config_id": job.provider_config_id,
            "prompt_template_id": job.prompt_template_id,
            "created_at": job.created_at,
        }

    def _ai_result_to_dict(self, result: AIAnalysisResult) -> dict[str, Any]:
        return {
            "id": result.id,
            "analysis_job_id": result.analysis_job_id,
            "target_type": result.target_type,
            "target_id": result.target_id,
            "result_json": result.result_json or {},
            "model": result.model,
            "prompt_version": result.prompt_version,
            "created_at": result.created_at,
        }
