import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import bindparam, func, or_, select, text

from database.db_session import get_session
from research.creator_scoring import score_creator_candidate
from research.enums import (
    CRAWL_UNIT_FAILED,
    CRAWL_UNIT_PENDING,
    CRAWL_UNIT_RETRYING,
    CRAWL_UNIT_RUNNING,
    CRAWL_UNIT_TERMINAL_STATUSES,
)
from research.models import (
    AIAnalysisJob,
    AIAnalysisResult,
    AIProviderConfig,
    AIPromptTemplate,
    CrawlEvent,
    RawRecord,
    ResearchAuthProfile,
    ResearchAccountProfile,
    ResearchAccountRole,
    ResearchAuthor,
    ResearchBacktest,
    ResearchComment,
    ResearchCompetitorAccount,
    ResearchCreatorCandidate,
    ResearchCreatorDailySnapshot,
    ResearchCreatorProfile,
    ResearchCrawlUnit,
    ResearchEntityTag,
    ResearchGlobalSetting,
    ResearchGrowthProject,
    ResearchGrowthProjectCollectionPlan,
    ResearchGrowthProjectKeyword,
    ResearchAIKeywordSuggestionSession,
    ResearchAIHotspot,
    ResearchAIInsightRun,
    ResearchAITopicIdea,
    ResearchCompetitorCompositionSnapshot,
    ResearchContentSample,
    ResearchContentTracker,
    ResearchContentTrackingSnapshot,
    ResearchExtractedContentKeyword,
    ResearchJob,
    ResearchKeywordHeatSnapshot,
    ResearchKeywordSet,
    ResearchKeywordOpportunitySnapshot,
    ResearchMonitorPool,
    ResearchMonitorPoolCreator,
    ResearchOpportunityFeedback,
    ResearchPlatformCapability,
    ResearchPlatformRateLimit,
    ResearchPost,
    ResearchScenePack,
    ResearchScenePackKeyword,
    ResearchSearchIntent,
    ResearchSimilarContentCandidate,
    ResearchTagDefinition,
    ResearchTagGroup,
    ResearchVertical,
    ResearchWorkerHeartbeat,
)


def retry_backoff_seconds(attempt_count: int) -> int:
    if attempt_count <= 1:
        return 60
    if attempt_count == 2:
        return 300
    return 1800


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ResearchRepository:
    async def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            job = ResearchJob(**payload)
            session.add(job)
            await session.flush()
            await session.refresh(job)
            return self._job_to_dict(job)

    async def create_research_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.create_job(payload)

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

    async def get_database_collection_stats(self) -> dict[str, Any]:
        platform_tables = {
            "xhs": ["xhs_note", "xhs_note_comment", "xhs_creator"],
            "dy": ["douyin_aweme", "douyin_aweme_comment", "dy_creator"],
            "weibo": ["weibo_note", "weibo_note_comment", "weibo_creator"],
            "tieba": ["tieba_note", "tieba_comment", "tieba_creator"],
            "zhihu": ["zhihu_content", "zhihu_comment", "zhihu_creator"],
            "bili": ["bilibili_video", "bilibili_video_comment", "bilibili_up_info"],
            "ks": ["kuaishou_video", "kuaishou_video_comment"],
        }
        async with get_session() as session:
            research_posts = await self._count_all(session, ResearchPost)
            research_comments = await self._count_all(session, ResearchComment)
            raw_records = await self._count_all(session, RawRecord)
            creator_profiles = await self._count_all(session, ResearchCreatorProfile)
            entity_tags = await self._count_all(session, ResearchEntityTag)
            creator_candidates = await self._count_all(session, ResearchCreatorCandidate)
            by_platform = {
                "posts": await self._count_all_by_platform(session, ResearchPost),
                "comments": await self._count_all_by_platform(session, ResearchComment),
                "raw_records": await self._count_all_by_platform(session, RawRecord),
            }
            raw_platform_tables: dict[str, dict[str, int]] = {}
            for platform, tables in platform_tables.items():
                table_counts: dict[str, int] = {}
                for table in tables:
                    table_counts[table] = await self._count_table(session, table)
                raw_platform_tables[platform] = table_counts
            platform_totals = {
                platform: sum(table_counts.values())
                for platform, table_counts in raw_platform_tables.items()
            }
            return {
                "total_collected": research_posts + research_comments + raw_records,
                "research_posts": research_posts,
                "research_comments": research_comments,
                "raw_records": raw_records,
                "creator_profiles": creator_profiles,
                "entity_tags": entity_tags,
                "creator_candidates": creator_candidates,
                "by_platform": by_platform,
                "raw_platform_tables": raw_platform_tables,
                "raw_platform_totals": platform_totals,
            }

    async def create_crawl_units(self, units: list[dict[str, Any]]) -> dict[str, Any]:
        if not units:
            return {"created": 0, "existing": 0, "units": []}

        job_id = int(units[0]["job_id"])
        unit_keys = [unit["unit_key"] for unit in units]
        async with get_session() as session:
            existing_result = await session.execute(
                select(ResearchCrawlUnit.unit_key).where(
                    ResearchCrawlUnit.job_id == job_id,
                    ResearchCrawlUnit.unit_key.in_(unit_keys),
                )
            )
            existing_keys = set(existing_result.scalars().all())
            created = 0
            for unit in units:
                if unit["unit_key"] in existing_keys:
                    continue
                session.add(ResearchCrawlUnit(**unit))
                created += 1

            await session.flush()
            result = await session.execute(
                select(ResearchCrawlUnit)
                .where(
                    ResearchCrawlUnit.job_id == job_id,
                    ResearchCrawlUnit.unit_key.in_(unit_keys),
                )
                .order_by(ResearchCrawlUnit.id.asc())
            )
            rows = [self._crawl_unit_to_dict(unit) for unit in result.scalars().all()]
            return {
                "created": created,
                "existing": len(existing_keys),
                "units": rows,
            }

    async def list_crawl_units(
        self, job_id: int, status: str | None = None
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchCrawlUnit).where(ResearchCrawlUnit.job_id == job_id)
            if status:
                stmt = stmt.where(ResearchCrawlUnit.status == status)
            result = await session.execute(
                stmt.order_by(ResearchCrawlUnit.priority.asc(), ResearchCrawlUnit.id.asc())
            )
            return [self._crawl_unit_to_dict(unit) for unit in result.scalars().all()]

    async def claim_next_crawl_unit(
        self,
        *,
        worker_id: str,
        job_id: int | None = None,
        statuses: tuple[str, ...] = (CRAWL_UNIT_PENDING, CRAWL_UNIT_RETRYING),
        lock_timeout_seconds: int = 1800,
    ) -> dict[str, Any] | None:
        await self.release_stale_crawl_units(lock_timeout_seconds=lock_timeout_seconds)
        now = datetime.now(timezone.utc)
        async with get_session() as session:
            stmt = (
                select(ResearchCrawlUnit)
                .where(
                    ResearchCrawlUnit.status.in_(statuses),
                    or_(
                        ResearchCrawlUnit.scheduled_at.is_(None),
                        ResearchCrawlUnit.scheduled_at <= now,
                    ),
                )
                .order_by(ResearchCrawlUnit.priority.asc(), ResearchCrawlUnit.id.asc())
                .limit(1)
            )
            if job_id is not None:
                stmt = stmt.where(ResearchCrawlUnit.job_id == job_id)
            if session.bind and session.bind.dialect.name == "postgresql":
                stmt = stmt.with_for_update(skip_locked=True)
            result = await session.execute(stmt)
            unit = result.scalar_one_or_none()
            if unit is None:
                return None

            unit.status = CRAWL_UNIT_RUNNING
            unit.locked_by = worker_id
            unit.locked_at = now
            unit.started_at = now
            unit.attempt_count = int(unit.attempt_count or 0) + 1
            await session.flush()
            await session.refresh(unit)
            return self._crawl_unit_to_dict(unit)

    async def update_crawl_unit_status(
        self,
        unit_id: int,
        status: str,
        *,
        last_error: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        async with get_session() as session:
            unit = await session.get(ResearchCrawlUnit, unit_id)
            if unit is None:
                return None
            unit.status = status
            unit.last_error = last_error
            if status == CRAWL_UNIT_RETRYING:
                unit.scheduled_at = now + timedelta(
                    seconds=retry_backoff_seconds(int(unit.attempt_count or 1))
                )
                unit.locked_by = None
                unit.locked_at = None
            if status in CRAWL_UNIT_TERMINAL_STATUSES:
                unit.finished_at = now
                unit.locked_by = None
                unit.locked_at = None
            await session.flush()
            await session.refresh(unit)
            return self._crawl_unit_to_dict(unit)

    async def release_stale_crawl_units(
        self, *, lock_timeout_seconds: int = 1800
    ) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=lock_timeout_seconds)
        async with get_session() as session:
            result = await session.execute(
                select(ResearchCrawlUnit).where(
                    ResearchCrawlUnit.status == CRAWL_UNIT_RUNNING,
                    ResearchCrawlUnit.locked_at.is_not(None),
                    ResearchCrawlUnit.locked_at < cutoff,
                )
            )
            stale_units = result.scalars().all()
            for unit in stale_units:
                unit.status = (
                    CRAWL_UNIT_FAILED
                    if int(unit.attempt_count or 0) >= int(unit.max_attempts or 1)
                    else CRAWL_UNIT_RETRYING
                )
                unit.locked_by = None
                unit.locked_at = None
                unit.last_error = "Worker lock expired"
                if unit.status == CRAWL_UNIT_RETRYING:
                    unit.scheduled_at = datetime.now(timezone.utc)
                else:
                    unit.finished_at = datetime.now(timezone.utc)
            await session.flush()
            return len(stale_units)

    async def get_crawl_unit_summary(self, job_id: int) -> dict[str, int]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchCrawlUnit.status, func.count())
                .where(ResearchCrawlUnit.job_id == job_id)
                .group_by(ResearchCrawlUnit.status)
            )
            return {status: int(count) for status, count in result.all()}

    async def all_crawl_units_finished(self, job_id: int) -> bool:
        summary = await self.get_crawl_unit_summary(job_id)
        total = sum(summary.values())
        finished = sum(
            count
            for status, count in summary.items()
            if status in CRAWL_UNIT_TERMINAL_STATUSES
        )
        return total > 0 and total == finished

    async def has_active_crawl_units(self, job_id: int) -> bool:
        async with get_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(ResearchCrawlUnit)
                .where(
                    ResearchCrawlUnit.job_id == job_id,
                    ResearchCrawlUnit.status.notin_(CRAWL_UNIT_TERMINAL_STATUSES),
                )
            )
            return int(result.scalar() or 0) > 0

    async def upsert_worker_heartbeat(
        self,
        *,
        worker_id: str,
        hostname: str,
        pid: int,
        status: str,
        current_unit_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        started_at: datetime | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        async with get_session() as session:
            result = await session.execute(
                select(ResearchWorkerHeartbeat).where(
                    ResearchWorkerHeartbeat.worker_id == worker_id
                )
            )
            heartbeat = result.scalar_one_or_none()
            if heartbeat is None:
                heartbeat = ResearchWorkerHeartbeat(
                    worker_id=worker_id,
                    hostname=hostname,
                    pid=pid,
                    status=status,
                    current_unit_id=current_unit_id,
                    metadata_json=metadata or {},
                    started_at=started_at or now,
                    last_seen_at=now,
                )
                session.add(heartbeat)
            else:
                heartbeat.hostname = hostname
                heartbeat.pid = pid
                heartbeat.status = status
                heartbeat.current_unit_id = current_unit_id
                heartbeat.metadata_json = metadata or {}
                heartbeat.last_seen_at = now
            await session.flush()
            await session.refresh(heartbeat)
            return self._worker_heartbeat_to_dict(heartbeat)

    async def list_worker_heartbeats(self, *, stale_after_seconds: int = 60) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
        async with get_session() as session:
            result = await session.execute(
                select(ResearchWorkerHeartbeat).order_by(
                    ResearchWorkerHeartbeat.last_seen_at.desc()
                )
            )
            workers = []
            for heartbeat in result.scalars().all():
                payload = self._worker_heartbeat_to_dict(heartbeat)
                payload["online"] = _as_utc(heartbeat.last_seen_at) >= cutoff
                workers.append(payload)
            return workers

    async def upsert_platform_rate_limit(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchPlatformRateLimit).where(
                    ResearchPlatformRateLimit.platform == payload["platform"]
                )
            )
            rate_limit = result.scalar_one_or_none()
            if rate_limit is None:
                rate_limit = ResearchPlatformRateLimit(**payload)
                session.add(rate_limit)
            else:
                for key, value in payload.items():
                    if hasattr(rate_limit, key):
                        setattr(rate_limit, key, value)
            await session.flush()
            await session.refresh(rate_limit)
            return self._platform_rate_limit_to_dict(rate_limit)

    async def list_platform_rate_limits(self) -> list[dict[str, Any]]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchPlatformRateLimit).order_by(ResearchPlatformRateLimit.platform.asc())
            )
            return [self._platform_rate_limit_to_dict(item) for item in result.scalars().all()]

    async def get_platform_rate_limit(self, platform: str) -> dict[str, Any] | None:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchPlatformRateLimit).where(
                    ResearchPlatformRateLimit.platform == platform
                )
            )
            item = result.scalar_one_or_none()
            return self._platform_rate_limit_to_dict(item) if item else None

    async def upsert_platform_capability(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchPlatformCapability).where(
                    ResearchPlatformCapability.platform == payload["platform"]
                )
            )
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchPlatformCapability(**payload)
                session.add(item)
            else:
                for key, value in payload.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._platform_capability_to_dict(item)

    async def list_platform_capabilities(self) -> list[dict[str, Any]]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchPlatformCapability).order_by(
                    ResearchPlatformCapability.platform.asc()
                )
            )
            return [self._platform_capability_to_dict(item) for item in result.scalars().all()]

    async def get_platform_capability(self, platform: str) -> dict[str, Any] | None:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchPlatformCapability).where(
                    ResearchPlatformCapability.platform == platform
                )
            )
            item = result.scalar_one_or_none()
            return self._platform_capability_to_dict(item) if item else None

    async def get_global_setting(self, key: str) -> dict[str, Any] | None:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchGlobalSetting).where(ResearchGlobalSetting.key == key)
            )
            item = result.scalar_one_or_none()
            return self._global_setting_to_dict(item) if item else None

    async def upsert_global_setting(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchGlobalSetting).where(ResearchGlobalSetting.key == key)
            )
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchGlobalSetting(key=key, value_json=value)
                session.add(item)
            else:
                item.value_json = value
            await session.flush()
            await session.refresh(item)
            return self._global_setting_to_dict(item)

    async def create_keyword_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchKeywordSet(**payload)
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._keyword_set_to_dict(item)

    async def list_keyword_sets(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchKeywordSet)
            if enabled_only:
                stmt = stmt.where(ResearchKeywordSet.enabled.is_(True))
            result = await session.execute(stmt.order_by(ResearchKeywordSet.id.desc()))
            return [self._keyword_set_to_dict(item) for item in result.scalars().all()]

    async def update_keyword_set(
        self, keyword_set_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchKeywordSet, keyword_set_id)
            if item is None:
                return None
            for key, value in payload.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._keyword_set_to_dict(item)

    async def create_vertical(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchVertical(**payload)
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._vertical_to_dict(item)

    async def upsert_vertical_by_code(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchVertical).where(ResearchVertical.code == payload["code"])
            )
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchVertical(**payload)
                session.add(item)
            else:
                for key, value in payload.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._vertical_to_dict(item)

    async def list_verticals(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchVertical)
            if enabled_only:
                stmt = stmt.where(ResearchVertical.enabled.is_(True))
            result = await session.execute(stmt.order_by(ResearchVertical.name.asc()))
            return [self._vertical_to_dict(item) for item in result.scalars().all()]

    async def update_vertical(self, vertical_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchVertical, vertical_id)
            if item is None:
                return None
            for key, value in payload.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._vertical_to_dict(item)

    async def create_tag_group(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchTagGroup(**payload)
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._tag_group_to_dict(item)

    async def upsert_tag_group_by_name(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchTagGroup).where(
                    ResearchTagGroup.vertical_id == payload["vertical_id"],
                    ResearchTagGroup.name == payload["name"],
                )
            )
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchTagGroup(**payload)
                session.add(item)
            else:
                for key, value in payload.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._tag_group_to_dict(item)

    async def list_tag_groups(
        self, *, vertical_id: int | None = None, enabled_only: bool = False
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchTagGroup)
            if vertical_id is not None:
                stmt = stmt.where(ResearchTagGroup.vertical_id == vertical_id)
            if enabled_only:
                stmt = stmt.where(ResearchTagGroup.enabled.is_(True))
            result = await session.execute(
                stmt.order_by(ResearchTagGroup.sort_order.asc(), ResearchTagGroup.id.asc())
            )
            return [self._tag_group_to_dict(item) for item in result.scalars().all()]

    async def update_tag_group(self, group_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchTagGroup, group_id)
            if item is None:
                return None
            for key, value in payload.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._tag_group_to_dict(item)

    async def create_tag_definition(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchTagDefinition(**payload)
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._tag_definition_to_dict(item)

    async def upsert_tag_definition_by_name(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchTagDefinition).where(
                    ResearchTagDefinition.vertical_id == payload["vertical_id"],
                    ResearchTagDefinition.group_id == payload["group_id"],
                    ResearchTagDefinition.tag_name == payload["tag_name"],
                )
            )
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchTagDefinition(**payload)
                session.add(item)
            else:
                for key, value in payload.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._tag_definition_to_dict(item)

    async def list_tag_definitions(
        self, *, vertical_id: int | None = None, enabled_only: bool = False
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchTagDefinition)
            if vertical_id is not None:
                stmt = stmt.where(ResearchTagDefinition.vertical_id == vertical_id)
            if enabled_only:
                stmt = stmt.where(ResearchTagDefinition.enabled.is_(True))
            result = await session.execute(
                stmt.order_by(ResearchTagDefinition.vertical_id.asc(), ResearchTagDefinition.id.asc())
            )
            return [self._tag_definition_to_dict(item) for item in result.scalars().all()]

    async def update_tag_definition(
        self, tag_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchTagDefinition, tag_id)
            if item is None:
                return None
            for key, value in payload.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._tag_definition_to_dict(item)

    async def upsert_entity_tag(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = select(ResearchEntityTag).where(
                ResearchEntityTag.entity_type == payload["entity_type"],
                ResearchEntityTag.entity_id == payload["entity_id"],
                ResearchEntityTag.platform == payload["platform"],
                ResearchEntityTag.vertical_id == payload["vertical_id"],
                ResearchEntityTag.tag_id == payload["tag_id"],
                ResearchEntityTag.source == payload["source"],
                ResearchEntityTag.analysis_version == payload.get("analysis_version", "v1"),
            )
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchEntityTag(**payload)
                session.add(item)
            else:
                item.confidence = payload["confidence"]
                item.evidence_json = payload.get("evidence_json") or {}
            await session.flush()
            await session.refresh(item)
            return self._entity_tag_to_dict(item)

    async def bulk_upsert_entity_tags(self, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [await self.upsert_entity_tag(payload) for payload in payloads]

    async def list_entity_tags(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        platform: str | None = None,
        vertical_id: int | None = None,
        tag_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchEntityTag)
            if entity_type:
                stmt = stmt.where(ResearchEntityTag.entity_type == entity_type)
            if entity_id:
                stmt = stmt.where(ResearchEntityTag.entity_id == entity_id)
            if platform:
                stmt = stmt.where(ResearchEntityTag.platform == platform)
            if vertical_id is not None:
                stmt = stmt.where(ResearchEntityTag.vertical_id == vertical_id)
            if tag_ids:
                stmt = stmt.where(ResearchEntityTag.tag_id.in_(tag_ids))
            result = await session.execute(stmt.order_by(ResearchEntityTag.confidence.desc()))
            return [self._entity_tag_to_dict(item) for item in result.scalars().all()]

    async def list_entity_tags_for_entities(
        self,
        *,
        entity_type: str,
        entity_ids: list[str],
        platform: str | None = None,
        vertical_id: int | None = None,
        tag_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        if not entity_ids:
            return []
        async with get_session() as session:
            stmt = select(ResearchEntityTag).where(
                ResearchEntityTag.entity_type == entity_type,
                ResearchEntityTag.entity_id.in_(entity_ids),
            )
            if platform:
                stmt = stmt.where(ResearchEntityTag.platform == platform)
            if vertical_id is not None:
                stmt = stmt.where(ResearchEntityTag.vertical_id == vertical_id)
            if tag_ids:
                stmt = stmt.where(ResearchEntityTag.tag_id.in_(tag_ids))
            result = await session.execute(stmt.order_by(ResearchEntityTag.confidence.desc()))
            return [self._entity_tag_to_dict(item) for item in result.scalars().all()]

    async def upsert_creator_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = select(ResearchCreatorProfile).where(
                ResearchCreatorProfile.platform == payload["platform"],
                ResearchCreatorProfile.creator_id == payload["creator_id"],
            )
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchCreatorProfile(**payload)
                session.add(item)
            else:
                for key, value in payload.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._creator_profile_to_dict(item)

    async def list_creator_profiles(
        self, *, platforms: list[str] | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchCreatorProfile)
            if platforms:
                stmt = stmt.where(ResearchCreatorProfile.platform.in_(platforms))
            stmt = stmt.order_by(ResearchCreatorProfile.updated_at.desc())
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [self._creator_profile_to_dict(item) for item in result.scalars().all()]

    async def get_creator_profile(self, platform: str, creator_id: str) -> dict[str, Any] | None:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchCreatorProfile).where(
                    ResearchCreatorProfile.platform == platform,
                    ResearchCreatorProfile.creator_id == creator_id,
                )
            )
            item = result.scalar_one_or_none()
            return self._creator_profile_to_dict(item) if item else None

    async def upsert_creator_daily_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = select(ResearchCreatorDailySnapshot).where(
                ResearchCreatorDailySnapshot.platform == payload["platform"],
                ResearchCreatorDailySnapshot.creator_id == payload["creator_id"],
                ResearchCreatorDailySnapshot.snapshot_date == payload["snapshot_date"],
            )
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchCreatorDailySnapshot(**payload)
                session.add(item)
            else:
                for key, value in payload.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._creator_daily_snapshot_to_dict(item)

    async def list_creator_daily_snapshots(
        self, *, platform: str | None = None, creator_id: str | None = None
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchCreatorDailySnapshot)
            if platform:
                stmt = stmt.where(ResearchCreatorDailySnapshot.platform == platform)
            if creator_id:
                stmt = stmt.where(ResearchCreatorDailySnapshot.creator_id == creator_id)
            result = await session.execute(
                stmt.order_by(ResearchCreatorDailySnapshot.snapshot_date.desc())
            )
            return [self._creator_daily_snapshot_to_dict(item) for item in result.scalars().all()]

    async def upsert_creator_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload.setdefault("pool_name", "default")
        async with get_session() as session:
            stmt = select(ResearchCreatorCandidate).where(
                ResearchCreatorCandidate.platform == payload["platform"],
                ResearchCreatorCandidate.creator_id == payload["creator_id"],
                ResearchCreatorCandidate.pool_name == payload["pool_name"],
            )
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchCreatorCandidate(**payload)
                session.add(item)
            else:
                for key, value in payload.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._creator_candidate_to_dict(item)

    async def list_creator_candidates(
        self,
        *,
        pool_name: str | None = None,
        platform: str | None = None,
        vertical_id: int | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchCreatorCandidate)
            if pool_name:
                stmt = stmt.where(ResearchCreatorCandidate.pool_name == pool_name)
            if platform:
                stmt = stmt.where(ResearchCreatorCandidate.platform == platform)
            if vertical_id is not None:
                stmt = stmt.where(ResearchCreatorCandidate.vertical_id == vertical_id)
            result = await session.execute(
                stmt.order_by(
                    ResearchCreatorCandidate.match_score.desc(),
                    ResearchCreatorCandidate.updated_at.desc(),
                )
            )
            return [self._creator_candidate_to_dict(item) for item in result.scalars().all()]

    async def create_search_intent(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchSearchIntent(**payload)
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._search_intent_to_dict(item)

    async def create_scene_pack(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchScenePack).where(
                    ResearchScenePack.vertical_id == payload["vertical_id"],
                    ResearchScenePack.name == payload["name"],
                )
            )
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchScenePack(**payload)
                session.add(item)
            else:
                for key, value in payload.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
                item.enabled = True
            await session.flush()
            await session.refresh(item)
            return self._scene_pack_to_dict(item)

    async def list_scene_packs(
        self, vertical_id: int | None = None, enabled_only: bool = False
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchScenePack)
            if vertical_id is not None:
                stmt = stmt.where(ResearchScenePack.vertical_id == vertical_id)
            if enabled_only:
                stmt = stmt.where(ResearchScenePack.enabled.is_(True))
            result = await session.execute(stmt.order_by(ResearchScenePack.id.asc()))
            return [self._scene_pack_to_dict(item) for item in result.scalars().all()]

    async def get_scene_pack(self, scene_pack_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchScenePack, scene_pack_id)
            return self._scene_pack_to_dict(item) if item else None

    async def update_scene_pack(
        self, scene_pack_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchScenePack, scene_pack_id)
            if item is None:
                return None
            for key, value in payload.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._scene_pack_to_dict(item)

    async def delete_scene_pack(self, scene_pack_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchScenePack, scene_pack_id)
            if item is None:
                return None
            keyword_count = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(ResearchScenePackKeyword)
                        .where(ResearchScenePackKeyword.scene_pack_id == scene_pack_id)
                    )
                ).scalar()
                or 0
            )
            if keyword_count:
                return {
                    "deleted": False,
                    "reason": "scene_pack_has_keywords",
                    "keyword_count": keyword_count,
                }
            await session.delete(item)
            await session.flush()
            return {"deleted": True, "id": scene_pack_id}

    async def create_scene_pack_keyword(self, payload: dict[str, Any]) -> dict[str, Any]:
        item_payload = {
            "scene_pack_id": payload["scene_pack_id"],
            "keyword": payload["keyword"],
            "keyword_type": payload["keyword_type"],
            "platform": payload.get("platform"),
            "weight": payload.get("weight", 1.0),
            "reason": payload.get("reason"),
            "usage_flags_json": payload.get("usage_flags") or [],
            "platform_overrides_json": payload.get("platform_overrides") or {},
            "enabled": payload.get("enabled", True),
        }
        async with get_session() as session:
            result = await session.execute(
                select(ResearchScenePackKeyword).where(
                    ResearchScenePackKeyword.scene_pack_id == item_payload["scene_pack_id"],
                    ResearchScenePackKeyword.keyword == item_payload["keyword"],
                    ResearchScenePackKeyword.keyword_type == item_payload["keyword_type"],
                )
            )
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchScenePackKeyword(**item_payload)
                session.add(item)
            else:
                for key, value in item_payload.items():
                    setattr(item, key, value)
                item.enabled = True
            await session.flush()
            await session.refresh(item)
            return self._scene_pack_keyword_to_dict(item)

    async def update_scene_pack_keyword(
        self, keyword_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        mapping = {
            "scene_pack_id": "scene_pack_id",
            "keyword": "keyword",
            "keyword_type": "keyword_type",
            "platform": "platform",
            "weight": "weight",
            "reason": "reason",
            "usage_flags": "usage_flags_json",
            "platform_overrides": "platform_overrides_json",
            "enabled": "enabled",
        }
        async with get_session() as session:
            item = await session.get(ResearchScenePackKeyword, keyword_id)
            if item is None:
                return None
            for source, target in mapping.items():
                if source in payload:
                    setattr(item, target, payload[source])
            await session.flush()
            await session.refresh(item)
            return self._scene_pack_keyword_to_dict(item)

    async def delete_scene_pack_keyword(self, keyword_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchScenePackKeyword, keyword_id)
            if item is None:
                return None
            await session.delete(item)
            await session.flush()
            return {"deleted": True, "id": keyword_id}

    async def list_scene_pack_keywords(
        self,
        scene_pack_ids: list[int] | None = None,
        enabled_only: bool = False,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchScenePackKeyword)
            if scene_pack_ids:
                stmt = stmt.where(ResearchScenePackKeyword.scene_pack_id.in_(scene_pack_ids))
            if enabled_only:
                stmt = stmt.where(ResearchScenePackKeyword.enabled.is_(True))
            result = await session.execute(stmt.order_by(ResearchScenePackKeyword.id.asc()))
            return [self._scene_pack_keyword_to_dict(item) for item in result.scalars().all()]

    async def create_growth_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchGrowthProject).where(
                    ResearchGrowthProject.name == payload["name"]
                )
            )
            item = result.scalar_one_or_none()
            values = {
                "primary_goal": payload.get("primary_goal") or "topic_discovery",
                "scene_pack_id": payload.get("scene_pack_id"),
                "platforms": payload.get("platforms") or [],
                "project_status": payload.get("project_status") or "active",
                "collection_status": payload.get("collection_status") or "not_started",
                "comment_collection_enabled": payload.get("comment_collection_enabled", True),
                "refresh_cadence": payload.get("refresh_cadence") or "off",
                "custom_interval_value": payload.get("custom_interval_value"),
                "custom_interval_unit": payload.get("custom_interval_unit"),
                "sample_status": payload.get("sample_status") or "sample_insufficient",
                "recommended_action": payload.get("recommended_action") or "start_collection",
                "archived": payload.get("archived", False),
            }
            if item is None:
                item = ResearchGrowthProject(name=payload["name"], **values)
                session.add(item)
            else:
                for key, value in values.items():
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._growth_project_to_dict(item)

    async def list_growth_project_records(
        self, *, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchGrowthProject)
            if not include_archived:
                stmt = stmt.where(ResearchGrowthProject.archived.is_(False))
            result = await session.execute(stmt.order_by(ResearchGrowthProject.updated_at.desc()))
            return [self._growth_project_to_dict(item) for item in result.scalars().all()]

    async def get_growth_project_record(self, project_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchGrowthProject, project_id)
            return self._growth_project_to_dict(item) if item else None

    async def update_growth_project(
        self, project_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchGrowthProject, project_id)
            if item is None:
                return None
            for key, value in payload.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._growth_project_to_dict(item)

    async def create_growth_project_keyword(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchGrowthProjectKeyword).where(
                    ResearchGrowthProjectKeyword.project_id == payload["project_id"],
                    ResearchGrowthProjectKeyword.keyword == payload["keyword"],
                    ResearchGrowthProjectKeyword.keyword_type == payload["keyword_type"],
                )
            )
            item = result.scalar_one_or_none()
            values = {
                "scene_pack_id": payload.get("scene_pack_id"),
                "source": payload.get("source") or "scene_pack",
                "status": payload.get("status") or "active",
            }
            if item is None:
                item = ResearchGrowthProjectKeyword(
                    project_id=payload["project_id"],
                    keyword=payload["keyword"],
                    keyword_type=payload["keyword_type"],
                    **values,
                )
                session.add(item)
            else:
                for key, value in values.items():
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._growth_project_keyword_to_dict(item)

    async def list_growth_project_keywords(
        self, project_id: int, status: str | None = None
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchGrowthProjectKeyword).where(
                ResearchGrowthProjectKeyword.project_id == project_id
            )
            if status:
                stmt = stmt.where(ResearchGrowthProjectKeyword.status == status)
            result = await session.execute(stmt.order_by(ResearchGrowthProjectKeyword.id.asc()))
            return [self._growth_project_keyword_to_dict(item) for item in result.scalars().all()]

    async def update_growth_project_keyword(
        self, keyword_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchGrowthProjectKeyword, keyword_id)
            if item is None:
                return None
            for key, value in payload.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._growth_project_keyword_to_dict(item)

    async def delete_growth_project_keywords(self, project_id: int) -> dict[str, Any]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchGrowthProjectKeyword).where(
                    ResearchGrowthProjectKeyword.project_id == project_id
                )
            )
            items = list(result.scalars().all())
            for item in items:
                await session.delete(item)
            await session.flush()
            return {"deleted": len(items), "project_id": project_id}

    async def create_growth_project_collection_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchGrowthProjectCollectionPlan).where(
                    ResearchGrowthProjectCollectionPlan.project_id == payload["project_id"],
                    ResearchGrowthProjectCollectionPlan.platform == payload["platform"],
                    ResearchGrowthProjectCollectionPlan.collection_mode
                    == (payload.get("collection_mode") or "search"),
                )
            )
            item = result.scalar_one_or_none()
            values = {
                "keyword_scope": payload.get("keyword_scope") or "active",
                "enabled": payload.get("enabled", True),
                "schedule_mode": payload.get("schedule_mode") or "manual",
                "schedule_interval_minutes": payload.get("schedule_interval_minutes"),
            }
            if item is None:
                item = ResearchGrowthProjectCollectionPlan(
                    project_id=payload["project_id"],
                    platform=payload["platform"],
                    collection_mode=payload.get("collection_mode") or "search",
                    **values,
                )
                session.add(item)
            else:
                for key, value in values.items():
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._growth_project_collection_plan_to_dict(item)

    async def list_growth_project_collection_plans(
        self, project_id: int
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchGrowthProjectCollectionPlan)
                .where(ResearchGrowthProjectCollectionPlan.project_id == project_id)
                .order_by(ResearchGrowthProjectCollectionPlan.id.asc())
            )
            return [
                self._growth_project_collection_plan_to_dict(item)
                for item in result.scalars().all()
            ]

    async def update_growth_project_collection_plans(
        self, project_id: int, payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchGrowthProjectCollectionPlan).where(
                    ResearchGrowthProjectCollectionPlan.project_id == project_id
                )
            )
            plans = list(result.scalars().all())
            for plan in plans:
                for key, value in payload.items():
                    if hasattr(plan, key):
                        setattr(plan, key, value)
            await session.flush()
            return [self._growth_project_collection_plan_to_dict(item) for item in plans]

    async def create_ai_keyword_suggestion_session(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        item_payload = {
            "vertical_id": payload.get("vertical_id"),
            "scene_pack_id": payload.get("scene_pack_id"),
            "seed_keywords_json": payload.get("seed_keywords") or [],
            "audience_context": payload.get("audience_context"),
            "status": payload.get("status", "pending"),
            "provider_config_id": payload.get("provider_config_id"),
            "suggestions_json": payload.get("suggestions") or [],
            "selected_keywords_json": payload.get("selected_keywords") or [],
            "error_message": payload.get("error_message"),
        }
        async with get_session() as session:
            item = ResearchAIKeywordSuggestionSession(**item_payload)
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._ai_keyword_suggestion_session_to_dict(item)

    async def list_ai_keyword_suggestion_sessions(
        self,
        *,
        status: str | None = None,
        vertical_id: int | None = None,
        scene_pack_id: int | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchAIKeywordSuggestionSession)
            if status:
                stmt = stmt.where(ResearchAIKeywordSuggestionSession.status == status)
            if vertical_id is not None:
                stmt = stmt.where(ResearchAIKeywordSuggestionSession.vertical_id == vertical_id)
            if scene_pack_id is not None:
                stmt = stmt.where(
                    ResearchAIKeywordSuggestionSession.scene_pack_id == scene_pack_id
                )
            result = await session.execute(
                stmt.order_by(ResearchAIKeywordSuggestionSession.id.desc())
            )
            return [
                self._ai_keyword_suggestion_session_to_dict(item)
                for item in result.scalars().all()
            ]

    async def approve_ai_keyword_suggestion_session(
        self, suggestion_id: int
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchAIKeywordSuggestionSession, suggestion_id)
            if item is None:
                return None
            created_keywords: list[dict[str, Any]] = []
            for suggestion in item.suggestions_json or []:
                keyword = suggestion.get("keyword") or suggestion.get("term")
                if not keyword or item.scene_pack_id is None:
                    continue
                row = ResearchScenePackKeyword(
                    scene_pack_id=item.scene_pack_id,
                    keyword=str(keyword),
                    keyword_type=suggestion.get("keyword_type", "secondary"),
                    platform=suggestion.get("platform"),
                    weight=float(suggestion.get("weight", 1.0)),
                    reason=suggestion.get("reason"),
                    usage_flags_json=suggestion.get("usage_flags")
                    or ["creator_discovery", "content_tracking", "keyword_heat"],
                    enabled=True,
                )
                session.add(row)
                await session.flush()
                await session.refresh(row)
                created_keywords.append(self._scene_pack_keyword_to_dict(row))
            item.status = "approved"
            item.selected_keywords_json = item.suggestions_json or []
            await session.flush()
            await session.refresh(item)
            result = self._ai_keyword_suggestion_session_to_dict(item)
            result["created_keywords"] = created_keywords
            return result

    async def reject_ai_keyword_suggestion_session(
        self, suggestion_id: int, *, reason: str | None = None
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchAIKeywordSuggestionSession, suggestion_id)
            if item is None:
                return None
            item.status = "rejected"
            item.error_message = reason
            await session.flush()
            await session.refresh(item)
            return self._ai_keyword_suggestion_session_to_dict(item)

    async def create_monitor_pool(self, payload: dict[str, Any]) -> dict[str, Any]:
        item_payload = self._monitor_pool_payload(payload)
        async with get_session() as session:
            item = ResearchMonitorPool(**item_payload)
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._monitor_pool_to_dict(item)

    async def get_monitor_pool(self, pool_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchMonitorPool, pool_id)
            return self._monitor_pool_to_dict(item) if item else None

    async def list_monitor_pools(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchMonitorPool)
            if enabled_only:
                stmt = stmt.where(ResearchMonitorPool.enabled.is_(True))
            result = await session.execute(stmt.order_by(ResearchMonitorPool.id.desc()))
            return [self._monitor_pool_to_dict(item) for item in result.scalars().all()]

    async def update_monitor_pool(
        self, pool_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchMonitorPool, pool_id)
            if item is None:
                return None
            for key, value in self._monitor_pool_payload(payload, partial=True).items():
                if hasattr(item, key):
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._monitor_pool_to_dict(item)

    async def add_monitor_pool_creators(
        self, pool_id: int, creators: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            results: list[dict[str, Any]] = []
            for creator in creators:
                platform = creator["platform"]
                creator_id = creator["creator_id"]
                stmt = select(ResearchMonitorPoolCreator).where(
                    ResearchMonitorPoolCreator.pool_id == pool_id,
                    ResearchMonitorPoolCreator.platform == platform,
                    ResearchMonitorPoolCreator.creator_id == creator_id,
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing is None:
                    existing = ResearchMonitorPoolCreator(
                        pool_id=pool_id,
                        platform=platform,
                        creator_id=creator_id,
                    )
                    session.add(existing)
                existing.display_name = creator.get("display_name")
                existing.source = creator.get("source", "manual")
                existing.match_score = creator.get("match_score")
                existing.notes = creator.get("notes")
                existing.enabled = creator.get("enabled", True)
                await session.flush()
                await session.refresh(existing)
                results.append(self._monitor_pool_creator_to_dict(existing))
            return results

    async def list_monitor_pool_creators(
        self, pool_id: int, enabled_only: bool = False
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchMonitorPoolCreator).where(
                ResearchMonitorPoolCreator.pool_id == pool_id
            )
            if enabled_only:
                stmt = stmt.where(ResearchMonitorPoolCreator.enabled.is_(True))
            result = await session.execute(stmt.order_by(ResearchMonitorPoolCreator.id.asc()))
            return [self._monitor_pool_creator_to_dict(item) for item in result.scalars().all()]

    async def upsert_content_sample(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = select(ResearchContentSample).where(
                ResearchContentSample.platform == payload["platform"],
                ResearchContentSample.content_id == payload["content_id"],
            )
            item = (await session.execute(stmt)).scalar_one_or_none()
            if item is None:
                item = ResearchContentSample(**payload)
                session.add(item)
            else:
                for key, value in payload.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._content_sample_to_dict(item)

    async def create_extracted_content_keywords(
        self, payloads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            rows = []
            for payload in payloads:
                item = ResearchExtractedContentKeyword(
                    content_sample_id=payload["content_sample_id"],
                    keyword=payload["keyword"],
                    keyword_type=payload.get("keyword_type", "detected"),
                    score=payload.get("score", 0.0),
                    source=payload.get("source", "rule"),
                    evidence_json=payload.get("evidence") or {},
                )
                session.add(item)
                rows.append(item)
            await session.flush()
            for item in rows:
                await session.refresh(item)
            return [self._extracted_content_keyword_to_dict(item) for item in rows]

    async def create_similar_content_candidates(
        self, payloads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            rows = []
            for payload in payloads:
                item = ResearchSimilarContentCandidate(
                    source_content_sample_id=payload["source_content_sample_id"],
                    platform=payload["platform"],
                    content_id=payload["content_id"],
                    creator_id=payload.get("creator_id"),
                    similarity_score=payload.get("similarity_score", 0.0),
                    reason=payload.get("reason"),
                    evidence_json=payload.get("evidence") or {},
                    status=payload.get("status", "candidate"),
                )
                session.add(item)
                rows.append(item)
            await session.flush()
            for item in rows:
                await session.refresh(item)
            return [self._similar_content_candidate_to_dict(item) for item in rows]

    async def create_content_tracker(self, payload: dict[str, Any]) -> dict[str, Any]:
        item_payload = self._content_tracker_payload(payload)
        async with get_session() as session:
            item = ResearchContentTracker(**item_payload)
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._content_tracker_to_dict(item)

    async def list_content_trackers(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchContentTracker)
            if enabled_only:
                stmt = stmt.where(ResearchContentTracker.enabled.is_(True))
            result = await session.execute(stmt.order_by(ResearchContentTracker.id.desc()))
            return [self._content_tracker_to_dict(item) for item in result.scalars().all()]

    async def get_content_tracker(self, tracker_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchContentTracker, tracker_id)
            return self._content_tracker_to_dict(item) if item else None

    async def create_content_tracking_snapshot(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchContentTrackingSnapshot(
                tracker_id=payload["tracker_id"],
                snapshot_date=payload["snapshot_date"],
                platform=payload.get("platform"),
                keyword_distribution_json=_json_safe(payload.get("keyword_distribution") or {}),
                tag_distribution_json=_json_safe(payload.get("tag_distribution") or {}),
                content_type_distribution_json=_json_safe(payload.get("content_type_distribution") or {}),
                publish_time_distribution_json=_json_safe(payload.get("publish_time_distribution") or {}),
                hot_post_rate=payload.get("hot_post_rate", 0.0),
                total_content_count=payload.get("total_content_count", 0),
                evidence_json=_json_safe(payload.get("evidence") or {}),
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._content_tracking_snapshot_to_dict(item)

    async def list_content_tracking_snapshots(
        self,
        *,
        tracker_id: int | None = None,
        platform: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchContentTrackingSnapshot)
            if tracker_id is not None:
                stmt = stmt.where(ResearchContentTrackingSnapshot.tracker_id == tracker_id)
            if platform is not None:
                stmt = stmt.where(ResearchContentTrackingSnapshot.platform == platform)
            stmt = stmt.order_by(
                ResearchContentTrackingSnapshot.snapshot_date.desc(),
                ResearchContentTrackingSnapshot.id.desc(),
            )
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [
                self._content_tracking_snapshot_to_dict(item)
                for item in result.scalars().all()
            ]

    async def upsert_keyword_heat_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = select(ResearchKeywordHeatSnapshot).where(
                ResearchKeywordHeatSnapshot.keyword == payload["keyword"],
                ResearchKeywordHeatSnapshot.platform == payload["platform"],
                ResearchKeywordHeatSnapshot.snapshot_date == payload["snapshot_date"],
            )
            item = (await session.execute(stmt)).scalar_one_or_none()
            item_payload = {
                "vertical_id": payload.get("vertical_id"),
                "scene_pack_id": payload.get("scene_pack_id"),
                "keyword": payload["keyword"],
                "platform": payload["platform"],
                "snapshot_date": payload["snapshot_date"],
                "heat_score": payload.get("heat_score", 0.0),
                "growth_score": payload.get("growth_score", 0.0),
                "push_signal_score": payload.get("push_signal_score", 0.0),
                "limit_signal_score": payload.get("limit_signal_score", 0.0),
                "platform_signal": payload.get("platform_signal", "normal_fluctuation"),
                "evidence_json": payload.get("evidence") or {},
            }
            if item is None:
                item = ResearchKeywordHeatSnapshot(**item_payload)
                session.add(item)
            else:
                for key, value in item_payload.items():
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._keyword_heat_snapshot_to_dict(item)

    async def list_keyword_heat_snapshots(
        self,
        *,
        vertical_id: int | None = None,
        scene_pack_id: int | None = None,
        platform: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchKeywordHeatSnapshot)
            if vertical_id is not None:
                stmt = stmt.where(ResearchKeywordHeatSnapshot.vertical_id == vertical_id)
            if scene_pack_id is not None:
                stmt = stmt.where(ResearchKeywordHeatSnapshot.scene_pack_id == scene_pack_id)
            if platform is not None:
                stmt = stmt.where(ResearchKeywordHeatSnapshot.platform == platform)
            stmt = stmt.order_by(
                ResearchKeywordHeatSnapshot.snapshot_date.desc(),
                ResearchKeywordHeatSnapshot.heat_score.desc(),
            )
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [self._keyword_heat_snapshot_to_dict(item) for item in result.scalars().all()]

    async def upsert_competitor_composition_snapshot(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        async with get_session() as session:
            stmt = select(ResearchCompetitorCompositionSnapshot).where(
                ResearchCompetitorCompositionSnapshot.competitor_id == payload["competitor_id"],
                ResearchCompetitorCompositionSnapshot.platform == payload["platform"],
                ResearchCompetitorCompositionSnapshot.snapshot_date == payload["snapshot_date"],
            )
            item = (await session.execute(stmt)).scalar_one_or_none()
            item_payload = {
                "competitor_id": payload["competitor_id"],
                "snapshot_date": payload["snapshot_date"],
                "platform": payload["platform"],
                "total_flow_count": payload.get("total_flow_count", 0),
                "keyword_distribution_json": _json_safe(payload.get("keyword_distribution") or {}),
                "tag_distribution_json": _json_safe(payload.get("tag_distribution") or {}),
                "content_type_distribution_json": _json_safe(payload.get("content_type_distribution") or {}),
                "publish_time_distribution_json": _json_safe(payload.get("publish_time_distribution") or {}),
                "hot_post_rate": payload.get("hot_post_rate", 0.0),
                "evidence_json": _json_safe(payload.get("evidence") or {}),
            }
            if item is None:
                item = ResearchCompetitorCompositionSnapshot(**item_payload)
                session.add(item)
            else:
                for key, value in item_payload.items():
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._competitor_composition_snapshot_to_dict(item)

    async def list_competitor_composition_snapshots(
        self,
        *,
        competitor_id: int | None = None,
        platform: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchCompetitorCompositionSnapshot)
            if competitor_id is not None:
                stmt = stmt.where(ResearchCompetitorCompositionSnapshot.competitor_id == competitor_id)
            if platform is not None:
                stmt = stmt.where(ResearchCompetitorCompositionSnapshot.platform == platform)
            stmt = stmt.order_by(
                ResearchCompetitorCompositionSnapshot.snapshot_date.desc(),
                ResearchCompetitorCompositionSnapshot.id.desc(),
            )
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [
                self._competitor_composition_snapshot_to_dict(item)
                for item in result.scalars().all()
            ]

    async def create_opportunity_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchOpportunityFeedback(
                opportunity_id=payload["opportunity_id"],
                opportunity_type=payload.get("opportunity_type"),
                opportunity_name=payload.get("opportunity_name"),
                feedback=payload["feedback"],
                note=payload.get("note"),
                payload_json=payload.get("payload") or {},
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._opportunity_feedback_to_dict(item)

    async def list_opportunity_feedback(self, limit: int = 500) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = (
                select(ResearchOpportunityFeedback)
                .order_by(ResearchOpportunityFeedback.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [
                self._opportunity_feedback_to_dict(item)
                for item in result.scalars().all()
            ]

    async def create_backtest(self, payload: dict[str, Any]) -> dict[str, Any]:
        item_payload = {
            "scenario": payload["scenario"],
            "vertical_id": payload.get("vertical_id"),
            "scene_pack_id": payload.get("scene_pack_id"),
            "keywords_json": payload.get("keywords") or [],
            "platforms_json": payload.get("platforms") or [],
            "start_date": payload["start_date"],
            "end_date": payload["end_date"],
            "use_local_data": bool(payload.get("use_local_data", True)),
            "use_tikhub_backfill": bool(payload.get("use_tikhub_backfill", False)),
            "replay_daily": bool(payload.get("replay_daily", True)),
            "status": payload.get("status", "pending"),
            "research_job_id": payload.get("research_job_id"),
            "report_json": payload.get("report") or {},
            "error_message": payload.get("error_message"),
        }
        async with get_session() as session:
            item = ResearchBacktest(**item_payload)
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._backtest_to_dict(item)

    async def get_backtest(self, backtest_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchBacktest, backtest_id)
            return self._backtest_to_dict(item) if item else None

    async def list_backtests(self, limit: int | None = 50) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchBacktest).order_by(
                ResearchBacktest.created_at.desc(),
                ResearchBacktest.id.desc(),
            )
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [self._backtest_to_dict(item) for item in result.scalars().all()]

    async def update_backtest(
        self, backtest_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        mapping = {
            "status": "status",
            "research_job_id": "research_job_id",
            "report": "report_json",
            "error_message": "error_message",
        }
        async with get_session() as session:
            item = await session.get(ResearchBacktest, backtest_id)
            if item is None:
                return None
            for source, target in mapping.items():
                if source in payload:
                    setattr(item, target, payload[source])
            await session.flush()
            await session.refresh(item)
            return self._backtest_to_dict(item)

    async def upsert_competitor_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = select(ResearchCompetitorAccount).where(
                ResearchCompetitorAccount.platform == payload["platform"],
                ResearchCompetitorAccount.creator_id == payload["creator_id"],
            )
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchCompetitorAccount(**payload)
                session.add(item)
            else:
                for key, value in payload.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._competitor_account_to_dict(item)

    async def list_competitor_accounts(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchCompetitorAccount)
            if enabled_only:
                stmt = stmt.where(ResearchCompetitorAccount.enabled.is_(True))
            result = await session.execute(stmt.order_by(ResearchCompetitorAccount.id.desc()))
            return [self._competitor_account_to_dict(item) for item in result.scalars().all()]

    async def get_competitor_account(self, competitor_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchCompetitorAccount, competitor_id)
            return self._competitor_account_to_dict(item) if item else None

    async def upsert_account_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = select(ResearchAccountProfile).where(
                ResearchAccountProfile.platform == payload["platform"],
                ResearchAccountProfile.account_id == payload["account_id"],
            )
            item = (await session.execute(stmt)).scalar_one_or_none()
            item_payload = {
                "platform": payload["platform"],
                "account_id": payload["account_id"],
                "sec_account_id": payload.get("sec_account_id"),
                "display_name": payload.get("display_name"),
                "avatar_url": payload.get("avatar_url"),
                "profile_url": payload.get("profile_url"),
                "bio": payload.get("bio"),
                "verified": bool(payload.get("verified", False)),
                "region": payload.get("region"),
                "follower_count": payload.get("follower_count"),
                "following_count": payload.get("following_count"),
                "post_count": payload.get("post_count"),
                "avg_engagement_rate": payload.get("avg_engagement_rate"),
                "hot_post_rate": payload.get("hot_post_rate"),
                "recent_post_count_30d": payload.get("recent_post_count_30d"),
                "latest_post_time": payload.get("latest_post_time"),
                "contact_clues_json": payload.get("contact_clues") or [],
                "tag_summary_json": payload.get("tag_summary") or {},
                "last_crawled_at": payload.get("last_crawled_at"),
            }
            if item is None:
                item = ResearchAccountProfile(**item_payload)
                session.add(item)
            else:
                for key, value in item_payload.items():
                    if value not in (None, "", [], {}):
                        setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._account_profile_to_dict(item)

    async def get_account_profile(self, profile_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchAccountProfile, profile_id)
            return self._account_profile_to_dict(item) if item else None

    async def list_account_profiles(
        self,
        *,
        platform: str | None = None,
        role: str | None = None,
        vertical_id: int | None = None,
        scene_pack_id: int | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchAccountProfile)
            if role or vertical_id is not None or scene_pack_id is not None:
                stmt = stmt.join(
                    ResearchAccountRole,
                    ResearchAccountRole.account_profile_id == ResearchAccountProfile.id,
                )
            if platform:
                stmt = stmt.where(ResearchAccountProfile.platform == platform)
            if role:
                stmt = stmt.where(ResearchAccountRole.role == role)
            if vertical_id is not None:
                stmt = stmt.where(ResearchAccountRole.vertical_id == vertical_id)
            if scene_pack_id is not None:
                stmt = stmt.where(ResearchAccountRole.scene_pack_id == scene_pack_id)
            result = await session.execute(stmt.order_by(ResearchAccountProfile.id.desc()))
            return [self._account_profile_to_dict(item) for item in result.scalars().unique().all()]

    async def upsert_account_role(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = select(ResearchAccountRole).where(
                ResearchAccountRole.account_profile_id == payload["account_profile_id"],
                ResearchAccountRole.role == payload["role"],
                ResearchAccountRole.vertical_id == payload.get("vertical_id"),
                ResearchAccountRole.scene_pack_id == payload.get("scene_pack_id"),
                ResearchAccountRole.monitor_pool_id == payload.get("monitor_pool_id"),
            )
            item = (await session.execute(stmt)).scalar_one_or_none()
            item_payload = {
                "account_profile_id": payload["account_profile_id"],
                "role": payload["role"],
                "vertical_id": payload.get("vertical_id"),
                "scene_pack_id": payload.get("scene_pack_id"),
                "monitor_pool_id": payload.get("monitor_pool_id"),
                "source": payload.get("source", "manual"),
                "status": payload.get("status", "active"),
            }
            if item is None:
                item = ResearchAccountRole(**item_payload)
                session.add(item)
            else:
                item.source = item_payload["source"]
                item.status = item_payload["status"]
            await session.flush()
            await session.refresh(item)
            return self._account_role_to_dict(item)

    async def list_account_roles(
        self,
        *,
        profile_id: int | None = None,
        role: str | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchAccountRole)
            if profile_id is not None:
                stmt = stmt.where(ResearchAccountRole.account_profile_id == profile_id)
            if role:
                stmt = stmt.where(ResearchAccountRole.role == role)
            result = await session.execute(stmt.order_by(ResearchAccountRole.id.desc()))
            return [self._account_role_to_dict(item) for item in result.scalars().all()]

    async def add_account_profile_to_monitor_pool(
        self, pool_id: int, profile_id: int, *, crawl_now: bool = False
    ) -> dict[str, Any]:
        pool = await self.get_monitor_pool(pool_id)
        if pool is None:
            raise KeyError(pool_id)
        role = await self.upsert_account_role(
            {
                "account_profile_id": profile_id,
                "role": "monitored_creator",
                "vertical_id": pool.get("vertical_id"),
                "scene_pack_id": pool.get("scene_pack_id"),
                "monitor_pool_id": pool_id,
                "source": "manual",
                "status": "active",
            }
        )
        role["crawl_now"] = crawl_now
        return role

    async def score_creator_candidates_for_scene_pack(
        self,
        *,
        scene_pack_id: int,
        platform: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        keywords = await self.list_scene_pack_keywords(
            scene_pack_ids=[scene_pack_id],
            enabled_only=True,
        )
        profiles = await self.list_account_profiles(
            platform=platform,
            role="candidate_creator",
            scene_pack_id=scene_pack_id,
        )
        posts = await self.list_all_posts(platform=platform, limit=5000)
        results: list[dict[str, Any]] = []
        for profile in profiles:
            account_posts = [
                post
                for post in posts
                if post.get("platform") == profile["platform"]
                and str((post.get("engagement_json") or {}).get("author_id") or "")
                == str(profile["account_id"])
            ]
            score = score_creator_candidate(profile, account_posts, keywords)
            if not score["evidence"]:
                continue
            results.append(
                {
                    "account_profile": profile,
                    "score": score["score"],
                    "labels": score["labels"],
                    "eligible": score["eligible"],
                    "matched_keywords": score["matched_keywords"],
                    "evidence": score["evidence"],
                }
            )
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:limit]

    async def list_competitor_snapshots(self, competitor_id: int) -> list[dict[str, Any]]:
        async with get_session() as session:
            competitor = await session.get(ResearchCompetitorAccount, competitor_id)
            if competitor is None:
                return []
            result = await session.execute(
                select(ResearchCreatorDailySnapshot)
                .where(
                    ResearchCreatorDailySnapshot.platform == competitor.platform,
                    ResearchCreatorDailySnapshot.creator_id == competitor.creator_id,
                )
                .order_by(ResearchCreatorDailySnapshot.snapshot_date.desc())
            )
            return [self._creator_daily_snapshot_to_dict(item) for item in result.scalars().all()]

    async def update_competitor_account(
        self, competitor_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchCompetitorAccount, competitor_id)
            if item is None:
                return None
            for key, value in payload.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._competitor_account_to_dict(item)

    async def create_keyword_opportunity_snapshot(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchKeywordOpportunitySnapshot(**payload)
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._keyword_opportunity_snapshot_to_dict(item)

    async def list_keyword_opportunity_snapshots(
        self,
        *,
        vertical_id: int | None = None,
        platform: str | None = None,
        tag_id: int | None = None,
        snapshot_date: date | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchKeywordOpportunitySnapshot)
            if vertical_id is not None:
                stmt = stmt.where(ResearchKeywordOpportunitySnapshot.vertical_id == vertical_id)
            if platform is not None:
                stmt = stmt.where(ResearchKeywordOpportunitySnapshot.platform == platform)
            if tag_id is not None:
                stmt = stmt.where(ResearchKeywordOpportunitySnapshot.tag_id == tag_id)
            if snapshot_date is not None:
                stmt = stmt.where(
                    ResearchKeywordOpportunitySnapshot.snapshot_date == snapshot_date
                )
            result = await session.execute(
                stmt.order_by(ResearchKeywordOpportunitySnapshot.snapshot_date.desc())
            )
            return [
                self._keyword_opportunity_snapshot_to_dict(item)
                for item in result.scalars().all()
            ]

    async def create_auth_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_payload = {
            "name": payload["name"],
            "platform": payload["platform"],
            "login_type": payload["login_type"],
            "cookies_encrypted": payload["cookies"],
            "enabled": payload["enabled"],
            "expires_at": payload.get("expires_at"),
            "notes": payload.get("notes"),
        }
        async with get_session() as session:
            profile = ResearchAuthProfile(**profile_payload)
            session.add(profile)
            await session.flush()
            await session.refresh(profile)
            return self._auth_profile_to_dict(profile)

    async def list_auth_profiles(self, platform: str | None = None) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchAuthProfile)
            if platform:
                stmt = stmt.where(ResearchAuthProfile.platform == platform)
            result = await session.execute(
                stmt.order_by(ResearchAuthProfile.platform.asc(), ResearchAuthProfile.id.desc())
            )
            return [self._auth_profile_to_dict(item) for item in result.scalars().all()]

    async def get_enabled_auth_profile(
        self, platform: str, *, include_secret: bool = False
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        async with get_session() as session:
            result = await session.execute(
                select(ResearchAuthProfile)
                .where(
                    ResearchAuthProfile.platform == platform,
                    ResearchAuthProfile.enabled.is_(True),
                    or_(
                        ResearchAuthProfile.expires_at.is_(None),
                        ResearchAuthProfile.expires_at > now,
                    ),
                )
                .order_by(ResearchAuthProfile.id.desc())
                .limit(1)
            )
            profile = result.scalar_one_or_none()
            if profile is None:
                return None
            payload = self._auth_profile_to_dict(profile)
            if include_secret:
                payload["cookies"] = profile.cookies_encrypted
            return payload

    async def update_auth_profile(
        self, profile_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            profile = await session.get(ResearchAuthProfile, profile_id)
            if profile is None:
                return None
            if "cookies" in payload and payload["cookies"] is not None:
                profile.cookies_encrypted = payload["cookies"]
            for key, value in payload.items():
                if key == "cookies":
                    continue
                if value is not None and hasattr(profile, key):
                    setattr(profile, key, value)
            await session.flush()
            await session.refresh(profile)
            return self._auth_profile_to_dict(profile)

    async def mark_auth_profile_verified(self, profile_id: int) -> dict[str, Any] | None:
        return await self.update_auth_profile(
            profile_id, {"last_verified_at": datetime.now(timezone.utc)}
        )

    async def list_posts(self, job_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchPost).where(ResearchPost.job_id == job_id)
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            posts = [self._post_to_dict(item) for item in result.scalars().all()]
            return await self._enrich_posts_from_platform_tables(session, posts)

    async def list_posts_page(
        self,
        *,
        job_ids: list[int] | None = None,
        job_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        async with get_session() as session:
            stmt = select(ResearchPost)
            count_stmt = select(func.count(ResearchPost.id))
            if job_id is not None:
                stmt = stmt.where(ResearchPost.job_id == job_id)
                count_stmt = count_stmt.where(ResearchPost.job_id == job_id)
            if job_ids is not None:
                if not job_ids:
                    return {"posts": [], "total": 0, "limit": limit, "offset": offset}
                stmt = stmt.where(ResearchPost.job_id.in_(job_ids))
                count_stmt = count_stmt.where(ResearchPost.job_id.in_(job_ids))
            total = int(await session.scalar(count_stmt) or 0)
            stmt = stmt.order_by(
                ResearchPost.publish_time.desc().nullslast(),
                ResearchPost.created_at.desc(),
                ResearchPost.id.desc(),
            ).offset(offset).limit(limit)
            result = await session.execute(stmt)
            posts = [self._post_to_dict(item) for item in result.scalars().all()]
            posts = await self._enrich_posts_from_platform_tables(session, posts)
            return {"posts": posts, "total": total, "limit": limit, "offset": offset}

    async def list_all_posts(
        self,
        *,
        job_id: int | None = None,
        platform: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchPost)
            if job_id is not None:
                stmt = stmt.where(ResearchPost.job_id == job_id)
            if platform:
                stmt = stmt.where(ResearchPost.platform == platform)
            if start_at is not None:
                stmt = stmt.where(ResearchPost.publish_time >= start_at)
            if end_at is not None:
                stmt = stmt.where(ResearchPost.publish_time <= end_at)
            stmt = stmt.order_by(
                ResearchPost.publish_time.desc().nullslast(),
                ResearchPost.created_at.desc(),
            )
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            posts = [self._post_to_dict(item) for item in result.scalars().all()]
            return await self._enrich_posts_from_platform_tables(session, posts)

    async def list_posts_by_creator(
        self,
        *,
        platform: str,
        creator_id: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchPost).where(
                ResearchPost.platform == platform,
                ResearchPost.author_hash == creator_id,
            )
            stmt = stmt.order_by(ResearchPost.publish_time.desc().nullslast())
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            posts = [self._post_to_dict(item) for item in result.scalars().all()]
            posts = await self._enrich_posts_from_platform_tables(session, posts)
            if posts:
                return posts
            stmt = select(ResearchPost).where(ResearchPost.platform == platform)
            stmt = stmt.order_by(ResearchPost.publish_time.desc().nullslast())
            stmt = stmt.limit(max(limit or 500, 500))
            result = await session.execute(stmt)
            posts = await self._enrich_posts_from_platform_tables(
                session,
                [self._post_to_dict(item) for item in result.scalars().all()],
            )
            matched = [
                post
                for post in posts
                if post.get("author_hash") == creator_id
                or str((post.get("engagement_json") or {}).get("author_id") or "") == creator_id
                or str((post.get("engagement_json") or {}).get("sec_uid") or "") == creator_id
            ]
            return matched[:limit] if limit else matched

    async def list_comments(self, job_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchComment).where(ResearchComment.job_id == job_id)
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [self._comment_to_dict(item) for item in result.scalars().all()]

    async def list_all_comments(
        self,
        *,
        job_id: int | None = None,
        platform: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchComment)
            if job_id is not None:
                stmt = stmt.where(ResearchComment.job_id == job_id)
            if platform:
                stmt = stmt.where(ResearchComment.platform == platform)
            stmt = stmt.order_by(ResearchComment.created_at.desc())
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

    async def list_all_authors(
        self,
        *,
        job_id: int | None = None,
        platform: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchAuthor)
            if job_id is not None:
                stmt = stmt.where(ResearchAuthor.job_id == job_id)
            if platform:
                stmt = stmt.where(ResearchAuthor.platform == platform)
            stmt = stmt.order_by(ResearchAuthor.created_at.desc())
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

    async def create_ai_insight_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchAIInsightRun(
                provider_config_id=payload.get("provider_config_id"),
                vertical_id=payload.get("vertical_id"),
                scene_pack_id=payload.get("scene_pack_id"),
                platforms_json=payload.get("platforms") or [],
                window_days=int(payload.get("window_days") or 7),
                status=payload.get("status") or "pending",
                input_summary_json=payload.get("input_summary") or {},
                output_json=payload.get("output") or {},
                error_message=payload.get("error_message"),
                model=payload.get("model"),
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._ai_insight_run_to_dict(item)

    async def update_ai_insight_run(
        self, run_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        mapping = {
            "status": "status",
            "input_summary": "input_summary_json",
            "output": "output_json",
            "error_message": "error_message",
            "model": "model",
        }
        async with get_session() as session:
            item = await session.get(ResearchAIInsightRun, run_id)
            if item is None:
                return None
            for source, target in mapping.items():
                if source in payload:
                    setattr(item, target, payload[source])
            await session.flush()
            await session.refresh(item)
            return self._ai_insight_run_to_dict(item)

    async def list_ai_insight_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        async with get_session() as session:
            result = await session.execute(
                select(ResearchAIInsightRun)
                .order_by(ResearchAIInsightRun.created_at.desc(), ResearchAIInsightRun.id.desc())
                .limit(limit)
            )
            return [self._ai_insight_run_to_dict(item) for item in result.scalars().all()]

    async def get_ai_insight_run(self, run_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchAIInsightRun, run_id)
            return self._ai_insight_run_to_dict(item) if item else None

    async def create_ai_hotspots(
        self, run_id: int, hotspots: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            rows: list[ResearchAIHotspot] = []
            for item in hotspots:
                row = ResearchAIHotspot(
                    run_id=run_id,
                    name=str(item.get("name") or "未命名热点")[:255],
                    platform=str(item.get("platform") or "all")[:32],
                    heat_level=str(item.get("heat_level") or item.get("label") or "watch")[:32],
                    confidence=str(item.get("confidence") or "low")[:32],
                    reason=str(item.get("reason") or item.get("why") or "AI 未返回推荐理由"),
                    evidence_json=item.get("evidence") or item.get("evidence_refs") or {},
                    platform_strategy_json=item.get("platform_strategy") or {},
                    risk_notes_json=item.get("risk_notes") or [],
                )
                session.add(row)
                rows.append(row)
            await session.flush()
            for row in rows:
                await session.refresh(row)
            return [self._ai_hotspot_to_dict(row) for row in rows]

    async def create_ai_topic_ideas(
        self, run_id: int, ideas: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            rows: list[ResearchAITopicIdea] = []
            for item in ideas:
                row = ResearchAITopicIdea(
                    run_id=run_id,
                    title=str(item.get("title") or "未命名选题"),
                    platform=str(item.get("platform") or "all")[:32],
                    target_audience=item.get("target_audience"),
                    keywords_json=item.get("keywords") or [],
                    content_angle=item.get("content_angle") or item.get("angle"),
                    outline_json=item.get("outline") or item.get("structure") or [],
                    reason=str(item.get("reason") or "AI 未返回推荐理由"),
                    evidence_json=item.get("evidence") or item.get("evidence_refs") or {},
                    risk_notes_json=item.get("risk_notes") or [],
                    expected_effect=item.get("expected_effect"),
                    status=str(item.get("status") or "active")[:32],
                )
                session.add(row)
                rows.append(row)
            await session.flush()
            for row in rows:
                await session.refresh(row)
            return [self._ai_topic_idea_to_dict(row) for row in rows]

    async def list_ai_hotspots(
        self, *, run_id: int | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchAIHotspot)
            if run_id is not None:
                stmt = stmt.where(ResearchAIHotspot.run_id == run_id)
            stmt = stmt.order_by(ResearchAIHotspot.created_at.desc(), ResearchAIHotspot.id.desc()).limit(limit)
            result = await session.execute(stmt)
            return [self._ai_hotspot_to_dict(item) for item in result.scalars().all()]

    async def list_ai_topic_ideas(
        self, *, run_id: int | None = None, status: str | None = "active", limit: int = 30
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = select(ResearchAITopicIdea)
            if run_id is not None:
                stmt = stmt.where(ResearchAITopicIdea.run_id == run_id)
            if status:
                stmt = stmt.where(ResearchAITopicIdea.status == status)
            stmt = stmt.order_by(ResearchAITopicIdea.created_at.desc(), ResearchAITopicIdea.id.desc()).limit(limit)
            result = await session.execute(stmt)
            return [self._ai_topic_idea_to_dict(item) for item in result.scalars().all()]

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

    async def upsert_ai_provider_by_name(self, payload: dict[str, Any]) -> dict[str, Any]:
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
            result = await session.execute(
                select(AIProviderConfig).where(AIProviderConfig.name == payload["name"])
            )
            provider = result.scalar_one_or_none()
            if provider is None:
                provider = AIProviderConfig(**provider_payload)
                session.add(provider)
            else:
                for key, value in provider_payload.items():
                    setattr(provider, key, value)
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

    async def upsert_prompt_template_by_name(self, payload: dict[str, Any]) -> dict[str, Any]:
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
            result = await session.execute(
                select(AIPromptTemplate).where(AIPromptTemplate.name == payload["name"])
            )
            prompt = result.scalar_one_or_none()
            if prompt is None:
                prompt = AIPromptTemplate(**prompt_payload)
                session.add(prompt)
            else:
                for key, value in prompt_payload.items():
                    setattr(prompt, key, value)
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
                stats_json=_json_safe(stats or {}),
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

    async def _count_all(self, session, model) -> int:
        result = await session.execute(select(func.count()).select_from(model))
        return int(result.scalar() or 0)

    async def _count_by_platform(self, session, model, job_id: int) -> dict[str, int]:
        result = await session.execute(
            select(model.platform, func.count()).where(model.job_id == job_id).group_by(model.platform)
        )
        return {platform: int(count) for platform, count in result.all()}

    async def _count_all_by_platform(self, session, model) -> dict[str, int]:
        result = await session.execute(select(model.platform, func.count()).group_by(model.platform))
        return {platform: int(count) for platform, count in result.all()}

    async def _count_table(self, session, table_name: str) -> int:
        result = await session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        return int(result.scalar() or 0)

    async def _enrich_posts_from_platform_tables(
        self,
        session,
        posts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not posts:
            return posts
        ids_by_platform: dict[str, set[str]] = {}
        for post in posts:
            platform_post_id = post.get("platform_post_id")
            if not platform_post_id:
                continue
            ids_by_platform.setdefault(str(post.get("platform") or ""), set()).add(str(platform_post_id))

        xhs_rows: dict[str, dict[str, Any]] = {}
        xhs_ids = list(ids_by_platform.get("xhs") or [])
        if xhs_ids:
            result = await session.execute(
                text(
                    """
                    SELECT note_id, user_id, nickname, note_url, liked_count, comment_count,
                           collected_count, share_count, source_keyword
                    FROM xhs_note
                    WHERE note_id IN :ids
                    """
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": xhs_ids},
            )
            xhs_rows = {str(row._mapping["note_id"]): dict(row._mapping) for row in result}

        dy_rows: dict[str, dict[str, Any]] = {}
        dy_ids = list(ids_by_platform.get("dy") or [])
        if dy_ids:
            result = await session.execute(
                text(
                    """
                    SELECT aweme_id, user_id, sec_uid, nickname, aweme_url, liked_count,
                           comment_count, share_count, collected_count, source_keyword
                    FROM douyin_aweme
                    WHERE CAST(aweme_id AS TEXT) IN :ids
                    """
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": dy_ids},
            )
            dy_rows = {str(row._mapping["aweme_id"]): dict(row._mapping) for row in result}

        for post in posts:
            platform = post.get("platform")
            platform_post_id = str(post.get("platform_post_id") or "")
            if platform == "xhs" and platform_post_id in xhs_rows:
                self._merge_platform_author_metadata(
                    post,
                    xhs_rows[platform_post_id],
                    author_id_key="user_id",
                    url_key="note_url",
                )
            elif platform == "dy" and platform_post_id in dy_rows:
                self._merge_platform_author_metadata(
                    post,
                    dy_rows[platform_post_id],
                    author_id_key="user_id",
                    url_key="aweme_url",
                    sec_uid_key="sec_uid",
                )
        return posts

    def _merge_platform_author_metadata(
        self,
        post: dict[str, Any],
        source: dict[str, Any],
        *,
        author_id_key: str,
        url_key: str,
        sec_uid_key: str | None = None,
    ) -> None:
        engagement = dict(post.get("engagement_json") or {})
        author_id = source.get(author_id_key)
        if author_id is not None:
            engagement.setdefault("author_id", str(author_id))
            engagement.setdefault("user_id", str(author_id))
        if sec_uid_key and source.get(sec_uid_key) is not None:
            engagement.setdefault("sec_uid", str(source[sec_uid_key]))
        for key in (
            "nickname",
            "liked_count",
            "comment_count",
            "share_count",
            "collected_count",
            "source_keyword",
        ):
            if source.get(key) not in (None, ""):
                engagement.setdefault(key, source[key])
        source_url = source.get(url_key)
        if source_url and not post.get("url"):
            post["url"] = source_url
        post["engagement_json"] = engagement

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
            "collection_mode": job.collection_mode or "search",
            "keywords": job.keywords or [],
            "target_ids": job.target_ids or [],
            "creator_ids": job.creator_ids or [],
            "start_date": job.start_date,
            "end_date": job.end_date,
            "status": job.status,
            "comment_policy": job.comment_policy,
            "raw_record_mode": job.raw_record_mode,
            "anonymize_authors": job.anonymize_authors,
            "schedule_enabled": bool(job.schedule_enabled),
            "schedule_interval_minutes": job.schedule_interval_minutes,
            "next_run_at": job.next_run_at,
            "last_scheduled_at": job.last_scheduled_at,
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

    def _crawl_unit_to_dict(self, unit: ResearchCrawlUnit) -> dict[str, Any]:
        return {
            "id": unit.id,
            "job_id": unit.job_id,
            "run_key": unit.run_key,
            "unit_key": unit.unit_key,
            "platform": unit.platform,
            "collection_mode": unit.collection_mode,
            "keyword": unit.keyword,
            "target_id": unit.target_id,
            "creator_id": unit.creator_id,
            "status": unit.status,
            "priority": unit.priority,
            "attempt_count": unit.attempt_count,
            "max_attempts": unit.max_attempts,
            "scheduled_at": unit.scheduled_at,
            "locked_by": unit.locked_by,
            "locked_at": unit.locked_at,
            "started_at": unit.started_at,
            "finished_at": unit.finished_at,
            "last_error": unit.last_error,
            "created_at": unit.created_at,
            "updated_at": unit.updated_at,
        }

    def _worker_heartbeat_to_dict(self, heartbeat: ResearchWorkerHeartbeat) -> dict[str, Any]:
        return {
            "id": heartbeat.id,
            "worker_id": heartbeat.worker_id,
            "hostname": heartbeat.hostname,
            "pid": heartbeat.pid,
            "status": heartbeat.status,
            "current_unit_id": heartbeat.current_unit_id,
            "metadata": heartbeat.metadata_json or {},
            "started_at": heartbeat.started_at,
            "last_seen_at": heartbeat.last_seen_at,
            "updated_at": heartbeat.updated_at,
        }

    def _platform_rate_limit_to_dict(self, item: ResearchPlatformRateLimit) -> dict[str, Any]:
        return {
            "id": item.id,
            "platform": item.platform,
            "requests_per_minute": item.requests_per_minute,
            "min_sleep_seconds": item.min_sleep_seconds,
            "max_sleep_seconds": item.max_sleep_seconds,
            "enabled": item.enabled,
            "updated_at": item.updated_at,
        }

    def _platform_capability_to_dict(self, item: ResearchPlatformCapability) -> dict[str, Any]:
        return {
            "id": item.id,
            "platform": item.platform,
            "enabled": bool(item.enabled),
            "crawl_search_enabled": bool(item.crawl_search_enabled),
            "crawl_creator_enabled": bool(item.crawl_creator_enabled),
            "crawl_detail_enabled": bool(item.crawl_detail_enabled),
            "comments_enabled": bool(item.comments_enabled),
            "analysis_enabled": bool(item.analysis_enabled),
            "daily_monitor_enabled": bool(item.daily_monitor_enabled),
            "keyword_heat_enabled": bool(item.keyword_heat_enabled),
            "rate_limit_per_minute": item.rate_limit_per_minute,
            "max_daily_jobs": item.max_daily_jobs,
            "notes": item.notes,
            "updated_at": item.updated_at,
        }

    def _global_setting_to_dict(self, item: ResearchGlobalSetting) -> dict[str, Any]:
        return {
            "id": item.id,
            "key": item.key,
            "value": item.value_json or {},
            "updated_at": item.updated_at,
        }

    def _keyword_set_to_dict(self, item: ResearchKeywordSet) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "platforms": item.platforms or [],
            "keywords": item.keywords or [],
            "negative_keywords": item.negative_keywords or [],
            "synonyms": item.synonyms or [],
            "topic": item.topic,
            "enabled": bool(item.enabled),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _vertical_to_dict(self, item: ResearchVertical) -> dict[str, Any]:
        return {
            "id": item.id,
            "code": item.code,
            "name": item.name,
            "enabled": bool(item.enabled),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _tag_group_to_dict(self, item: ResearchTagGroup) -> dict[str, Any]:
        return {
            "id": item.id,
            "vertical_id": item.vertical_id,
            "name": item.name,
            "description": item.description,
            "sort_order": item.sort_order,
            "enabled": bool(item.enabled),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _tag_definition_to_dict(self, item: ResearchTagDefinition) -> dict[str, Any]:
        return {
            "id": item.id,
            "vertical_id": item.vertical_id,
            "group_id": item.group_id,
            "tag_name": item.tag_name,
            "keywords": item.keywords or [],
            "synonyms": item.synonyms or [],
            "negative_keywords": item.negative_keywords or [],
            "ai_prompt_hint": item.ai_prompt_hint,
            "weight": item.weight,
            "enabled": bool(item.enabled),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _entity_tag_to_dict(self, item: ResearchEntityTag) -> dict[str, Any]:
        return {
            "id": item.id,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "platform": item.platform,
            "vertical_id": item.vertical_id,
            "tag_id": item.tag_id,
            "confidence": float(item.confidence or 0),
            "source": item.source,
            "evidence_json": item.evidence_json or {},
            "analysis_version": item.analysis_version,
            "created_at": item.created_at,
        }

    def _creator_profile_to_dict(self, item: ResearchCreatorProfile) -> dict[str, Any]:
        return {
            "id": item.id,
            "platform": item.platform,
            "creator_id": item.creator_id,
            "display_name": item.display_name,
            "profile_url": item.profile_url,
            "bio": item.bio,
            "follower_count": item.follower_count,
            "following_count": item.following_count,
            "post_count": item.post_count,
            "avg_engagement_rate": item.avg_engagement_rate,
            "hot_post_rate": item.hot_post_rate,
            "recent_post_count_30d": item.recent_post_count_30d,
            "latest_snapshot_at": item.latest_snapshot_at,
            "tag_summary_json": item.tag_summary_json or {},
            "updated_at": item.updated_at,
        }

    def _account_profile_to_dict(self, item: ResearchAccountProfile) -> dict[str, Any]:
        return {
            "id": item.id,
            "platform": item.platform,
            "account_id": item.account_id,
            "sec_account_id": item.sec_account_id,
            "display_name": item.display_name,
            "avatar_url": item.avatar_url,
            "profile_url": item.profile_url,
            "bio": item.bio,
            "verified": bool(item.verified),
            "region": item.region,
            "follower_count": item.follower_count,
            "following_count": item.following_count,
            "post_count": item.post_count,
            "avg_engagement_rate": item.avg_engagement_rate,
            "hot_post_rate": item.hot_post_rate,
            "recent_post_count_30d": item.recent_post_count_30d,
            "latest_post_time": item.latest_post_time,
            "contact_clues": item.contact_clues_json or [],
            "tag_summary": item.tag_summary_json or {},
            "last_crawled_at": item.last_crawled_at,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _account_role_to_dict(self, item: ResearchAccountRole) -> dict[str, Any]:
        return {
            "id": item.id,
            "account_profile_id": item.account_profile_id,
            "role": item.role,
            "vertical_id": item.vertical_id,
            "scene_pack_id": item.scene_pack_id,
            "monitor_pool_id": item.monitor_pool_id,
            "source": item.source,
            "status": item.status,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _creator_daily_snapshot_to_dict(self, item: ResearchCreatorDailySnapshot) -> dict[str, Any]:
        return {
            "id": item.id,
            "platform": item.platform,
            "creator_id": item.creator_id,
            "snapshot_date": item.snapshot_date,
            "follower_count": item.follower_count,
            "total_like_count": item.total_like_count,
            "total_comment_count": item.total_comment_count,
            "total_share_count": item.total_share_count,
            "new_post_count": item.new_post_count,
            "hot_post_count": item.hot_post_count,
            "tag_distribution_json": item.tag_distribution_json or {},
            "top_posts_json": item.top_posts_json or [],
            "created_at": item.created_at,
        }

    def _creator_candidate_to_dict(self, item: ResearchCreatorCandidate) -> dict[str, Any]:
        return {
            "id": item.id,
            "platform": item.platform,
            "creator_id": item.creator_id,
            "pool_name": item.pool_name,
            "vertical_id": item.vertical_id,
            "match_score": item.match_score,
            "matched_tags": item.matched_tags_json or [],
            "evidence": item.evidence_json or {},
            "notes": item.notes,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _search_intent_to_dict(self, item: ResearchSearchIntent) -> dict[str, Any]:
        return {
            "id": item.id,
            "raw_query": item.raw_query,
            "detected_verticals": item.detected_verticals or [],
            "selected_vertical_id": item.selected_vertical_id,
            "required_tags": item.required_tags or [],
            "optional_tags": item.optional_tags or [],
            "negative_tags": item.negative_tags or [],
            "confidence": float(item.confidence or 0),
            "parser_source": item.parser_source,
            "created_at": item.created_at,
        }

    def _scene_pack_to_dict(self, item: ResearchScenePack) -> dict[str, Any]:
        return {
            "id": item.id,
            "vertical_id": item.vertical_id,
            "name": item.name,
            "description": item.description,
            "weight": item.weight,
            "default_platforms": item.default_platforms or [],
            "primary_goal": item.primary_goal,
            "default_collection_depth": item.default_collection_depth,
            "default_ai_template": item.default_ai_template,
            "source": item.source,
            "archived": bool(item.archived),
            "enabled": bool(item.enabled),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _scene_pack_keyword_to_dict(self, item: ResearchScenePackKeyword) -> dict[str, Any]:
        return {
            "id": item.id,
            "scene_pack_id": item.scene_pack_id,
            "keyword": item.keyword,
            "keyword_type": item.keyword_type,
            "platform": item.platform,
            "weight": item.weight,
            "reason": item.reason,
            "usage_flags": item.usage_flags_json or [],
            "platform_overrides": item.platform_overrides_json or {},
            "enabled": bool(item.enabled),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _growth_project_to_dict(self, item: ResearchGrowthProject) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "primary_goal": item.primary_goal,
            "scene_pack_id": item.scene_pack_id,
            "platforms": item.platforms or [],
            "project_status": item.project_status,
            "collection_status": item.collection_status,
            "comment_collection_enabled": bool(item.comment_collection_enabled),
            "refresh_cadence": item.refresh_cadence,
            "custom_interval_value": item.custom_interval_value,
            "custom_interval_unit": item.custom_interval_unit,
            "sample_status": item.sample_status,
            "recommended_action": item.recommended_action,
            "opportunity_score": item.opportunity_score,
            "last_collected_at": item.last_collected_at,
            "archived": bool(item.archived),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _growth_project_keyword_to_dict(self, item: ResearchGrowthProjectKeyword) -> dict[str, Any]:
        return {
            "id": item.id,
            "project_id": item.project_id,
            "scene_pack_id": item.scene_pack_id,
            "keyword": item.keyword,
            "keyword_type": item.keyword_type,
            "source": item.source,
            "status": item.status,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _growth_project_collection_plan_to_dict(
        self, item: ResearchGrowthProjectCollectionPlan
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "project_id": item.project_id,
            "platform": item.platform,
            "collection_mode": item.collection_mode,
            "keyword_scope": item.keyword_scope,
            "enabled": bool(item.enabled),
            "schedule_mode": item.schedule_mode,
            "schedule_interval_minutes": item.schedule_interval_minutes,
            "last_run_at": item.last_run_at,
            "next_run_at": item.next_run_at,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _ai_keyword_suggestion_session_to_dict(
        self, item: ResearchAIKeywordSuggestionSession
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "vertical_id": item.vertical_id,
            "scene_pack_id": item.scene_pack_id,
            "seed_keywords": item.seed_keywords_json or [],
            "audience_context": item.audience_context,
            "status": item.status,
            "provider_config_id": item.provider_config_id,
            "suggestions": item.suggestions_json or [],
            "selected_keywords": item.selected_keywords_json or [],
            "error_message": item.error_message,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _monitor_pool_payload(
        self, payload: dict[str, Any], *, partial: bool = False
    ) -> dict[str, Any]:
        mapping = {
            "name": "name",
            "description": "description",
            "vertical_id": "vertical_id",
            "platforms": "platforms",
            "schedule_interval_minutes": "schedule_interval_minutes",
            "automation_mode": "automation_mode",
            "auto_top_n": "auto_top_n",
            "min_match_score": "min_match_score",
            "min_recent_posts_30d": "min_recent_posts_30d",
            "follower_min": "follower_min",
            "follower_max": "follower_max",
            "exclude_existing_creators": "exclude_existing_creators",
            "enabled": "enabled",
            "research_job_id": "research_job_id",
        }
        result = {
            target: payload[source]
            for source, target in mapping.items()
            if source in payload and (payload[source] is not None or not partial)
        }
        if "scene_pack_ids" in payload:
            result["scene_pack_ids_json"] = payload.get("scene_pack_ids") or []
            scene_pack_ids = result["scene_pack_ids_json"]
            result["scene_pack_id"] = scene_pack_ids[0] if scene_pack_ids else None
        elif not partial:
            result["scene_pack_ids_json"] = []
        if "comment_policy" in payload:
            result["comment_policy_json"] = payload.get("comment_policy") or {}
            result["comment_policy"] = (
                "full"
                if result["comment_policy_json"].get("enable_sub_comments")
                else "limited"
                if result["comment_policy_json"].get("enable_comments", True)
                else "none"
            )
        elif not partial:
            result["comment_policy_json"] = {
                "enable_comments": True,
                "enable_sub_comments": False,
            }
            result["comment_policy"] = "limited"
        return result

    def _monitor_pool_to_dict(self, item: ResearchMonitorPool) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "vertical_id": item.vertical_id,
            "scene_pack_id": item.scene_pack_id,
            "scene_pack_ids": item.scene_pack_ids_json or [],
            "platforms": item.platforms or [],
            "comment_policy": item.comment_policy_json or {},
            "schedule_interval_minutes": item.schedule_interval_minutes,
            "automation_mode": item.automation_mode,
            "auto_top_n": item.auto_top_n,
            "min_match_score": item.min_match_score,
            "min_recent_posts_30d": item.min_recent_posts_30d,
            "follower_min": item.follower_min,
            "follower_max": item.follower_max,
            "exclude_existing_creators": bool(item.exclude_existing_creators),
            "research_job_id": item.research_job_id,
            "enabled": bool(item.enabled),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _monitor_pool_creator_to_dict(self, item: ResearchMonitorPoolCreator) -> dict[str, Any]:
        return {
            "id": item.id,
            "pool_id": item.pool_id,
            "platform": item.platform,
            "creator_id": item.creator_id,
            "display_name": item.display_name,
            "source": item.source,
            "match_score": item.match_score,
            "joined_at": item.joined_at,
            "last_crawled_at": item.last_crawled_at,
            "enabled": bool(item.enabled),
            "notes": item.notes,
        }

    def _content_sample_to_dict(self, item: ResearchContentSample) -> dict[str, Any]:
        return {
            "id": item.id,
            "platform": item.platform,
            "content_id": item.content_id,
            "creator_id": item.creator_id,
            "title": item.title,
            "text_content": item.text_content,
            "video_summary": item.video_summary,
            "content_type": item.content_type,
            "url": item.url,
            "publish_time": item.publish_time,
            "engagement": item.engagement_json or {},
            "raw_record_id": item.raw_record_id,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _extracted_content_keyword_to_dict(
        self, item: ResearchExtractedContentKeyword
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "content_sample_id": item.content_sample_id,
            "keyword": item.keyword,
            "keyword_type": item.keyword_type,
            "score": item.score,
            "source": item.source,
            "evidence": item.evidence_json or {},
            "created_at": item.created_at,
        }

    def _similar_content_candidate_to_dict(
        self, item: ResearchSimilarContentCandidate
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "source_content_sample_id": item.source_content_sample_id,
            "platform": item.platform,
            "content_id": item.content_id,
            "creator_id": item.creator_id,
            "similarity_score": item.similarity_score,
            "reason": item.reason,
            "evidence": item.evidence_json or {},
            "status": item.status,
            "created_at": item.created_at,
        }

    def _content_tracker_payload(
        self, payload: dict[str, Any], *, partial: bool = False
    ) -> dict[str, Any]:
        mapping = {
            "name": "name",
            "description": "description",
            "source_content_sample_id": "source_content_sample_id",
            "vertical_id": "vertical_id",
            "platforms": "platforms",
            "schedule_interval_minutes": "schedule_interval_minutes",
            "enabled": "enabled",
        }
        result = {
            target: payload[source]
            for source, target in mapping.items()
            if source in payload and (payload[source] is not None or not partial)
        }
        if "scene_pack_ids" in payload:
            result["scene_pack_ids_json"] = payload.get("scene_pack_ids") or []
            scene_pack_ids = result["scene_pack_ids_json"]
            result["scene_pack_id"] = scene_pack_ids[0] if scene_pack_ids else None
        elif not partial:
            result["scene_pack_ids_json"] = []
        if "included_keywords" in payload:
            result["included_keywords_json"] = payload.get("included_keywords") or []
            result["keywords_json"] = result["included_keywords_json"]
        elif not partial:
            result["included_keywords_json"] = []
            result["keywords_json"] = []
        if "excluded_keywords" in payload:
            result["excluded_keywords_json"] = payload.get("excluded_keywords") or []
        elif not partial:
            result["excluded_keywords_json"] = []
        if "seed_refs" in payload:
            result["seed_refs_json"] = payload.get("seed_refs") or []
        elif not partial:
            result["seed_refs_json"] = []
        if "comment_policy" in payload:
            result["comment_policy_json"] = payload.get("comment_policy") or {}
        elif not partial:
            result["comment_policy_json"] = {
                "enable_comments": True,
                "enable_sub_comments": False,
            }
        if not partial:
            result.setdefault("tracking_mode", payload.get("tracking_mode", "mixed"))
        elif "tracking_mode" in payload:
            result["tracking_mode"] = payload["tracking_mode"]
        return result

    def _content_tracker_to_dict(self, item: ResearchContentTracker) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "source_content_sample_id": item.source_content_sample_id,
            "vertical_id": item.vertical_id,
            "scene_pack_id": item.scene_pack_id,
            "scene_pack_ids": item.scene_pack_ids_json or [],
            "platforms": item.platforms or [],
            "included_keywords": item.included_keywords_json or [],
            "excluded_keywords": item.excluded_keywords_json or [],
            "seed_refs": item.seed_refs_json or [],
            "tracking_mode": item.tracking_mode,
            "schedule_interval_minutes": item.schedule_interval_minutes,
            "comment_policy": item.comment_policy_json or {},
            "enabled": bool(item.enabled),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _content_tracking_snapshot_to_dict(
        self, item: ResearchContentTrackingSnapshot
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "tracker_id": item.tracker_id,
            "snapshot_date": item.snapshot_date,
            "platform": item.platform,
            "keyword_distribution": item.keyword_distribution_json or {},
            "tag_distribution": item.tag_distribution_json or {},
            "content_type_distribution": item.content_type_distribution_json or {},
            "publish_time_distribution": item.publish_time_distribution_json or {},
            "hot_post_rate": item.hot_post_rate,
            "total_content_count": item.total_content_count,
            "evidence": item.evidence_json or {},
            "created_at": item.created_at,
        }

    def _keyword_heat_snapshot_to_dict(self, item: ResearchKeywordHeatSnapshot) -> dict[str, Any]:
        return {
            "id": item.id,
            "vertical_id": item.vertical_id,
            "scene_pack_id": item.scene_pack_id,
            "keyword": item.keyword,
            "platform": item.platform,
            "snapshot_date": item.snapshot_date,
            "heat_score": item.heat_score,
            "growth_score": item.growth_score,
            "push_signal_score": item.push_signal_score,
            "limit_signal_score": item.limit_signal_score,
            "platform_signal": item.platform_signal,
            "evidence": item.evidence_json or {},
            "created_at": item.created_at,
        }

    def _competitor_composition_snapshot_to_dict(
        self, item: ResearchCompetitorCompositionSnapshot
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "competitor_id": item.competitor_id,
            "snapshot_date": item.snapshot_date,
            "platform": item.platform,
            "total_flow_count": item.total_flow_count,
            "keyword_distribution": item.keyword_distribution_json or {},
            "tag_distribution": item.tag_distribution_json or {},
            "content_type_distribution": item.content_type_distribution_json or {},
            "publish_time_distribution": item.publish_time_distribution_json or {},
            "hot_post_rate": item.hot_post_rate,
            "interaction_structure": (item.evidence_json or {}).get("interaction_structure", {}),
            "evidence": item.evidence_json or {},
            "created_at": item.created_at,
        }

    def _opportunity_feedback_to_dict(self, item: ResearchOpportunityFeedback) -> dict[str, Any]:
        return {
            "id": item.id,
            "opportunity_id": item.opportunity_id,
            "opportunity_type": item.opportunity_type,
            "opportunity_name": item.opportunity_name,
            "feedback": item.feedback,
            "note": item.note,
            "payload": item.payload_json or {},
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    def _competitor_account_to_dict(self, item: ResearchCompetitorAccount) -> dict[str, Any]:
        return {
            "id": item.id,
            "platform": item.platform,
            "creator_id": item.creator_id,
            "display_name": item.display_name,
            "profile_url": item.profile_url,
            "vertical_id": item.vertical_id,
            "enabled": bool(item.enabled),
            "notes": item.notes,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _backtest_to_dict(self, item: ResearchBacktest) -> dict[str, Any]:
        return {
            "id": item.id,
            "scenario": item.scenario,
            "vertical_id": item.vertical_id,
            "scene_pack_id": item.scene_pack_id,
            "keywords": item.keywords_json or [],
            "platforms": item.platforms_json or [],
            "start_date": item.start_date,
            "end_date": item.end_date,
            "use_local_data": bool(item.use_local_data),
            "use_tikhub_backfill": bool(item.use_tikhub_backfill),
            "replay_daily": bool(item.replay_daily),
            "status": item.status,
            "research_job_id": item.research_job_id,
            "report": item.report_json or {},
            "error_message": item.error_message,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _ai_insight_run_to_dict(self, item: ResearchAIInsightRun) -> dict[str, Any]:
        return {
            "id": item.id,
            "provider_config_id": item.provider_config_id,
            "vertical_id": item.vertical_id,
            "scene_pack_id": item.scene_pack_id,
            "platforms": item.platforms_json or [],
            "window_days": item.window_days,
            "status": item.status,
            "input_summary": item.input_summary_json or {},
            "output": item.output_json or {},
            "error_message": item.error_message,
            "model": item.model,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _ai_hotspot_to_dict(self, item: ResearchAIHotspot) -> dict[str, Any]:
        return {
            "id": item.id,
            "run_id": item.run_id,
            "name": item.name,
            "platform": item.platform,
            "heat_level": item.heat_level,
            "confidence": item.confidence,
            "reason": item.reason,
            "evidence": item.evidence_json or {},
            "platform_strategy": item.platform_strategy_json or {},
            "risk_notes": item.risk_notes_json or [],
            "created_at": item.created_at,
        }

    def _ai_topic_idea_to_dict(self, item: ResearchAITopicIdea) -> dict[str, Any]:
        return {
            "id": item.id,
            "run_id": item.run_id,
            "title": item.title,
            "platform": item.platform,
            "target_audience": item.target_audience,
            "keywords": item.keywords_json or [],
            "content_angle": item.content_angle,
            "outline": item.outline_json or [],
            "reason": item.reason,
            "evidence": item.evidence_json or {},
            "risk_notes": item.risk_notes_json or [],
            "expected_effect": item.expected_effect,
            "status": item.status,
            "created_at": item.created_at,
        }

    def _keyword_opportunity_snapshot_to_dict(
        self, item: ResearchKeywordOpportunitySnapshot
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "vertical_id": item.vertical_id,
            "platform": item.platform,
            "tag_id": item.tag_id,
            "snapshot_date": item.snapshot_date,
            "heat_score": item.heat_score,
            "growth_score": item.growth_score,
            "competition_score": item.competition_score,
            "supply_gap_score": item.supply_gap_score,
            "platform_signal": item.platform_signal,
            "evidence": item.evidence_json or {},
            "created_at": item.created_at,
        }

    def _auth_profile_to_dict(self, profile: ResearchAuthProfile) -> dict[str, Any]:
        return {
            "id": profile.id,
            "name": profile.name,
            "platform": profile.platform,
            "login_type": profile.login_type,
            "enabled": profile.enabled,
            "cookie_set": bool(profile.cookies_encrypted),
            "last_verified_at": profile.last_verified_at,
            "expires_at": profile.expires_at,
            "notes": profile.notes,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
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
