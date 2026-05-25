import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy import bindparam, delete, func, or_, select, text, update

from database.db_session import get_session
from database.models import XhsNote
from research.creator_scoring import score_creator_candidate
from research.enums import (
    CRAWL_UNIT_CANCELLED,
    CRAWL_UNIT_FAILED,
    CRAWL_UNIT_PENDING,
    CRAWL_UNIT_RETRYING,
    CRAWL_UNIT_RUNNING,
    CRAWL_UNIT_SUCCEEDED,
    CRAWL_UNIT_TERMINAL_STATUSES,
)
from research.models import (
    AIAnalysisJob,
    AIAnalysisResult,
    AIProviderConfig,
    AIPromptTemplate,
    CrawlCheckpoint,
    CrawlEvent,
    RawRecord,
    ResearchAuthProfile,
    ResearchAccountProfile,
    ResearchAccountRole,
    ResearchAuthor,
    ResearchBacktest,
    ResearchComment,
    ResearchCollectionRun,
    ResearchCompetitorAccount,
    ResearchCreatorCandidate,
    ResearchCreatorDailySnapshot,
    ResearchCreatorProfile,
    ResearchCreatorSearchSession,
    ResearchCreatorSearchSessionResult,
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
    ResearchContentTrackerAnalysisRun,
    ResearchContentTrackerAnalysisSnapshot,
    ResearchContentTrackerCandidateSample,
    ResearchContentTrackingSnapshot,
    ResearchExtractedContentKeyword,
    ResearchJob,
    ResearchKeywordHeatSnapshot,
    ResearchKeywordSet,
    ResearchKeywordOpportunitySnapshot,
    ResearchLead,
    ResearchLeadAttributionDailySnapshot,
    ResearchLeadAttributionResult,
    ResearchLeadAttributionSpend,
    ResearchLeadConversionEvent,
    ResearchLeadTouchpoint,
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
from saas.tenant_context import get_current_org_id, is_platform_admin_request


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


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _growth_project_slug(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if not candidate:
        return ""
    slug = "".join(
        ch if ch.isalnum() or ch == "_" or ("\u4e00" <= ch <= "\u9fff") else "_"
        for ch in candidate.replace(" ", "_")
    )
    return slug.strip("_")


def _growth_project_job_key(project_record_id: int) -> str:
    return f"growth_project_record_{project_record_id}"


def _job_growth_project_key(comment_policy: Any) -> str | None:
    if not isinstance(comment_policy, dict):
        return None
    value = str(comment_policy.get("growth_project_key") or "").strip()
    return value or None


_ORG_UNSET = object()


class ResearchRepository:
    def __init__(self, org_id: int | None | object = _ORG_UNSET):
        if org_id is _ORG_UNSET:
            org_id = None if is_platform_admin_request() else get_current_org_id()
        self.org_id = int(org_id) if org_id is not None else None

    @classmethod
    def global_scope(cls) -> "ResearchRepository":
        return cls(org_id=None)

    def for_org(self, org_id: int) -> "ResearchRepository":
        return type(self)(org_id=org_id)

    def _apply_tenant(self, stmt, model):
        if self.org_id is None or not hasattr(model, "org_id"):
            return stmt
        return stmt.where(model.org_id == self.org_id)

    def _tenant_payload(self, model, payload: dict[str, Any]) -> dict[str, Any]:
        if self.org_id is None or not hasattr(model, "org_id"):
            return payload
        return {**payload, "org_id": self.org_id}

    def _tenant_kwargs(self, model) -> dict[str, int]:
        if self.org_id is None or not hasattr(model, "org_id"):
            return {}
        return {"org_id": self.org_id}

    def _tenant_item_visible(self, item: Any) -> bool:
        if item is None or self.org_id is None or not hasattr(item, "org_id"):
            return True
        return int(item.org_id) == self.org_id if item.org_id is not None else False

    def _claim_legacy_tenant_item(self, item: Any) -> bool:
        if item is None or self.org_id is None or not hasattr(item, "org_id"):
            return False
        if getattr(item, "org_id", None) is not None:
            return False
        item.org_id = self.org_id
        return True

    async def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            job = ResearchJob(**self._tenant_payload(ResearchJob, payload))
            session.add(job)
            await session.flush()
            await session.refresh(job)
            return self._job_to_dict(job)

    async def create_research_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.create_job(payload)

    async def list_jobs(self) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchJob), ResearchJob)
            result = await session.execute(
                stmt.order_by(ResearchJob.created_at.desc())
            )
            return [self._job_to_dict(job) for job in result.scalars().all()]

    async def list_jobs_for_project(self, project_keys: list[str]) -> list[dict[str, Any]]:
        keys = [str(key).strip() for key in project_keys if str(key).strip()]
        if not keys:
            return []
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchJob), ResearchJob)
            result = await session.execute(
                stmt
                .where(ResearchJob.topic.in_(keys))
                .order_by(ResearchJob.created_at.desc())
            )
            return [self._job_to_dict(job) for job in result.scalars().all()]

    async def get_job(self, job_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            job = await session.get(ResearchJob, job_id)
            if job is None or not self._tenant_item_visible(job):
                return None
            return self._job_to_dict(job)

    async def update_job(self, job_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        async with get_session() as session:
            job = await session.get(ResearchJob, job_id)
            if job is None or not self._tenant_item_visible(job):
                return None
            for key, value in payload.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            await session.flush()
            await session.refresh(job)
            return self._job_to_dict(job)

    async def retag_project_jobs(self, old_project_key: str, new_project_key: str) -> dict[str, Any]:
        old_key = str(old_project_key or "").strip()
        new_key = str(new_project_key or "").strip()
        if not old_key or not new_key or old_key == new_key:
            return {"updated": 0, "old_project_key": old_key, "new_project_key": new_key}
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchJob), ResearchJob)
            result = await session.execute(
                stmt.where(ResearchJob.topic == old_key)
            )
            jobs = list(result.scalars().all())
            for job in jobs:
                job.topic = new_key
            await session.flush()
            return {
                "updated": len(jobs),
                "old_project_key": old_key,
                "new_project_key": new_key,
            }

    async def update_job_status(self, job_id: int, status: str) -> dict[str, Any] | None:
        return await self.update_job(job_id, {"status": status})

    async def list_events(self, job_id: int, limit: int = 200) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(CrawlEvent), CrawlEvent)
            stmt = (
                stmt
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

    async def get_job_stats_many(self, job_ids: list[int]) -> dict[int, dict[str, Any]]:
        normalized_job_ids = sorted({int(job_id) for job_id in job_ids})
        if not normalized_job_ids:
            return {}
        async with get_session() as session:
            post_counts = await self._count_many(session, ResearchPost, normalized_job_ids)
            comment_counts = await self._count_many(session, ResearchComment, normalized_job_ids)
            author_counts = await self._count_many(session, ResearchAuthor, normalized_job_ids)
            raw_record_counts = await self._count_many(session, RawRecord, normalized_job_ids)
            post_platform_counts = await self._count_by_platform_many(session, ResearchPost, normalized_job_ids)
            comment_platform_counts = await self._count_by_platform_many(session, ResearchComment, normalized_job_ids)

        stats_by_job_id: dict[int, dict[str, Any]] = {}
        for job_id in normalized_job_ids:
            stats_by_job_id[job_id] = {
                "posts": int(post_counts.get(job_id, 0)),
                "comments": int(comment_counts.get(job_id, 0)),
                "authors": int(author_counts.get(job_id, 0)),
                "raw_records": int(raw_record_counts.get(job_id, 0)),
                "by_platform": {
                    "posts": post_platform_counts.get(job_id, {}),
                    "comments": comment_platform_counts.get(job_id, {}),
                },
            }
        return stats_by_job_id

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
            existing_stmt = self._apply_tenant(
                select(ResearchCrawlUnit.unit_key),
                ResearchCrawlUnit,
            )
            existing_result = await session.execute(
                existing_stmt.where(
                    ResearchCrawlUnit.job_id == job_id,
                    ResearchCrawlUnit.unit_key.in_(unit_keys),
                )
            )
            existing_keys = set(existing_result.scalars().all())
            created = 0
            for unit in units:
                if unit["unit_key"] in existing_keys:
                    continue
                session.add(ResearchCrawlUnit(**self._tenant_payload(ResearchCrawlUnit, unit)))
                created += 1

            await session.flush()
            stmt = self._apply_tenant(select(ResearchCrawlUnit), ResearchCrawlUnit)
            result = await session.execute(
                stmt
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
            stmt = self._apply_tenant(select(ResearchCrawlUnit), ResearchCrawlUnit).where(
                ResearchCrawlUnit.job_id == job_id
            )
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
        ignore_schedule: bool = False,
    ) -> dict[str, Any] | None:
        await self.release_stale_crawl_units(lock_timeout_seconds=lock_timeout_seconds)
        now = datetime.now(timezone.utc)
        async with get_session() as session:
            stmt = (
                self._apply_tenant(select(ResearchCrawlUnit), ResearchCrawlUnit)
                .where(
                    ResearchCrawlUnit.status.in_(statuses),
                )
                .order_by(ResearchCrawlUnit.priority.asc(), ResearchCrawlUnit.id.asc())
                .limit(1)
            )
            if not ignore_schedule:
                stmt = stmt.where(
                    or_(
                        ResearchCrawlUnit.scheduled_at.is_(None),
                        ResearchCrawlUnit.scheduled_at <= now,
                    )
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
            if unit is None or not self._tenant_item_visible(unit):
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

    async def bulk_update_crawl_unit_status(
        self,
        *,
        job_id: int,
        status: str,
        platform: str | None = None,
        from_statuses: tuple[str, ...] | None = None,
        last_error: str | None = None,
    ) -> int:
        now = datetime.now(timezone.utc)
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchCrawlUnit), ResearchCrawlUnit).where(
                ResearchCrawlUnit.job_id == job_id
            )
            if platform is not None:
                stmt = stmt.where(ResearchCrawlUnit.platform == platform)
            if from_statuses:
                stmt = stmt.where(ResearchCrawlUnit.status.in_(from_statuses))
            result = await session.execute(stmt)
            units = list(result.scalars().all())
            for unit in units:
                unit.status = status
                unit.last_error = last_error
                if status == CRAWL_UNIT_RUNNING:
                    unit.started_at = unit.started_at or now
                    unit.scheduled_at = unit.scheduled_at or now
                    unit.locked_by = None
                    unit.locked_at = None
                    unit.attempt_count = max(1, int(unit.attempt_count or 0))
                elif status == CRAWL_UNIT_RETRYING:
                    unit.scheduled_at = now + timedelta(
                        seconds=retry_backoff_seconds(int(unit.attempt_count or 1))
                    )
                    unit.locked_by = None
                    unit.locked_at = None
                elif status in CRAWL_UNIT_TERMINAL_STATUSES:
                    unit.finished_at = now
                    unit.locked_by = None
                    unit.locked_at = None
            await session.flush()
            return len(units)

    async def release_stale_crawl_units(
        self, *, lock_timeout_seconds: int = 1800
    ) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=lock_timeout_seconds)
        async with get_session() as session:
            result = await session.execute(
                self._apply_tenant(select(ResearchCrawlUnit), ResearchCrawlUnit).where(
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
                self._apply_tenant(select(ResearchCrawlUnit.status, func.count()), ResearchCrawlUnit)
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
                self._apply_tenant(select(func.count()).select_from(ResearchCrawlUnit), ResearchCrawlUnit)
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

    async def create_lead(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchLead(**self._tenant_payload(ResearchLead, payload))
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._lead_to_dict(item)

    async def update_lead(self, lead_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchLead, lead_id)
            if item is None or not self._tenant_item_visible(item):
                return None
            for key, value in payload.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._lead_to_dict(item)

    async def get_lead(self, lead_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchLead, lead_id)
            if item is not None and not self._tenant_item_visible(item):
                return None
            return self._lead_to_dict(item) if item else None

    async def get_lead_by_external_id(
        self,
        project_id: int,
        external_lead_id: str,
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            result = await session.execute(
                self._apply_tenant(select(ResearchLead), ResearchLead).where(
                    ResearchLead.project_id == project_id,
                    ResearchLead.external_lead_id == external_lead_id,
                )
            )
            item = result.scalar_one_or_none()
            return self._lead_to_dict(item) if item else None

    async def find_lead_for_dedupe(
        self,
        *,
        project_id: int,
        dedupe_by: str,
        external_lead_id: str | None = None,
        phone_hash: str | None = None,
        wechat_hash: str | None = None,
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            conditions = [ResearchLead.project_id == project_id]
            if dedupe_by == "phone_hash" and phone_hash:
                conditions.append(ResearchLead.phone_hash == phone_hash)
            elif dedupe_by == "wechat_hash" and wechat_hash:
                conditions.append(ResearchLead.wechat_hash == wechat_hash)
            elif external_lead_id:
                conditions.append(ResearchLead.external_lead_id == external_lead_id)
            else:
                return None
            result = await session.execute(
                self._apply_tenant(select(ResearchLead), ResearchLead).where(*conditions)
            )
            item = result.scalar_one_or_none()
            return self._lead_to_dict(item) if item else None

    async def list_project_leads(
        self,
        project_id: int,
        *,
        status: str | None = None,
        platform: str | None = None,
        keyword: str | None = None,
        owner: str | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchLead), ResearchLead).where(
                ResearchLead.project_id == project_id
            )
            if status:
                stmt = stmt.where(ResearchLead.lead_status == status)
            if platform:
                stmt = stmt.where(ResearchLead.source_platform == platform)
            if keyword:
                stmt = stmt.where(ResearchLead.source_keyword == keyword)
            if owner:
                stmt = stmt.where(ResearchLead.owner == owner)
            stmt = stmt.order_by(ResearchLead.created_at.desc(), ResearchLead.id.desc())
            result = await session.execute(stmt)
            return [self._lead_to_dict(item) for item in result.scalars().all()]

    async def list_all_leads(
        self,
        *,
        status: str | None = None,
        platform: str | None = None,
        keyword: str | None = None,
        owner: str | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchLead), ResearchLead)
            if status:
                stmt = stmt.where(ResearchLead.lead_status == status)
            if platform:
                stmt = stmt.where(ResearchLead.source_platform == platform)
            if keyword:
                stmt = stmt.where(ResearchLead.source_keyword == keyword)
            if owner:
                stmt = stmt.where(ResearchLead.owner == owner)
            stmt = stmt.order_by(ResearchLead.created_at.desc(), ResearchLead.id.desc())
            result = await session.execute(stmt)
            return [self._lead_to_dict(item) for item in result.scalars().all()]

    async def create_lead_touchpoint(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchLeadTouchpoint(
                **self._tenant_payload(ResearchLeadTouchpoint, payload)
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._lead_touchpoint_to_dict(item)

    async def find_lead_touchpoint_for_dedupe(
        self,
        *,
        lead_id: int,
        touch_type: str,
        platform: str | None,
        source_keyword: str | None,
        post_id: int | None,
        raw_record_id: int | None,
        touch_time: datetime,
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchLeadTouchpoint),
                ResearchLeadTouchpoint,
            ).where(
                ResearchLeadTouchpoint.lead_id == lead_id,
                ResearchLeadTouchpoint.touch_type == touch_type,
                ResearchLeadTouchpoint.touch_time == touch_time,
            )
            if platform is None:
                stmt = stmt.where(ResearchLeadTouchpoint.platform.is_(None))
            else:
                stmt = stmt.where(ResearchLeadTouchpoint.platform == platform)
            if source_keyword is None:
                stmt = stmt.where(ResearchLeadTouchpoint.source_keyword.is_(None))
            else:
                stmt = stmt.where(ResearchLeadTouchpoint.source_keyword == source_keyword)
            if post_id is None:
                stmt = stmt.where(ResearchLeadTouchpoint.post_id.is_(None))
            else:
                stmt = stmt.where(ResearchLeadTouchpoint.post_id == post_id)
            if raw_record_id is None:
                stmt = stmt.where(ResearchLeadTouchpoint.raw_record_id.is_(None))
            else:
                stmt = stmt.where(ResearchLeadTouchpoint.raw_record_id == raw_record_id)
            result = await session.execute(stmt.limit(1))
            item = result.scalar_one_or_none()
            return self._lead_touchpoint_to_dict(item) if item else None

    async def list_lead_touchpoints(self, lead_id: int) -> list[dict[str, Any]]:
        async with get_session() as session:
            result = await session.execute(
                self._apply_tenant(
                    select(ResearchLeadTouchpoint),
                    ResearchLeadTouchpoint,
                )
                .where(ResearchLeadTouchpoint.lead_id == lead_id)
                .order_by(
                    ResearchLeadTouchpoint.touch_time.asc(),
                    ResearchLeadTouchpoint.id.asc(),
                )
            )
            return [self._lead_touchpoint_to_dict(item) for item in result.scalars().all()]

    async def create_lead_conversion_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchLeadConversionEvent(
                **self._tenant_payload(ResearchLeadConversionEvent, payload)
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._lead_conversion_event_to_dict(item)

    async def find_lead_conversion_event_for_dedupe(
        self,
        *,
        lead_id: int,
        event_type: str,
        event_value: float | None,
        event_count: int,
        event_time: datetime,
        source_system: str,
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchLeadConversionEvent),
                ResearchLeadConversionEvent,
            ).where(
                ResearchLeadConversionEvent.lead_id == lead_id,
                ResearchLeadConversionEvent.event_type == event_type,
                ResearchLeadConversionEvent.event_count == event_count,
                ResearchLeadConversionEvent.event_time == event_time,
                ResearchLeadConversionEvent.source_system == source_system,
            )
            if event_value is None:
                stmt = stmt.where(ResearchLeadConversionEvent.event_value.is_(None))
            else:
                stmt = stmt.where(ResearchLeadConversionEvent.event_value == event_value)
            result = await session.execute(stmt.limit(1))
            item = result.scalar_one_or_none()
            return self._lead_conversion_event_to_dict(item) if item else None

    async def list_lead_conversion_events(self, lead_id: int) -> list[dict[str, Any]]:
        async with get_session() as session:
            result = await session.execute(
                self._apply_tenant(
                    select(ResearchLeadConversionEvent),
                    ResearchLeadConversionEvent,
                )
                .where(ResearchLeadConversionEvent.lead_id == lead_id)
                .order_by(
                    ResearchLeadConversionEvent.event_time.asc(),
                    ResearchLeadConversionEvent.id.asc(),
                )
            )
            return [self._lead_conversion_event_to_dict(item) for item in result.scalars().all()]

    async def list_project_conversion_events(
        self,
        project_id: int,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchLeadConversionEvent),
                ResearchLeadConversionEvent,
            ).where(
                ResearchLeadConversionEvent.project_id == project_id
            )
            if start_at is not None:
                stmt = stmt.where(ResearchLeadConversionEvent.event_time >= start_at)
            if end_at is not None:
                stmt = stmt.where(ResearchLeadConversionEvent.event_time <= end_at)
            stmt = stmt.order_by(
                ResearchLeadConversionEvent.event_time.asc(),
                ResearchLeadConversionEvent.id.asc(),
            )
            result = await session.execute(stmt)
            return [self._lead_conversion_event_to_dict(item) for item in result.scalars().all()]

    async def list_all_conversion_events(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchLeadConversionEvent),
                ResearchLeadConversionEvent,
            )
            if start_at is not None:
                stmt = stmt.where(ResearchLeadConversionEvent.event_time >= start_at)
            if end_at is not None:
                stmt = stmt.where(ResearchLeadConversionEvent.event_time <= end_at)
            stmt = stmt.order_by(
                ResearchLeadConversionEvent.event_time.asc(),
                ResearchLeadConversionEvent.id.asc(),
            )
            result = await session.execute(stmt)
            return [self._lead_conversion_event_to_dict(item) for item in result.scalars().all()]

    async def replace_lead_attribution_results(
        self,
        *,
        conversion_event_id: int,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            await session.execute(
                self._apply_tenant(
                    delete(ResearchLeadAttributionResult),
                    ResearchLeadAttributionResult,
                ).where(ResearchLeadAttributionResult.conversion_event_id == conversion_event_id)
            )
            created: list[ResearchLeadAttributionResult] = []
            for payload in rows:
                item = ResearchLeadAttributionResult(
                    **self._tenant_payload(ResearchLeadAttributionResult, payload)
                )
                session.add(item)
                created.append(item)
            await session.flush()
            for item in created:
                await session.refresh(item)
            return [self._lead_attribution_result_to_dict(item) for item in created]

    async def list_project_attribution_results(
        self,
        project_id: int,
        *,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchLeadAttributionResult),
                ResearchLeadAttributionResult,
            ).where(
                ResearchLeadAttributionResult.project_id == project_id
            )
            if model:
                stmt = stmt.where(ResearchLeadAttributionResult.model == model)
            stmt = stmt.order_by(
                ResearchLeadAttributionResult.computed_at.desc(),
                ResearchLeadAttributionResult.id.desc(),
            )
            result = await session.execute(stmt)
            return [self._lead_attribution_result_to_dict(item) for item in result.scalars().all()]

    async def list_all_attribution_results(
        self,
        *,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchLeadAttributionResult),
                ResearchLeadAttributionResult,
            )
            if model:
                stmt = stmt.where(ResearchLeadAttributionResult.model == model)
            stmt = stmt.order_by(
                ResearchLeadAttributionResult.computed_at.desc(),
                ResearchLeadAttributionResult.id.desc(),
            )
            result = await session.execute(stmt)
            return [self._lead_attribution_result_to_dict(item) for item in result.scalars().all()]

    async def create_lead_attribution_spend(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchLeadAttributionSpend(
                **self._tenant_payload(ResearchLeadAttributionSpend, payload)
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._lead_attribution_spend_to_dict(item)

    async def find_lead_attribution_spend_for_dedupe(
        self,
        *,
        project_id: int,
        spend_date: date,
        dimension: str,
        dimension_key: str,
        source_system: str,
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            result = await session.execute(
                self._apply_tenant(
                    select(ResearchLeadAttributionSpend),
                    ResearchLeadAttributionSpend,
                ).where(
                    ResearchLeadAttributionSpend.project_id == project_id,
                    ResearchLeadAttributionSpend.spend_date == spend_date,
                    ResearchLeadAttributionSpend.dimension == dimension,
                    ResearchLeadAttributionSpend.dimension_key == dimension_key,
                    ResearchLeadAttributionSpend.source_system == source_system,
                )
            )
            item = result.scalar_one_or_none()
            return self._lead_attribution_spend_to_dict(item) if item else None

    async def update_lead_attribution_spend(
        self,
        spend_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchLeadAttributionSpend, spend_id)
            if item is None or not self._tenant_item_visible(item):
                return None
            for key, value in payload.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._lead_attribution_spend_to_dict(item)

    async def list_project_attribution_spend(
        self,
        project_id: int,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchLeadAttributionSpend),
                ResearchLeadAttributionSpend,
            ).where(
                ResearchLeadAttributionSpend.project_id == project_id
            )
            if start_date is not None:
                stmt = stmt.where(ResearchLeadAttributionSpend.spend_date >= start_date)
            if end_date is not None:
                stmt = stmt.where(ResearchLeadAttributionSpend.spend_date <= end_date)
            stmt = stmt.order_by(
                ResearchLeadAttributionSpend.spend_date.asc(),
                ResearchLeadAttributionSpend.id.asc(),
            )
            result = await session.execute(stmt)
            return [self._lead_attribution_spend_to_dict(item) for item in result.scalars().all()]

    async def list_all_attribution_spend(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchLeadAttributionSpend),
                ResearchLeadAttributionSpend,
            )
            if start_date is not None:
                stmt = stmt.where(ResearchLeadAttributionSpend.spend_date >= start_date)
            if end_date is not None:
                stmt = stmt.where(ResearchLeadAttributionSpend.spend_date <= end_date)
            stmt = stmt.order_by(
                ResearchLeadAttributionSpend.spend_date.asc(),
                ResearchLeadAttributionSpend.id.asc(),
            )
            result = await session.execute(stmt)
            return [self._lead_attribution_spend_to_dict(item) for item in result.scalars().all()]

    async def create_lead_attribution_daily_snapshot(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        async with get_session() as session:
            result = await session.execute(
                self._apply_tenant(
                    select(ResearchLeadAttributionDailySnapshot),
                    ResearchLeadAttributionDailySnapshot,
                ).where(
                    ResearchLeadAttributionDailySnapshot.project_id == payload["project_id"],
                    ResearchLeadAttributionDailySnapshot.model == payload["model"],
                    ResearchLeadAttributionDailySnapshot.snapshot_date == payload["snapshot_date"],
                )
            )
            incoming_summary = payload.get("summary_json") or {}
            incoming_date_from = incoming_summary.get("date_from")
            incoming_date_to = incoming_summary.get("date_to")
            for existing in result.scalars().all():
                existing_summary = existing.summary_json or {}
                if (
                    existing_summary.get("date_from") == incoming_date_from
                    and existing_summary.get("date_to") == incoming_date_to
                ):
                    await session.delete(existing)
            item = ResearchLeadAttributionDailySnapshot(
                **self._tenant_payload(ResearchLeadAttributionDailySnapshot, payload)
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._lead_attribution_daily_snapshot_to_dict(item)

    async def get_latest_lead_attribution_daily_snapshot(
        self,
        project_id: int,
        *,
        model: str,
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            result = await session.execute(
                self._apply_tenant(
                    select(ResearchLeadAttributionDailySnapshot),
                    ResearchLeadAttributionDailySnapshot,
                )
                .where(
                    ResearchLeadAttributionDailySnapshot.project_id == project_id,
                    ResearchLeadAttributionDailySnapshot.model == model,
                )
                .order_by(
                    ResearchLeadAttributionDailySnapshot.snapshot_date.desc(),
                    ResearchLeadAttributionDailySnapshot.id.desc(),
                )
            )
            item = result.scalars().first()
            return self._lead_attribution_daily_snapshot_to_dict(item) if item else None

    async def get_matching_lead_attribution_daily_snapshot(
        self,
        project_id: int,
        *,
        model: str,
        date_from: str | None,
        date_to: str | None,
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            result = await session.execute(
                self._apply_tenant(
                    select(ResearchLeadAttributionDailySnapshot),
                    ResearchLeadAttributionDailySnapshot,
                )
                .where(
                    ResearchLeadAttributionDailySnapshot.project_id == project_id,
                    ResearchLeadAttributionDailySnapshot.model == model,
                )
                .order_by(
                    ResearchLeadAttributionDailySnapshot.snapshot_date.desc(),
                    ResearchLeadAttributionDailySnapshot.id.desc(),
                )
            )
            for item in result.scalars().all():
                summary = item.summary_json or {}
                if summary.get("date_from") == date_from and summary.get("date_to") == date_to:
                    return self._lead_attribution_daily_snapshot_to_dict(item)
            return None

    async def create_keyword_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchKeywordSet(**self._tenant_payload(ResearchKeywordSet, payload))
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._keyword_set_to_dict(item)

    async def list_keyword_sets(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchKeywordSet), ResearchKeywordSet)
            if enabled_only:
                stmt = stmt.where(ResearchKeywordSet.enabled.is_(True))
            result = await session.execute(stmt.order_by(ResearchKeywordSet.id.desc()))
            return [self._keyword_set_to_dict(item) for item in result.scalars().all()]

    async def update_keyword_set(
        self, keyword_set_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchKeywordSet, keyword_set_id)
            if item is None or not self._tenant_item_visible(item):
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
            stmt = self._apply_tenant(select(ResearchEntityTag), ResearchEntityTag).where(
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
                item = ResearchEntityTag(**self._tenant_payload(ResearchEntityTag, payload))
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
            stmt = self._apply_tenant(select(ResearchEntityTag), ResearchEntityTag)
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
            stmt = self._apply_tenant(select(ResearchEntityTag), ResearchEntityTag).where(
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
            stmt = self._apply_tenant(select(ResearchCreatorProfile), ResearchCreatorProfile).where(
                ResearchCreatorProfile.platform == payload["platform"],
                ResearchCreatorProfile.creator_id == payload["creator_id"],
            )
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchCreatorProfile(
                    **self._tenant_payload(ResearchCreatorProfile, payload)
                )
                session.add(item)
            else:
                for key, value in payload.items():
                    if hasattr(item, key) and value not in (None, "", [], {}):
                        setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._creator_profile_to_dict(item)

    async def list_creator_profiles(
        self, *, platforms: list[str] | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchCreatorProfile), ResearchCreatorProfile)
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
                self._apply_tenant(select(ResearchCreatorProfile), ResearchCreatorProfile).where(
                    ResearchCreatorProfile.platform == platform,
                    ResearchCreatorProfile.creator_id == creator_id,
                )
            )
            item = result.scalar_one_or_none()
            return self._creator_profile_to_dict(item) if item else None

    async def upsert_creator_daily_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchCreatorDailySnapshot),
                ResearchCreatorDailySnapshot,
            ).where(
                ResearchCreatorDailySnapshot.platform == payload["platform"],
                ResearchCreatorDailySnapshot.creator_id == payload["creator_id"],
                ResearchCreatorDailySnapshot.snapshot_date == payload["snapshot_date"],
            )
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchCreatorDailySnapshot(
                    **self._tenant_payload(ResearchCreatorDailySnapshot, payload)
                )
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
            stmt = self._apply_tenant(
                select(ResearchCreatorDailySnapshot),
                ResearchCreatorDailySnapshot,
            )
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
            stmt = self._apply_tenant(
                select(ResearchCreatorCandidate),
                ResearchCreatorCandidate,
            ).where(
                ResearchCreatorCandidate.platform == payload["platform"],
                ResearchCreatorCandidate.creator_id == payload["creator_id"],
                ResearchCreatorCandidate.pool_name == payload["pool_name"],
            )
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchCreatorCandidate(
                    **self._tenant_payload(ResearchCreatorCandidate, payload)
                )
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
            stmt = self._apply_tenant(select(ResearchCreatorCandidate), ResearchCreatorCandidate)
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
            item = ResearchSearchIntent(**self._tenant_payload(ResearchSearchIntent, payload))
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._search_intent_to_dict(item)

    async def create_creator_search_session(
        self,
        payload: dict[str, Any],
        *,
        results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        results = [as_record for as_record in (results or []) if isinstance(as_record, dict)]
        session_payload = {
            "raw_query": str(payload.get("raw_query") or ""),
            "selected_vertical_id": payload.get("selected_vertical_id"),
            "search_payload_json": _json_safe(payload.get("search_payload_json") or {}),
            "view_state_json": _json_safe(payload.get("view_state_json") or {}),
            "diagnostics_json": _json_safe(payload.get("diagnostics_json") or {}),
            "realtime_json": _json_safe(payload.get("realtime_json") or {}),
            "progress_json": _json_safe(payload.get("progress_json") or {}),
            "message": payload.get("message"),
            "result_summary": payload.get("result_summary"),
            "result_count": int(payload.get("result_count") or len(results)),
            "saved": bool(payload.get("saved", False)),
            "saved_name": payload.get("saved_name"),
            "status": str(payload.get("status") or "completed"),
        }
        async with get_session() as session:
            session_results: list[ResearchCreatorSearchSessionResult] = []
            item = ResearchCreatorSearchSession(
                **self._tenant_payload(ResearchCreatorSearchSession, session_payload)
            )
            session.add(item)
            await session.flush()
            if results:
                session_results = [
                    ResearchCreatorSearchSessionResult(
                        **self._tenant_payload(
                            ResearchCreatorSearchSessionResult,
                            {
                                "session_id": item.id,
                                "rank": index + 1,
                                "platform": row.get("platform"),
                                "creator_id": row.get("creator_id"),
                                "source_type": row.get("source_type"),
                                "match_score": row.get("match_score"),
                                "snapshot_json": _json_safe(row),
                            },
                        )
                    )
                    for index, row in enumerate(results)
                ]
                session.add_all(session_results)
            await session.flush()
            await session.refresh(item)
            return self._creator_search_session_to_dict(
                item,
                results=[self._creator_search_session_result_to_dict(row) for row in session_results],
            )

    async def get_creator_search_session(self, session_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchCreatorSearchSession, session_id)
            if item is None or not self._tenant_item_visible(item):
                return None
            result_stmt = self._apply_tenant(
                select(ResearchCreatorSearchSessionResult),
                ResearchCreatorSearchSessionResult,
            ).where(
                ResearchCreatorSearchSessionResult.session_id == session_id
            )
            result_rows = await session.execute(
                result_stmt.order_by(
                    ResearchCreatorSearchSessionResult.rank.asc(),
                    ResearchCreatorSearchSessionResult.id.asc(),
                )
            )
            return self._creator_search_session_to_dict(
                item,
                results=[self._creator_search_session_result_to_dict(row) for row in result_rows.scalars().all()],
            )

    async def get_latest_creator_search_session(self) -> dict[str, Any] | None:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchCreatorSearchSession),
                ResearchCreatorSearchSession,
            )
            result = await session.execute(
                stmt.order_by(
                    ResearchCreatorSearchSession.updated_at.desc(),
                    ResearchCreatorSearchSession.id.desc(),
                ).limit(1)
            )
            item = result.scalar_one_or_none()
            if item is None:
                return None
            result_stmt = self._apply_tenant(
                select(ResearchCreatorSearchSessionResult),
                ResearchCreatorSearchSessionResult,
            ).where(
                ResearchCreatorSearchSessionResult.session_id == item.id
            )
            result_rows = await session.execute(
                result_stmt.order_by(
                    ResearchCreatorSearchSessionResult.rank.asc(),
                    ResearchCreatorSearchSessionResult.id.asc(),
                )
            )
            return self._creator_search_session_to_dict(
                item,
                results=[self._creator_search_session_result_to_dict(row) for row in result_rows.scalars().all()],
            )

    async def mark_creator_search_session_saved(
        self,
        session_id: int,
        *,
        saved: bool = True,
        saved_name: str | None = None,
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchCreatorSearchSession, session_id)
            if item is None or not self._tenant_item_visible(item):
                return None
            item.saved = bool(saved)
            if saved_name is not None:
                item.saved_name = saved_name
            elif item.saved and not item.saved_name:
                item.saved_name = (item.raw_query or "").strip()[:255] or "未命名搜索"
            await session.flush()
            await session.refresh(item)
            result_stmt = self._apply_tenant(
                select(ResearchCreatorSearchSessionResult),
                ResearchCreatorSearchSessionResult,
            ).where(
                ResearchCreatorSearchSessionResult.session_id == item.id
            )
            result_rows = await session.execute(
                result_stmt.order_by(
                    ResearchCreatorSearchSessionResult.rank.asc(),
                    ResearchCreatorSearchSessionResult.id.asc(),
                )
            )
            return self._creator_search_session_to_dict(
                item,
                results=[self._creator_search_session_result_to_dict(row) for row in result_rows.scalars().all()],
            )

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
            stmt = self._apply_tenant(select(ResearchGrowthProject), ResearchGrowthProject)
            result = await session.execute(
                stmt.where(
                    ResearchGrowthProject.name == payload["name"]
                )
            )
            item = result.scalar_one_or_none()
            if item is None and self.org_id is not None:
                legacy_result = await session.execute(
                    select(ResearchGrowthProject).where(
                        ResearchGrowthProject.name == payload["name"],
                        ResearchGrowthProject.org_id.is_(None),
                    )
                )
                item = legacy_result.scalar_one_or_none()
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
                "daily_collection_limit_per_platform": payload.get(
                    "daily_collection_limit_per_platform", 50
                ),
                "sample_status": payload.get("sample_status") or "sample_insufficient",
                "recommended_action": payload.get("recommended_action") or "start_collection",
                "archived": payload.get("archived", False),
            }
            if item is None:
                item = ResearchGrowthProject(
                    name=payload["name"],
                    **values,
                    **self._tenant_kwargs(ResearchGrowthProject),
                )
                session.add(item)
            else:
                self._claim_legacy_tenant_item(item)
                for key, value in values.items():
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._growth_project_to_dict(item)

    async def list_growth_project_records(
        self, *, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchGrowthProject), ResearchGrowthProject)
            if not include_archived:
                stmt = stmt.where(ResearchGrowthProject.archived.is_(False))
            result = await session.execute(stmt.order_by(ResearchGrowthProject.updated_at.desc()))
            return [self._growth_project_to_dict(item) for item in result.scalars().all()]

    async def resolve_growth_project_record(
        self,
        project_identifier: str | int,
        *,
        include_archived: bool = False,
    ) -> dict[str, Any] | None:
        identifier = str(project_identifier or "").strip()
        if not identifier:
            return None
        if identifier.isdigit():
            record = await self.get_growth_project_record(int(identifier))
            if record and (include_archived or not record.get("archived")):
                return record
            if record is not None:
                return None
        else:
            records = await self.list_growth_project_records(include_archived=include_archived)
            for record in records:
                if _growth_project_slug(record.get("name")) == identifier:
                    return record
        if self.org_id is None:
            return None
        async with get_session() as session:
            item: ResearchGrowthProject | None = None
            if identifier.isdigit():
                candidate = await session.get(ResearchGrowthProject, int(identifier))
                if candidate is not None and candidate.org_id is None:
                    item = candidate
            else:
                result = await session.execute(
                    select(ResearchGrowthProject)
                    .where(ResearchGrowthProject.org_id.is_(None))
                    .order_by(ResearchGrowthProject.updated_at.desc(), ResearchGrowthProject.id.desc())
                )
                for candidate in result.scalars().all():
                    if _growth_project_slug(candidate.name) == identifier:
                        item = candidate
                        break
            if item is None:
                return None
            if item.archived and not include_archived:
                return None
            claimed = await self._claim_legacy_growth_project(session, item)
            if claimed is None:
                return None
            await session.flush()
            await session.refresh(claimed)
            return self._growth_project_to_dict(claimed)

    async def get_growth_project_record(self, project_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchGrowthProject, project_id)
            if item is None:
                return None
            if self.org_id is not None and item.org_id is None:
                item = await self._claim_legacy_growth_project(session, item)
                if item is None:
                    return None
                await session.flush()
                await session.refresh(item)
            if item is not None and not self._tenant_item_visible(item):
                return None
            return self._growth_project_to_dict(item) if item else None

    async def update_growth_project(
        self, project_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchGrowthProject, project_id)
            if item is None or not self._tenant_item_visible(item):
                return None
            for key, value in payload.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._growth_project_to_dict(item)

    async def _claim_legacy_growth_project(
        self,
        session,
        item: ResearchGrowthProject,
    ) -> ResearchGrowthProject | None:
        if self.org_id is None:
            return item
        if item.org_id is not None:
            return item if int(item.org_id) == self.org_id else None

        conflict = await session.execute(
            select(ResearchGrowthProject.id).where(
                ResearchGrowthProject.org_id == self.org_id,
                ResearchGrowthProject.name == item.name,
                ResearchGrowthProject.id != item.id,
            )
        )
        if conflict.scalar_one_or_none() is not None:
            return None

        project_slug = _growth_project_slug(item.name)
        explicit_project_key = _growth_project_job_key(int(item.id))
        legacy_jobs_result = await session.execute(
            select(ResearchJob)
            .where(
                ResearchJob.org_id.is_(None),
                or_(
                    ResearchJob.topic == project_slug,
                    ResearchJob.topic == item.name,
                ),
            )
            .order_by(ResearchJob.created_at.desc(), ResearchJob.id.desc())
        )
        explicit_jobs: list[ResearchJob] = []
        slug_jobs: list[ResearchJob] = []
        seen_job_ids: set[int] = set()
        for job in legacy_jobs_result.scalars().all():
            if job.id in seen_job_ids:
                continue
            seen_job_ids.add(int(job.id))
            if _job_growth_project_key(job.comment_policy) == explicit_project_key:
                explicit_jobs.append(job)
            else:
                slug_jobs.append(job)
        legacy_jobs = [*explicit_jobs, *slug_jobs]
        job_ids = [int(job.id) for job in legacy_jobs]
        analysis_job_ids: list[int] = []
        if job_ids:
            analysis_result = await session.execute(
                select(AIAnalysisJob.id).where(
                    AIAnalysisJob.org_id.is_(None),
                    AIAnalysisJob.research_job_id.in_(job_ids),
                )
            )
            analysis_job_ids = [int(job_id) for job_id in analysis_result.scalars().all()]

        item.org_id = self.org_id
        for job in legacy_jobs:
            job.org_id = self.org_id

        project_scoped_models = (
            ResearchGrowthProjectKeyword,
            ResearchGrowthProjectCollectionPlan,
            ResearchLead,
            ResearchLeadTouchpoint,
            ResearchLeadConversionEvent,
            ResearchLeadAttributionResult,
            ResearchLeadAttributionSpend,
            ResearchLeadAttributionDailySnapshot,
        )
        for model in project_scoped_models:
            await session.execute(
                update(model)
                .where(
                    model.org_id.is_(None),
                    model.project_id == item.id,
                )
                .values(org_id=self.org_id)
            )

        if job_ids:
            job_scoped_models = (
                CrawlCheckpoint,
                CrawlEvent,
                ResearchCrawlUnit,
                RawRecord,
                ResearchAuthor,
                ResearchPost,
                ResearchComment,
                ResearchCollectionRun,
            )
            for model in job_scoped_models:
                await session.execute(
                    update(model)
                    .where(
                        model.org_id.is_(None),
                        model.job_id.in_(job_ids),
                    )
                    .values(org_id=self.org_id)
                )
            await session.execute(
                update(AIAnalysisJob)
                .where(
                    AIAnalysisJob.org_id.is_(None),
                    AIAnalysisJob.research_job_id.in_(job_ids),
                )
                .values(org_id=self.org_id)
            )
        if analysis_job_ids:
            await session.execute(
                update(AIAnalysisResult)
                .where(
                    AIAnalysisResult.org_id.is_(None),
                    AIAnalysisResult.analysis_job_id.in_(analysis_job_ids),
                )
                .values(org_id=self.org_id)
            )
        await session.execute(
            update(ResearchCollectionRun)
            .where(
                ResearchCollectionRun.org_id.is_(None),
                ResearchCollectionRun.target_type == "growth_project",
                ResearchCollectionRun.target_id == item.id,
            )
            .values(org_id=self.org_id)
        )
        return item

    async def create_growth_project_keyword(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchGrowthProjectKeyword),
                ResearchGrowthProjectKeyword,
            )
            result = await session.execute(
                stmt.where(
                    ResearchGrowthProjectKeyword.project_id == payload["project_id"],
                    ResearchGrowthProjectKeyword.keyword == payload["keyword"],
                    ResearchGrowthProjectKeyword.keyword_type == payload["keyword_type"],
                )
            )
            item = result.scalar_one_or_none()
            if item is None and self.org_id is not None:
                legacy_result = await session.execute(
                    select(ResearchGrowthProjectKeyword).where(
                        ResearchGrowthProjectKeyword.project_id == payload["project_id"],
                        ResearchGrowthProjectKeyword.keyword == payload["keyword"],
                        ResearchGrowthProjectKeyword.keyword_type == payload["keyword_type"],
                        ResearchGrowthProjectKeyword.org_id.is_(None),
                    )
                )
                item = legacy_result.scalar_one_or_none()
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
                    **self._tenant_kwargs(ResearchGrowthProjectKeyword),
                )
                session.add(item)
            else:
                self._claim_legacy_tenant_item(item)
                for key, value in values.items():
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._growth_project_keyword_to_dict(item)

    async def list_growth_project_keywords(
        self, project_id: int, status: str | None = None
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchGrowthProjectKeyword),
                ResearchGrowthProjectKeyword,
            ).where(
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
            if item is None or not self._tenant_item_visible(item):
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
                self._apply_tenant(
                    select(ResearchGrowthProjectKeyword),
                    ResearchGrowthProjectKeyword,
                ).where(
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
            stmt = self._apply_tenant(
                select(ResearchGrowthProjectCollectionPlan),
                ResearchGrowthProjectCollectionPlan,
            )
            result = await session.execute(
                stmt.where(
                    ResearchGrowthProjectCollectionPlan.project_id == payload["project_id"],
                    ResearchGrowthProjectCollectionPlan.platform == payload["platform"],
                    ResearchGrowthProjectCollectionPlan.collection_mode
                    == (payload.get("collection_mode") or "search"),
                )
            )
            item = result.scalar_one_or_none()
            if item is None and self.org_id is not None:
                legacy_result = await session.execute(
                    select(ResearchGrowthProjectCollectionPlan).where(
                        ResearchGrowthProjectCollectionPlan.project_id == payload["project_id"],
                        ResearchGrowthProjectCollectionPlan.platform == payload["platform"],
                        ResearchGrowthProjectCollectionPlan.collection_mode
                        == (payload.get("collection_mode") or "search"),
                        ResearchGrowthProjectCollectionPlan.org_id.is_(None),
                    )
                )
                item = legacy_result.scalar_one_or_none()
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
                    **self._tenant_kwargs(ResearchGrowthProjectCollectionPlan),
                )
                session.add(item)
            else:
                self._claim_legacy_tenant_item(item)
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
                self._apply_tenant(
                    select(ResearchGrowthProjectCollectionPlan),
                    ResearchGrowthProjectCollectionPlan,
                )
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
                self._apply_tenant(
                    select(ResearchGrowthProjectCollectionPlan),
                    ResearchGrowthProjectCollectionPlan,
                ).where(
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

    async def sync_growth_project_collection_plans(
        self,
        project_id: int,
        *,
        platforms: list[str],
        interval_minutes: int | None,
    ) -> list[dict[str, Any]]:
        desired_platforms = list(
            dict.fromkeys([str(item).strip() for item in platforms if str(item).strip()])
        )
        desired_set = set(desired_platforms)
        schedule_mode = "interval" if interval_minutes else "manual"
        async with get_session() as session:
            result = await session.execute(
                self._apply_tenant(
                    select(ResearchGrowthProjectCollectionPlan),
                    ResearchGrowthProjectCollectionPlan,
                ).where(
                    ResearchGrowthProjectCollectionPlan.project_id == project_id,
                    ResearchGrowthProjectCollectionPlan.collection_mode == "search",
                )
            )
            plans = list(result.scalars().all())
            by_platform = {plan.platform: plan for plan in plans}

            for platform in desired_platforms:
                plan = by_platform.get(platform)
                if plan is None:
                    plan = ResearchGrowthProjectCollectionPlan(
                        project_id=project_id,
                        platform=platform,
                        collection_mode="search",
                        **self._tenant_kwargs(ResearchGrowthProjectCollectionPlan),
                    )
                    session.add(plan)
                    plans.append(plan)
                    by_platform[platform] = plan
                plan.keyword_scope = "active"
                plan.enabled = True
                plan.schedule_mode = schedule_mode
                plan.schedule_interval_minutes = interval_minutes

            for plan in plans:
                if plan.platform not in desired_set:
                    plan.enabled = False
                    plan.schedule_mode = "manual"
                    plan.schedule_interval_minutes = None

            await session.flush()
            result = await session.execute(
                self._apply_tenant(
                    select(ResearchGrowthProjectCollectionPlan),
                    ResearchGrowthProjectCollectionPlan,
                )
                .where(ResearchGrowthProjectCollectionPlan.project_id == project_id)
                .order_by(ResearchGrowthProjectCollectionPlan.id.asc())
            )
            return [
                self._growth_project_collection_plan_to_dict(item)
                for item in result.scalars().all()
            ]

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
            item = ResearchAIKeywordSuggestionSession(
                **item_payload,
                **self._tenant_kwargs(ResearchAIKeywordSuggestionSession),
            )
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
            stmt = self._apply_tenant(
                select(ResearchAIKeywordSuggestionSession),
                ResearchAIKeywordSuggestionSession,
            )
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
            if item is None or not self._tenant_item_visible(item):
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
            if item is None or not self._tenant_item_visible(item):
                return None
            item.status = "rejected"
            item.error_message = reason
            await session.flush()
            await session.refresh(item)
            return self._ai_keyword_suggestion_session_to_dict(item)

    async def create_monitor_pool(self, payload: dict[str, Any]) -> dict[str, Any]:
        item_payload = self._monitor_pool_payload(payload)
        async with get_session() as session:
            item = ResearchMonitorPool(
                **item_payload,
                **self._tenant_kwargs(ResearchMonitorPool),
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._monitor_pool_to_dict(item)

    async def get_monitor_pool(self, pool_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchMonitorPool, pool_id)
            if item is not None and not self._tenant_item_visible(item):
                return None
            return self._monitor_pool_to_dict(item) if item else None

    async def list_monitor_pools(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchMonitorPool), ResearchMonitorPool)
            if enabled_only:
                stmt = stmt.where(ResearchMonitorPool.enabled.is_(True))
            result = await session.execute(stmt.order_by(ResearchMonitorPool.id.desc()))
            return [self._monitor_pool_to_dict(item) for item in result.scalars().all()]

    async def update_monitor_pool(
        self, pool_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchMonitorPool, pool_id)
            if item is None or not self._tenant_item_visible(item):
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
                stmt = self._apply_tenant(
                    select(ResearchMonitorPoolCreator),
                    ResearchMonitorPoolCreator,
                ).where(
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
                        **self._tenant_kwargs(ResearchMonitorPoolCreator),
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
            stmt = self._apply_tenant(
                select(ResearchMonitorPoolCreator),
                ResearchMonitorPoolCreator,
            ).where(
                ResearchMonitorPoolCreator.pool_id == pool_id
            )
            if enabled_only:
                stmt = stmt.where(ResearchMonitorPoolCreator.enabled.is_(True))
            result = await session.execute(stmt.order_by(ResearchMonitorPoolCreator.id.asc()))
            return [self._monitor_pool_creator_to_dict(item) for item in result.scalars().all()]

    async def upsert_content_sample(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchContentSample), ResearchContentSample).where(
                ResearchContentSample.platform == payload["platform"],
                ResearchContentSample.content_id == payload["content_id"],
            )
            item = (await session.execute(stmt)).scalar_one_or_none()
            if item is None:
                item = ResearchContentSample(
                    **self._tenant_payload(ResearchContentSample, payload)
                )
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
                    **self._tenant_kwargs(ResearchExtractedContentKeyword),
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
                    **self._tenant_kwargs(ResearchSimilarContentCandidate),
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
            item = ResearchContentTracker(
                **item_payload,
                **self._tenant_kwargs(ResearchContentTracker),
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._content_tracker_to_dict(item)

    async def list_content_trackers(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchContentTracker), ResearchContentTracker)
            if enabled_only:
                stmt = stmt.where(ResearchContentTracker.enabled.is_(True))
            result = await session.execute(stmt.order_by(ResearchContentTracker.id.desc()))
            return [self._content_tracker_to_dict(item) for item in result.scalars().all()]

    async def get_content_tracker(self, tracker_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchContentTracker, tracker_id)
            if item is not None and not self._tenant_item_visible(item):
                return None
            return self._content_tracker_to_dict(item) if item else None

    async def update_content_tracker(
        self, tracker_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        item_payload = self._content_tracker_payload(payload, partial=True)
        async with get_session() as session:
            item = await session.get(ResearchContentTracker, tracker_id)
            if item is None or not self._tenant_item_visible(item):
                return None
            for key, value in item_payload.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._content_tracker_to_dict(item)

    async def set_content_tracker_latest_analysis(
        self,
        *,
        tracker_id: int,
        run_id: int,
        snapshot_id: int,
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchContentTracker, tracker_id)
            if item is None or not self._tenant_item_visible(item):
                return None
            item.latest_analysis_run_id = run_id
            item.latest_analysis_snapshot_id = snapshot_id
            await session.flush()
            await session.refresh(item)
            return self._content_tracker_to_dict(item)

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
                **self._tenant_kwargs(ResearchContentTrackingSnapshot),
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
            stmt = self._apply_tenant(
                select(ResearchContentTrackingSnapshot),
                ResearchContentTrackingSnapshot,
            )
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

    async def create_collection_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchCollectionRun(
                run_type=payload["run_type"],
                target_type=payload["target_type"],
                target_id=int(payload["target_id"]),
                mode=payload.get("mode", "collect_only"),
                trigger_source=payload.get("trigger_source", "manual"),
                status=payload.get("status", "queued"),
                phase=payload.get("phase", "queued"),
                job_id=payload.get("job_id"),
                analysis_run_id=payload.get("analysis_run_id"),
                started_at=payload.get("started_at"),
                completed_at=payload.get("completed_at"),
                request_payload_json=_json_safe(payload.get("request_payload") or {}),
                summary_json=_json_safe(payload.get("summary") or {}),
                error_json=_json_safe(payload.get("error") or {}),
                **self._tenant_kwargs(ResearchCollectionRun),
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._collection_run_to_dict(item)

    async def update_collection_run(
        self, run_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchCollectionRun, run_id)
            if item is None or not self._tenant_item_visible(item):
                return None
            mapping = {
                "run_type": "run_type",
                "target_type": "target_type",
                "target_id": "target_id",
                "mode": "mode",
                "trigger_source": "trigger_source",
                "status": "status",
                "phase": "phase",
                "job_id": "job_id",
                "analysis_run_id": "analysis_run_id",
                "started_at": "started_at",
                "completed_at": "completed_at",
            }
            for source, target in mapping.items():
                if source in payload:
                    setattr(item, target, payload[source])
            if "request_payload" in payload:
                item.request_payload_json = _json_safe(payload.get("request_payload") or {})
            if "summary" in payload:
                item.summary_json = _json_safe(payload.get("summary") or {})
            if "error" in payload:
                item.error_json = _json_safe(payload.get("error") or {})
            await session.flush()
            await session.refresh(item)
            return self._collection_run_to_dict(item)

    async def get_collection_run(self, run_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchCollectionRun, run_id)
            if item is not None and not self._tenant_item_visible(item):
                return None
            return self._collection_run_to_dict(item) if item else None

    async def list_collection_runs(
        self,
        *,
        target_type: str | None = None,
        target_id: int | None = None,
        run_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchCollectionRun), ResearchCollectionRun)
            if target_type is not None:
                stmt = stmt.where(ResearchCollectionRun.target_type == target_type)
            if target_id is not None:
                stmt = stmt.where(ResearchCollectionRun.target_id == target_id)
            if run_type is not None:
                stmt = stmt.where(ResearchCollectionRun.run_type == run_type)
            stmt = stmt.order_by(
                ResearchCollectionRun.created_at.desc(),
                ResearchCollectionRun.id.desc(),
            ).limit(max(1, min(limit, 100)))
            result = await session.execute(stmt)
            return [self._collection_run_to_dict(item) for item in result.scalars().all()]

    async def create_content_tracker_analysis_run(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchContentTrackerAnalysisRun(
                tracker_id=payload["tracker_id"],
                status=payload.get("status", "completed"),
                analysis_version=payload.get("analysis_version", "v1"),
                window_days=int(payload.get("window_days") or 7),
                started_at=payload.get("started_at"),
                completed_at=payload.get("completed_at"),
                sample_count=int(payload.get("sample_count") or 0),
                candidate_count=int(payload.get("candidate_count") or 0),
                sample_quality_score=float(payload.get("sample_quality_score") or 0.0),
                trend_strength_score=float(payload.get("trend_strength_score") or 0.0),
                noise_rate=float(payload.get("noise_rate") or 0.0),
                decision_confidence=float(payload.get("decision_confidence") or 0.0),
                input_summary_json=_json_safe(payload.get("input_summary") or {}),
                summary_json=_json_safe(payload.get("summary") or {}),
                error_message=payload.get("error_message"),
                **self._tenant_kwargs(ResearchContentTrackerAnalysisRun),
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._content_tracker_analysis_run_to_dict(item)

    async def update_content_tracker_analysis_run(
        self, run_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchContentTrackerAnalysisRun, run_id)
            if item is None or not self._tenant_item_visible(item):
                return None
            mapping = {
                "status": "status",
                "analysis_version": "analysis_version",
                "window_days": "window_days",
                "started_at": "started_at",
                "completed_at": "completed_at",
                "sample_count": "sample_count",
                "candidate_count": "candidate_count",
                "sample_quality_score": "sample_quality_score",
                "trend_strength_score": "trend_strength_score",
                "noise_rate": "noise_rate",
                "decision_confidence": "decision_confidence",
                "error_message": "error_message",
            }
            for source, target in mapping.items():
                if source in payload:
                    setattr(item, target, payload[source])
            if "input_summary" in payload:
                item.input_summary_json = _json_safe(payload.get("input_summary") or {})
            if "summary" in payload:
                item.summary_json = _json_safe(payload.get("summary") or {})
            await session.flush()
            await session.refresh(item)
            return self._content_tracker_analysis_run_to_dict(item)

    async def get_content_tracker_analysis_run(
        self, run_id: int
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchContentTrackerAnalysisRun, run_id)
            if item is not None and not self._tenant_item_visible(item):
                return None
            return self._content_tracker_analysis_run_to_dict(item) if item else None

    async def create_content_tracker_analysis_snapshot(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        async with get_session() as session:
            item = ResearchContentTrackerAnalysisSnapshot(
                tracker_id=payload["tracker_id"],
                run_id=payload["run_id"],
                snapshot_date=payload["snapshot_date"],
                status=payload.get("status", "ready"),
                overview_json=_json_safe(payload.get("overview") or {}),
                trends_json=_json_safe(payload.get("trends") or {}),
                keywords_json=_json_safe(payload.get("keywords") or {}),
                patterns_json=_json_safe(payload.get("patterns") or {}),
                creators_json=_json_safe(payload.get("creators") or {}),
                samples_json=_json_safe(payload.get("samples") or {}),
                risks_json=_json_safe(payload.get("risks") or {}),
                decisions_json=_json_safe(payload.get("decisions") or {}),
                meta_json=_json_safe(payload.get("meta") or {}),
                **self._tenant_kwargs(ResearchContentTrackerAnalysisSnapshot),
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._content_tracker_analysis_snapshot_to_dict(item)

    async def get_latest_content_tracker_analysis_snapshot(
        self, tracker_id: int
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            tracker = await session.get(ResearchContentTracker, tracker_id)
            if tracker is None or not self._tenant_item_visible(tracker):
                return None
            if tracker.latest_analysis_snapshot_id:
                latest = await session.get(
                    ResearchContentTrackerAnalysisSnapshot,
                    tracker.latest_analysis_snapshot_id,
                )
                if (
                    latest is not None
                    and self._tenant_item_visible(latest)
                    and latest.tracker_id == tracker_id
                ):
                    return self._content_tracker_analysis_snapshot_to_dict(latest)

            stmt = (
                self._apply_tenant(
                    select(ResearchContentTrackerAnalysisSnapshot),
                    ResearchContentTrackerAnalysisSnapshot,
                )
                .where(ResearchContentTrackerAnalysisSnapshot.tracker_id == tracker_id)
                .order_by(
                    ResearchContentTrackerAnalysisSnapshot.snapshot_date.desc(),
                    ResearchContentTrackerAnalysisSnapshot.id.desc(),
                )
                .limit(1)
            )
            item = (await session.execute(stmt)).scalar_one_or_none()
            return self._content_tracker_analysis_snapshot_to_dict(item) if item else None

    async def list_content_tracker_analysis_snapshots(
        self, *, tracker_id: int, limit: int = 20
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = (
                self._apply_tenant(
                    select(ResearchContentTrackerAnalysisSnapshot),
                    ResearchContentTrackerAnalysisSnapshot,
                )
                .where(ResearchContentTrackerAnalysisSnapshot.tracker_id == tracker_id)
                .order_by(
                    ResearchContentTrackerAnalysisSnapshot.snapshot_date.desc(),
                    ResearchContentTrackerAnalysisSnapshot.id.desc(),
                )
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [
                self._content_tracker_analysis_snapshot_to_dict(item)
                for item in result.scalars().all()
            ]

    async def replace_content_tracker_candidate_samples(
        self,
        *,
        run_id: int,
        tracker_id: int,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            existing = await session.execute(
                self._apply_tenant(
                    select(ResearchContentTrackerCandidateSample),
                    ResearchContentTrackerCandidateSample,
                ).where(
                    ResearchContentTrackerCandidateSample.run_id == run_id
                )
            )
            for item in existing.scalars().all():
                await session.delete(item)

            rows: list[ResearchContentTrackerCandidateSample] = []
            for candidate in candidates:
                item = ResearchContentTrackerCandidateSample(
                    tracker_id=tracker_id,
                    run_id=run_id,
                    platform=candidate["platform"],
                    platform_post_id=candidate["platform_post_id"],
                    author_id=candidate.get("author_id"),
                    title=candidate.get("title"),
                    url=candidate.get("url"),
                    publish_time=candidate.get("publish_time"),
                    candidate_level=candidate.get("candidate_level", "L2"),
                    similarity_score=float(candidate.get("similarity_score") or 0.0),
                    engagement_total=int(candidate.get("engagement_total") or 0),
                    is_hot=bool(candidate.get("is_hot")),
                    matched_keywords_json=_json_safe(candidate.get("matched_keywords") or []),
                    fingerprint_json=_json_safe(candidate.get("fingerprint") or {}),
                    engagement_json=_json_safe(candidate.get("engagement") or {}),
                    evidence_json=_json_safe(candidate.get("evidence") or {}),
                    **self._tenant_kwargs(ResearchContentTrackerCandidateSample),
                )
                session.add(item)
                rows.append(item)
            await session.flush()
            for item in rows:
                await session.refresh(item)
            return [self._content_tracker_candidate_sample_to_dict(item) for item in rows]

    async def list_content_tracker_candidate_samples(
        self,
        *,
        run_id: int,
        candidate_level: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchContentTrackerCandidateSample),
                ResearchContentTrackerCandidateSample,
            ).where(
                ResearchContentTrackerCandidateSample.run_id == run_id
            )
            if candidate_level is not None:
                stmt = stmt.where(
                    ResearchContentTrackerCandidateSample.candidate_level == candidate_level
                )
            stmt = stmt.order_by(
                ResearchContentTrackerCandidateSample.similarity_score.desc(),
                ResearchContentTrackerCandidateSample.engagement_total.desc(),
                ResearchContentTrackerCandidateSample.id.desc(),
            )
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [
                self._content_tracker_candidate_sample_to_dict(item)
                for item in result.scalars().all()
            ]

    async def upsert_keyword_heat_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchKeywordHeatSnapshot),
                ResearchKeywordHeatSnapshot,
            ).where(
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
                item = ResearchKeywordHeatSnapshot(
                    **item_payload,
                    **self._tenant_kwargs(ResearchKeywordHeatSnapshot),
                )
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
            stmt = self._apply_tenant(
                select(ResearchKeywordHeatSnapshot),
                ResearchKeywordHeatSnapshot,
            )
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
            stmt = self._apply_tenant(
                select(ResearchCompetitorCompositionSnapshot),
                ResearchCompetitorCompositionSnapshot,
            ).where(
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
                item = ResearchCompetitorCompositionSnapshot(
                    **item_payload,
                    **self._tenant_kwargs(ResearchCompetitorCompositionSnapshot),
                )
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
            stmt = self._apply_tenant(
                select(ResearchCompetitorCompositionSnapshot),
                ResearchCompetitorCompositionSnapshot,
            )
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
                **self._tenant_kwargs(ResearchOpportunityFeedback),
            )
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._opportunity_feedback_to_dict(item)

    async def list_opportunity_feedback(self, limit: int = 500) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = (
                self._apply_tenant(
                    select(ResearchOpportunityFeedback),
                    ResearchOpportunityFeedback,
                )
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
            item = ResearchBacktest(**item_payload, **self._tenant_kwargs(ResearchBacktest))
            session.add(item)
            await session.flush()
            await session.refresh(item)
            return self._backtest_to_dict(item)

    async def get_backtest(self, backtest_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchBacktest, backtest_id)
            if item is not None and not self._tenant_item_visible(item):
                return None
            return self._backtest_to_dict(item) if item else None

    async def list_backtests(self, limit: int | None = 50) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchBacktest), ResearchBacktest).order_by(
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
            if item is None or not self._tenant_item_visible(item):
                return None
            for source, target in mapping.items():
                if source in payload:
                    setattr(item, target, payload[source])
            await session.flush()
            await session.refresh(item)
            return self._backtest_to_dict(item)

    async def upsert_competitor_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchCompetitorAccount),
                ResearchCompetitorAccount,
            ).where(
                ResearchCompetitorAccount.platform == payload["platform"],
                ResearchCompetitorAccount.creator_id == payload["creator_id"],
            )
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()
            if item is None:
                item = ResearchCompetitorAccount(
                    **self._tenant_payload(ResearchCompetitorAccount, payload)
                )
                session.add(item)
            else:
                for key, value in payload.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
            await session.flush()
            await session.refresh(item)
            return self._competitor_account_to_dict(item)

    async def list_competitor_accounts(
        self,
        *,
        enabled_only: bool = False,
        monitor_type: str | None = "competitor",
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(
                select(ResearchCompetitorAccount),
                ResearchCompetitorAccount,
            )
            if enabled_only:
                stmt = stmt.where(ResearchCompetitorAccount.enabled.is_(True))
            if monitor_type:
                stmt = stmt.where(ResearchCompetitorAccount.monitor_type == monitor_type)
            result = await session.execute(stmt.order_by(ResearchCompetitorAccount.id.desc()))
            return [self._competitor_account_to_dict(item) for item in result.scalars().all()]

    async def get_competitor_account(self, competitor_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchCompetitorAccount, competitor_id)
            if item is not None and not self._tenant_item_visible(item):
                return None
            return self._competitor_account_to_dict(item) if item else None

    async def upsert_account_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchAccountProfile), ResearchAccountProfile).where(
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
                item = ResearchAccountProfile(
                    **item_payload,
                    **self._tenant_kwargs(ResearchAccountProfile),
                )
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
            if item is not None and not self._tenant_item_visible(item):
                return None
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
            stmt = self._apply_tenant(select(ResearchAccountProfile), ResearchAccountProfile)
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
            stmt = self._apply_tenant(select(ResearchAccountRole), ResearchAccountRole).where(
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
                item = ResearchAccountRole(
                    **item_payload,
                    **self._tenant_kwargs(ResearchAccountRole),
                )
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
            stmt = self._apply_tenant(select(ResearchAccountRole), ResearchAccountRole)
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
        if await self.get_account_profile(profile_id) is None:
            raise KeyError(profile_id)
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
            if competitor is None or not self._tenant_item_visible(competitor):
                return []
            result = await session.execute(
                self._apply_tenant(
                    select(ResearchCreatorDailySnapshot),
                    ResearchCreatorDailySnapshot,
                )
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
            if item is None or not self._tenant_item_visible(item):
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
            item = ResearchKeywordOpportunitySnapshot(
                **self._tenant_payload(ResearchKeywordOpportunitySnapshot, payload)
            )
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
            stmt = self._apply_tenant(
                select(ResearchKeywordOpportunitySnapshot),
                ResearchKeywordOpportunitySnapshot,
            )
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
            profile = ResearchAuthProfile(
                **profile_payload,
                **self._tenant_kwargs(ResearchAuthProfile),
            )
            session.add(profile)
            await session.flush()
            await session.refresh(profile)
            return self._auth_profile_to_dict(profile)

    async def list_auth_profiles(self, platform: str | None = None) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchAuthProfile), ResearchAuthProfile)
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
                self._apply_tenant(select(ResearchAuthProfile), ResearchAuthProfile)
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
            if profile is None or not self._tenant_item_visible(profile):
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
            stmt = self._apply_tenant(select(ResearchPost), ResearchPost).where(
                ResearchPost.job_id == job_id
            )
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
            stmt = self._apply_tenant(select(ResearchPost), ResearchPost)
            count_stmt = self._apply_tenant(select(func.count(ResearchPost.id)), ResearchPost)
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

    async def get_posts_by_ids(self, post_ids: list[int]) -> list[dict[str, Any]]:
        if not post_ids:
            return []
        async with get_session() as session:
            result = await session.execute(
                self._apply_tenant(select(ResearchPost), ResearchPost).where(ResearchPost.id.in_(post_ids))
            )
            posts = [self._post_to_dict(item) for item in result.scalars().all()]
            return await self._enrich_posts_from_platform_tables(session, posts)

    async def list_posts_by_platform_post_ids(
        self,
        *,
        platform: str,
        creator_id: str,
        post_ids: list[str],
    ) -> list[dict[str, Any]]:
        normalized = [str(post_id or "").strip() for post_id in post_ids if str(post_id or "").strip()]
        if not normalized:
            return []
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchPost), ResearchPost).where(
                ResearchPost.platform == platform,
                ResearchPost.platform_post_id.in_(normalized),
            )
            stmt = stmt.order_by(ResearchPost.publish_time.desc().nullslast())
            result = await session.execute(stmt)
            posts = [self._post_to_dict(item) for item in result.scalars().all()]
            posts = await self._enrich_posts_from_platform_tables(session, posts)
            return [
                self._finalize_creator_post(
                    post,
                    platform=platform,
                    creator_id=creator_id,
                )
                for post in posts
            ]

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
            stmt = self._apply_tenant(select(ResearchPost), ResearchPost)
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
            stmt = self._apply_tenant(select(ResearchPost), ResearchPost).where(
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
                return [
                    self._finalize_creator_post(
                        post,
                        platform=platform,
                        creator_id=creator_id,
                        matched_by_author_hash=True,
                    )
                    for post in posts
                ]
            trusted_posts = await self._list_posts_by_creator_from_platform_source(
                session,
                platform=platform,
                creator_id=creator_id,
                limit=limit,
            )
            if trusted_posts:
                return trusted_posts
            stmt = self._apply_tenant(select(ResearchPost), ResearchPost).where(ResearchPost.platform == platform)
            stmt = stmt.order_by(ResearchPost.publish_time.desc().nullslast())
            stmt = stmt.limit(max(limit or 500, 500))
            result = await session.execute(stmt)
            posts = await self._enrich_posts_from_platform_tables(
                session,
                [self._post_to_dict(item) for item in result.scalars().all()],
            )
            matched = [
                self._finalize_creator_post(
                    post,
                    platform=platform,
                    creator_id=creator_id,
                )
                for post in posts
                if self._post_matches_creator(
                    post,
                    platform=platform,
                    creator_id=creator_id,
                )
            ]
            return matched[:limit] if limit else matched

    async def list_xhs_notes_missing_token_by_creator(
        self,
        *,
        creator_id: str,
        days_back: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        start_ts: int | None = None
        if days_back:
            start_at = datetime.combine(date.today() - timedelta(days=days_back - 1), datetime.min.time())
            start_ts = int(start_at.replace(tzinfo=timezone.utc).timestamp())

        async with get_session() as session:
            stmt = select(XhsNote).where(
                XhsNote.user_id == creator_id,
                or_(XhsNote.xsec_token.is_(None), func.trim(XhsNote.xsec_token) == ""),
            )
            if start_ts is not None:
                stmt = stmt.where(or_(XhsNote.time.is_(None), XhsNote.time >= start_ts))
            stmt = stmt.order_by(XhsNote.time.desc().nullslast(), XhsNote.id.desc())
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "note_id": str(item.note_id or ""),
                    "type": str(item.type or ""),
                    "time": item.time,
                    "note_url": item.note_url,
                    "xsec_token": item.xsec_token,
                }
                for item in rows
                if item.note_id
            ]

    async def update_xhs_note_link_data(
        self,
        *,
        note_id: str,
        xsec_token: str,
        note_url: str,
    ) -> dict[str, int]:
        token = str(xsec_token or "").strip()
        url = str(note_url or "").strip()
        if not note_id or not token or not url:
            return {"xhs_notes": 0, "research_posts": 0}

        modified_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        async with get_session() as session:
            note_stmt = select(XhsNote).where(XhsNote.note_id == note_id)
            note_result = await session.execute(note_stmt)
            notes = note_result.scalars().all()
            for item in notes:
                item.xsec_token = token
                item.note_url = url
                item.last_modify_ts = modified_ts

            post_stmt = self._apply_tenant(
                select(ResearchPost),
                ResearchPost,
            ).where(
                ResearchPost.platform == "xhs",
                ResearchPost.platform_post_id == str(note_id),
            )
            post_result = await session.execute(post_stmt)
            posts = post_result.scalars().all()
            for item in posts:
                item.url = url
                engagement = dict(item.engagement_json or {})
                engagement["xsec_token"] = token
                item.engagement_json = _json_safe(engagement)

            await session.flush()
            return {"xhs_notes": len(notes), "research_posts": len(posts)}

    async def get_competitor_post_diagnostics(
        self,
        *,
        platform: str,
        creator_id: str,
        scan_limit: int = 2000,
        example_limit: int = 8,
    ) -> dict[str, Any]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchPost), ResearchPost).where(ResearchPost.platform == platform)
            stmt = stmt.order_by(ResearchPost.publish_time.desc().nullslast(), ResearchPost.id.desc())
            stmt = stmt.limit(max(100, min(scan_limit, 5000)))
            result = await session.execute(stmt)
            posts = await self._enrich_posts_from_platform_tables(
                session,
                [self._post_to_dict(item) for item in result.scalars().all()],
            )

            matched_posts: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for post in posts:
                if not self._post_matches_creator(
                    post,
                    platform=platform,
                    creator_id=creator_id,
                ):
                    continue
                post_id = str(post.get("platform_post_id") or self._fallback_post_id(post))
                if not post_id or post_id in seen_ids:
                    continue
                seen_ids.add(post_id)
                matched_posts.append(
                    self._finalize_creator_post(
                        dict(post),
                        platform=platform,
                        creator_id=creator_id,
                    )
                )

            stats = {
                "raw_matched_posts": len(matched_posts),
                "author_verified_posts": 0,
                "displayable_posts": 0,
                "eligible_posts": 0,
                "degraded_link_posts": 0,
                "invalid_url_posts": 0,
                "missing_token_posts": 0,
                "author_mismatch_posts": 0,
            }
            examples: list[dict[str, Any]] = []
            for post in matched_posts:
                reason = self._diagnostic_reason(
                    post,
                    platform=platform,
                    creator_id=creator_id,
                )
                if post.get("author_verified"):
                    stats["author_verified_posts"] += 1
                    stats["displayable_posts"] += 1
                else:
                    stats["author_mismatch_posts"] += 1
                if post.get("author_verified") and post.get("has_valid_url"):
                    stats["eligible_posts"] += 1
                elif post.get("author_verified"):
                    stats["degraded_link_posts"] += 1
                    stats["invalid_url_posts"] += 1
                    if reason == "missing_xsec_token":
                        stats["missing_token_posts"] += 1
                if reason != "ok" and len(examples) < example_limit:
                    examples.append(
                        {
                            "post_id": str(post.get("platform_post_id") or ""),
                            "title": post.get("title") or "",
                            "reason": reason,
                            "publish_time": _iso_datetime(post.get("publish_time"))
                            if isinstance(post.get("publish_time"), datetime)
                            else post.get("publish_time"),
                        }
                    )
            return {
                "platform": platform,
                "creator_id": creator_id,
                "stats": stats,
                "examples": examples,
            }

    def _diagnostic_reason(
        self,
        post: dict[str, Any],
        *,
        platform: str,
        creator_id: str,
    ) -> str:
        if post.get("author_verified") and post.get("has_valid_url"):
            return "ok"
        if not post.get("author_verified"):
            return "author_mismatch"
        engagement = post.get("engagement_json") or {}
        if platform == "xhs" and str(engagement.get("platform_author_id") or "") == creator_id:
            if not str(engagement.get("xsec_token") or "").strip():
                return "missing_xsec_token"
        return "invalid_platform_url"

    async def _list_posts_by_creator_from_platform_source(
        self,
        session,
        *,
        platform: str,
        creator_id: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        trusted_ids = await self._list_trusted_platform_post_ids(
            session,
            platform=platform,
            creator_id=creator_id,
            limit=max(limit or 500, 500),
        )
        if not trusted_ids:
            return []
        stmt = self._apply_tenant(select(ResearchPost), ResearchPost).where(
            ResearchPost.platform == platform,
            ResearchPost.platform_post_id.in_(trusted_ids),
        )
        stmt = stmt.order_by(ResearchPost.publish_time.desc().nullslast())
        if limit:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        posts = [self._post_to_dict(item) for item in result.scalars().all()]
        posts = await self._enrich_posts_from_platform_tables(session, posts)
        return [
            self._finalize_creator_post(
                post,
                platform=platform,
                creator_id=creator_id,
            )
            for post in posts
            if self._post_matches_creator(
                post,
                platform=platform,
                creator_id=creator_id,
                trusted_only=True,
            )
        ]

    async def _list_trusted_platform_post_ids(
        self,
        session,
        *,
        platform: str,
        creator_id: str,
        limit: int,
    ) -> list[str]:
        if platform == "xhs":
            result = await session.execute(
                text(
                    """
                    SELECT note_id
                    FROM xhs_note
                    WHERE user_id = :creator_id
                    ORDER BY time DESC, id DESC
                    LIMIT :limit
                    """
                ),
                {"creator_id": creator_id, "limit": limit},
            )
            return [str(row._mapping["note_id"]) for row in result if row._mapping["note_id"]]
        if platform == "dy":
            result = await session.execute(
                text(
                    """
                    SELECT CAST(aweme_id AS TEXT) AS aweme_id
                    FROM douyin_aweme
                    WHERE user_id = :creator_id OR sec_uid = :creator_id
                    ORDER BY create_time DESC, id DESC
                    LIMIT :limit
                    """
                ),
                {"creator_id": creator_id, "limit": limit},
            )
            return [str(row._mapping["aweme_id"]) for row in result if row._mapping["aweme_id"]]
        return []

    def _post_matches_creator(
        self,
        post: dict[str, Any],
        *,
        platform: str,
        creator_id: str,
        trusted_only: bool = False,
    ) -> bool:
        creator_value = str(creator_id or "").strip()
        if not creator_value:
            return False
        if str(post.get("author_hash") or "") == creator_value:
            return True
        engagement = post.get("engagement_json") or {}
        trusted_author_ids = {
            str(engagement.get("platform_author_id") or "").strip(),
            str(engagement.get("platform_sec_uid") or "").strip(),
        }
        trusted_author_ids.discard("")
        if trusted_author_ids:
            return creator_value in trusted_author_ids
        if trusted_only:
            return False
        loose_author_ids = {
            str(engagement.get("author_id") or "").strip(),
            str(engagement.get("user_id") or "").strip(),
            str(engagement.get("sec_uid") or "").strip(),
        }
        loose_author_ids.discard("")
        return creator_value in loose_author_ids

    def _finalize_creator_post(
        self,
        post: dict[str, Any],
        *,
        platform: str,
        creator_id: str,
        matched_by_author_hash: bool = False,
    ) -> dict[str, Any]:
        engagement = dict(post.get("engagement_json") or {})
        normalized_url = self._normalize_platform_post_url(platform, post.get("url"), engagement)
        post["url"] = normalized_url
        post["has_valid_url"] = bool(normalized_url)
        post["author_verified"] = matched_by_author_hash or self._post_matches_creator(
            post,
            platform=platform,
            creator_id=creator_id,
            trusted_only=True,
        )
        post["engagement_json"] = engagement
        return post

    def _normalize_platform_post_url(
        self,
        platform: str,
        source_url: Any,
        engagement: dict[str, Any],
    ) -> str:
        raw_url = str(source_url or "").strip()
        if not raw_url:
            return ""
        parsed = urlparse(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        if platform != "xhs":
            return raw_url
        if "xiaohongshu.com" not in parsed.netloc:
            return ""
        query = parse_qs(parsed.query, keep_blank_values=True)
        token = ""
        if query.get("xsec_token"):
            token = str(query["xsec_token"][0] or "").strip()
        if not token:
            token = str(engagement.get("xsec_token") or "").strip()
            if token:
                query["xsec_token"] = [token]
                query.setdefault("xsec_source", ["pc_search"])
                return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
            return ""
        return raw_url

    async def list_comments(self, job_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchComment), ResearchComment).where(
                ResearchComment.job_id == job_id
            )
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
            stmt = self._apply_tenant(select(ResearchComment), ResearchComment)
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
            stmt = self._apply_tenant(select(ResearchAuthor), ResearchAuthor).where(
                ResearchAuthor.job_id == job_id
            )
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
            stmt = self._apply_tenant(select(ResearchAuthor), ResearchAuthor)
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
            stmt = self._apply_tenant(select(RawRecord), RawRecord).where(RawRecord.job_id == job_id)
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
                **self._tenant_kwargs(ResearchAIInsightRun),
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
            if item is None or not self._tenant_item_visible(item):
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
                self._apply_tenant(select(ResearchAIInsightRun), ResearchAIInsightRun)
                .order_by(ResearchAIInsightRun.created_at.desc(), ResearchAIInsightRun.id.desc())
                .limit(limit)
            )
            return [self._ai_insight_run_to_dict(item) for item in result.scalars().all()]

    async def get_ai_insight_run(self, run_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            item = await session.get(ResearchAIInsightRun, run_id)
            if item is not None and not self._tenant_item_visible(item):
                return None
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
                    **self._tenant_kwargs(ResearchAIHotspot),
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
                    **self._tenant_kwargs(ResearchAITopicIdea),
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
            stmt = self._apply_tenant(select(ResearchAIHotspot), ResearchAIHotspot)
            if run_id is not None:
                stmt = stmt.where(ResearchAIHotspot.run_id == run_id)
            stmt = stmt.order_by(ResearchAIHotspot.created_at.desc(), ResearchAIHotspot.id.desc()).limit(limit)
            result = await session.execute(stmt)
            return [self._ai_hotspot_to_dict(item) for item in result.scalars().all()]

    async def list_ai_topic_ideas(
        self, *, run_id: int | None = None, status: str | None = "active", limit: int = 30
    ) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(ResearchAITopicIdea), ResearchAITopicIdea)
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
            job = AIAnalysisJob(**self._tenant_payload(AIAnalysisJob, payload))
            session.add(job)
            await session.flush()
            await session.refresh(job)
            return self._ai_analysis_job_to_dict(job)

    async def get_ai_analysis_job(self, analysis_job_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            job = await session.get(AIAnalysisJob, analysis_job_id)
            if job is None or not self._tenant_item_visible(job):
                return None
            return self._ai_analysis_job_to_dict(job)

    async def list_ai_analysis_jobs(self, research_job_id: int | None = None) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(AIAnalysisJob), AIAnalysisJob)
            if research_job_id is not None:
                stmt = stmt.where(AIAnalysisJob.research_job_id == research_job_id)
            result = await session.execute(stmt.order_by(AIAnalysisJob.created_at.desc()))
            return [self._ai_analysis_job_to_dict(item) for item in result.scalars().all()]

    async def update_ai_analysis_job_status(
        self, analysis_job_id: int, status: str
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            job = await session.get(AIAnalysisJob, analysis_job_id)
            if job is None or not self._tenant_item_visible(job):
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
                **self._tenant_kwargs(AIAnalysisResult),
            )
            session.add(result)
            await session.flush()
            await session.refresh(result)
            return self._ai_result_to_dict(result)

    async def list_ai_results(self, job_id: int | None = None) -> list[dict[str, Any]]:
        async with get_session() as session:
            stmt = self._apply_tenant(select(AIAnalysisResult), AIAnalysisResult)
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
                **self._tenant_kwargs(CrawlEvent),
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
        stmt = self._apply_tenant(select(func.count()).select_from(model), model).where(model.job_id == job_id)
        result = await session.execute(stmt)
        return int(result.scalar() or 0)

    async def _count_many(self, session, model, job_ids: list[int]) -> dict[int, int]:
        if not job_ids:
            return {}
        result = await session.execute(
            self._apply_tenant(select(model.job_id, func.count()), model)
            .where(model.job_id.in_(job_ids))
            .group_by(model.job_id)
        )
        return {int(job_id): int(count) for job_id, count in result.all()}

    async def _count_all(self, session, model) -> int:
        result = await session.execute(self._apply_tenant(select(func.count()).select_from(model), model))
        return int(result.scalar() or 0)

    async def _count_by_platform(self, session, model, job_id: int) -> dict[str, int]:
        result = await session.execute(
            self._apply_tenant(select(model.platform, func.count()), model)
            .where(model.job_id == job_id)
            .group_by(model.platform)
        )
        return {platform: int(count) for platform, count in result.all()}

    async def _count_by_platform_many(self, session, model, job_ids: list[int]) -> dict[int, dict[str, int]]:
        if not job_ids:
            return {}
        result = await session.execute(
            self._apply_tenant(select(model.job_id, model.platform, func.count()), model)
            .where(model.job_id.in_(job_ids))
            .group_by(model.job_id, model.platform)
        )
        counts: dict[int, dict[str, int]] = {}
        for job_id, platform, count in result.all():
            counts.setdefault(int(job_id), {})[str(platform)] = int(count)
        return counts

    async def _count_all_by_platform(self, session, model) -> dict[str, int]:
        result = await session.execute(
            self._apply_tenant(select(model.platform, func.count()), model).group_by(model.platform)
        )
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
                    SELECT note_id, user_id, nickname, note_url, xsec_token, liked_count, comment_count,
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
            engagement["platform_author_id"] = str(author_id)
            engagement.setdefault("author_id", str(author_id))
            engagement.setdefault("user_id", str(author_id))
        if sec_uid_key and source.get(sec_uid_key) is not None:
            engagement["platform_sec_uid"] = str(source[sec_uid_key])
            engagement.setdefault("sec_uid", str(source[sec_uid_key]))
        for key in (
            "nickname",
            "liked_count",
            "comment_count",
            "share_count",
            "collected_count",
            "source_keyword",
            "xsec_token",
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
            stmt = self._apply_tenant(select(RawRecord), RawRecord).where(
                RawRecord.job_id == job_id,
                RawRecord.platform == platform,
                RawRecord.source_type == source_type,
                RawRecord.payload_hash == payload_hash,
            )
            if source_id is None:
                stmt = stmt.where(RawRecord.source_id.is_(None))
            else:
                stmt = stmt.where(RawRecord.source_id == source_id)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                return {
                    "id": existing.id,
                    "payload_hash": existing.payload_hash,
                    "fetched_at": existing.fetched_at,
                }
            raw_record = RawRecord(
                job_id=job_id,
                platform=platform,
                source_type=source_type,
                source_id=source_id,
                source_url=source_url,
                payload_hash=payload_hash,
                payload_json=payload,
                parser_version=parser_version,
                **self._tenant_kwargs(RawRecord),
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
            stmt = self._apply_tenant(stmt, ResearchAuthor)
            result = await session.execute(stmt)
            author = result.scalar_one_or_none()
            if author is None:
                author = ResearchAuthor(**self._tenant_payload(ResearchAuthor, payload))
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
            stmt = self._apply_tenant(select(ResearchPost), ResearchPost).where(
                ResearchPost.job_id == payload["job_id"],
                ResearchPost.platform == payload["platform"],
                ResearchPost.platform_post_id == payload["platform_post_id"],
            )
            result = await session.execute(stmt)
            post = result.scalar_one_or_none()
            if post is None:
                post = ResearchPost(**self._tenant_payload(ResearchPost, payload))
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
            stmt = self._apply_tenant(select(ResearchComment), ResearchComment).where(
                ResearchComment.job_id == payload["job_id"],
                ResearchComment.platform == payload["platform"],
                ResearchComment.platform_comment_id == payload["platform_comment_id"],
            )
            result = await session.execute(stmt)
            comment = result.scalar_one_or_none()
            if comment is None:
                comment = ResearchComment(**self._tenant_payload(ResearchComment, payload))
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

    def _lead_to_dict(self, item: ResearchLead) -> dict[str, Any]:
        return {
            "id": item.id,
            "project_id": item.project_id,
            "external_lead_id": item.external_lead_id,
            "lead_status": item.lead_status,
            "lead_score": item.lead_score,
            "owner": item.owner,
            "name_masked": item.name_masked,
            "phone_hash": item.phone_hash,
            "wechat_hash": item.wechat_hash,
            "source_platform": item.source_platform,
            "source_keyword": item.source_keyword,
            "first_touch_at": item.first_touch_at,
            "last_touch_at": item.last_touch_at,
            "meta_json": item.meta_json or {},
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _lead_touchpoint_to_dict(self, item: ResearchLeadTouchpoint) -> dict[str, Any]:
        return {
            "id": item.id,
            "lead_id": item.lead_id,
            "project_id": item.project_id,
            "touch_type": item.touch_type,
            "platform": item.platform,
            "source_keyword": item.source_keyword,
            "creator_id": item.creator_id,
            "post_id": item.post_id,
            "raw_record_id": item.raw_record_id,
            "touch_time": item.touch_time,
            "session_key": item.session_key,
            "weight_hint": item.weight_hint,
            "evidence_json": item.evidence_json or {},
            "created_at": item.created_at,
        }

    def _lead_conversion_event_to_dict(self, item: ResearchLeadConversionEvent) -> dict[str, Any]:
        return {
            "id": item.id,
            "lead_id": item.lead_id,
            "project_id": item.project_id,
            "event_type": item.event_type,
            "event_value": item.event_value,
            "event_count": item.event_count,
            "event_time": item.event_time,
            "source_system": item.source_system,
            "operator": item.operator,
            "payload_json": item.payload_json or {},
            "created_at": item.created_at,
        }

    def _lead_attribution_result_to_dict(
        self,
        item: ResearchLeadAttributionResult,
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "project_id": item.project_id,
            "lead_id": item.lead_id,
            "conversion_event_id": item.conversion_event_id,
            "model": item.model,
            "dimension": item.dimension,
            "dimension_key": item.dimension_key,
            "credit": item.credit,
            "window_days": item.window_days,
            "meta_json": item.meta_json or {},
            "computed_at": item.computed_at,
        }

    def _lead_attribution_daily_snapshot_to_dict(
        self,
        item: ResearchLeadAttributionDailySnapshot,
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "project_id": item.project_id,
            "snapshot_date": item.snapshot_date,
            "model": item.model,
            "funnel": item.funnel_json or [],
            "platform_metrics": item.platform_metrics_json or [],
            "keyword_metrics": item.keyword_metrics_json or [],
            "content_metrics": item.content_metrics_json or [],
            "creator_metrics": item.creator_metrics_json or [],
            "summary": item.summary_json or {},
            "created_at": item.created_at,
        }

    def _lead_attribution_spend_to_dict(
        self,
        item: ResearchLeadAttributionSpend,
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "project_id": item.project_id,
            "spend_date": item.spend_date,
            "dimension": item.dimension,
            "dimension_key": item.dimension_key,
            "amount": item.amount,
            "source_system": item.source_system,
            "meta_json": item.meta_json or {},
            "created_at": item.created_at,
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

    def _creator_search_session_result_to_dict(
        self,
        item: ResearchCreatorSearchSessionResult,
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "session_id": item.session_id,
            "rank": item.rank,
            "platform": item.platform,
            "creator_id": item.creator_id,
            "source_type": item.source_type,
            "match_score": item.match_score,
            "snapshot": item.snapshot_json or {},
            "created_at": item.created_at,
        }

    def _creator_search_session_to_dict(
        self,
        item: ResearchCreatorSearchSession,
        *,
        results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        result_rows = results or []
        snapshots = []
        for row in result_rows:
            if isinstance(row, dict) and isinstance(row.get("snapshot"), dict):
                snapshots.append(row["snapshot"])
        return {
            "id": item.id,
            "raw_query": item.raw_query,
            "selected_vertical_id": item.selected_vertical_id,
            "search_payload": item.search_payload_json or {},
            "view_state": item.view_state_json or {},
            "diagnostics": item.diagnostics_json or {},
            "realtime": item.realtime_json or {},
            "progress": item.progress_json or {},
            "message": item.message,
            "result_summary": item.result_summary,
            "result_count": int(item.result_count or len(snapshots)),
            "saved": bool(item.saved),
            "saved_name": item.saved_name,
            "status": item.status,
            "results": snapshots,
            "result_rows": result_rows,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
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
            "daily_collection_limit_per_platform": int(
                item.daily_collection_limit_per_platform or 50
            ),
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
            "latest_analysis_run_id": item.latest_analysis_run_id,
            "latest_analysis_snapshot_id": item.latest_analysis_snapshot_id,
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

    def _collection_run_to_dict(self, item: ResearchCollectionRun) -> dict[str, Any]:
        return {
            "id": item.id,
            "run_type": item.run_type,
            "target_type": item.target_type,
            "target_id": item.target_id,
            "mode": item.mode,
            "trigger_source": item.trigger_source,
            "status": item.status,
            "phase": item.phase,
            "job_id": item.job_id,
            "analysis_run_id": item.analysis_run_id,
            "started_at": _iso_datetime(item.started_at),
            "completed_at": _iso_datetime(item.completed_at),
            "request_payload": item.request_payload_json or {},
            "summary": item.summary_json or {},
            "error": item.error_json or {},
            "created_at": _iso_datetime(item.created_at),
            "updated_at": _iso_datetime(item.updated_at),
        }

    def _content_tracker_analysis_run_to_dict(
        self, item: ResearchContentTrackerAnalysisRun
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "tracker_id": item.tracker_id,
            "status": item.status,
            "analysis_version": item.analysis_version,
            "window_days": item.window_days,
            "started_at": item.started_at,
            "completed_at": item.completed_at,
            "sample_count": item.sample_count,
            "candidate_count": item.candidate_count,
            "sample_quality_score": item.sample_quality_score,
            "trend_strength_score": item.trend_strength_score,
            "noise_rate": item.noise_rate,
            "decision_confidence": item.decision_confidence,
            "input_summary": item.input_summary_json or {},
            "summary": item.summary_json or {},
            "error_message": item.error_message,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _content_tracker_analysis_snapshot_to_dict(
        self, item: ResearchContentTrackerAnalysisSnapshot
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "tracker_id": item.tracker_id,
            "run_id": item.run_id,
            "snapshot_date": item.snapshot_date,
            "status": item.status,
            "overview": item.overview_json or {},
            "trends": item.trends_json or {},
            "keywords": item.keywords_json or {},
            "patterns": item.patterns_json or {},
            "creators": item.creators_json or {},
            "samples": item.samples_json or {},
            "risks": item.risks_json or {},
            "decisions": item.decisions_json or {},
            "meta": item.meta_json or {},
            "created_at": item.created_at,
        }

    def _content_tracker_candidate_sample_to_dict(
        self, item: ResearchContentTrackerCandidateSample
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "tracker_id": item.tracker_id,
            "run_id": item.run_id,
            "platform": item.platform,
            "platform_post_id": item.platform_post_id,
            "author_id": item.author_id,
            "author_name": self._author_name_from_engagement(item.engagement_json or {}),
            "title": item.title,
            "url": item.url,
            "publish_time": item.publish_time,
            "candidate_level": item.candidate_level,
            "similarity_score": item.similarity_score,
            "engagement_total": item.engagement_total,
            "is_hot": bool(item.is_hot),
            "matched_keywords": item.matched_keywords_json or [],
            "fingerprint": item.fingerprint_json or {},
            "engagement": item.engagement_json or {},
            "evidence": item.evidence_json or {},
            "created_at": item.created_at,
        }

    @staticmethod
    def _author_name_from_engagement(engagement: dict[str, Any]) -> str | None:
        for key in ("nickname", "author_name", "user_name", "display_name"):
            value = str(engagement.get(key) or "").strip()
            if value:
                return value
        user = engagement.get("user")
        if isinstance(user, dict):
            value = str(user.get("nickname") or user.get("name") or "").strip()
            if value:
                return value
        return None

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
            "monitor_type": item.monitor_type or "competitor",
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
