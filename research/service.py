import re
from datetime import datetime
from typing import Any, Protocol

from research.enums import JOB_PENDING
from research.growth_projects import (
    build_growth_project_detail,
    build_growth_project_summaries,
    project_key_for_job,
)
from research.schemas import (
    ResearchJobCreate,
    ResearchJobUpdate,
    validate_collection_inputs,
)


class JobRepository(Protocol):
    async def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def list_jobs(self) -> list[dict[str, Any]]:
        ...

    async def list_jobs_for_project(self, project_keys: list[str]) -> list[dict[str, Any]]:
        ...

    async def get_job(self, job_id: int) -> dict[str, Any] | None:
        ...

    async def get_job_stats(self, job_id: int) -> dict[str, Any]:
        ...

    async def get_job_stats_many(self, job_ids: list[int]) -> dict[int, dict[str, Any]]:
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

    async def list_growth_projects(self) -> list[dict[str, Any]]:
        jobs = await self.repository.list_jobs()
        stats = await self._stats_by_job_id(jobs)
        summaries = build_growth_project_summaries(jobs, stats)
        return await self._merge_growth_project_records(summaries, jobs, stats)

    async def get_growth_project(self, project_id: str) -> dict[str, Any] | None:
        records = await self._growth_project_records()
        record = await self._resolve_growth_project_record(project_id)
        if record is None:
            record = records.get(project_id)
        lookup_keys = [project_id]
        if record is not None:
            lookup_keys.extend(
                [
                    str(record.get("id") or ""),
                    _slug(record["name"]),
                ]
            )
        lookup_keys = list(dict.fromkeys([key for key in lookup_keys if key]))
        project_jobs = await self._project_jobs(lookup_keys)
        if record and project_jobs:
            project_jobs = _scoped_jobs_for_record(record, project_jobs)
        if not project_jobs and record is None:
            jobs = await self.repository.list_jobs()
            key_set = {_slug(key) for key in lookup_keys}
            project_jobs = [job for job in jobs if _slug(project_key_for_job(job)) in key_set]
        stats = await self._stats_by_job_id(project_jobs)
        detail = build_growth_project_detail(project_id, project_jobs, stats)
        if detail is not None:
            record = record or records.get(_slug(detail["project"]["name"]))
        if detail is None and record:
            if record.get("archived"):
                return None
            detail = _record_only_growth_project_detail(project_id, record)
        if detail is None:
            return None
        if record:
            if record.get("archived"):
                return None
            detail["project"] = _apply_growth_project_record(detail["project"], record)
            detail["settings"]["primary_goal"] = detail["project"]["primary_goal"]
            detail["settings"]["platforms"] = detail["project"]["platforms"]
            detail["settings"]["scene_pack_id"] = record.get("scene_pack_id")
            detail["settings"]["comment_collection_enabled"] = record.get("comment_collection_enabled", True)
            detail["settings"]["refresh_cadence"] = record.get("refresh_cadence") or "off"
            detail["settings"]["custom_interval_value"] = record.get("custom_interval_value")
            detail["settings"]["custom_interval_unit"] = record.get("custom_interval_unit")
            detail["settings"]["refresh_time_utc8"] = record.get("refresh_time_utc8")
            detail["settings"]["daily_collection_limit_per_platform"] = int(
                record.get("daily_collection_limit_per_platform") or 50
            )
            keywords = await self._growth_project_keywords(record["id"])
            if keywords:
                detail["keywords"] = [
                    {
                        "keyword": item["keyword"],
                        "type": item["keyword_type"],
                        "source": item["source"],
                        "status": item.get("status"),
                    }
                    for item in keywords
                ]
        return detail

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
        validate_collection_inputs(
            collection_mode=payload.get(
                "collection_mode", existing.get("collection_mode", "search")
            ),
            keywords=payload.get("keywords", existing.get("keywords") or []),
            target_ids=payload.get("target_ids", existing.get("target_ids") or []),
            creator_ids=payload.get("creator_ids", existing.get("creator_ids") or []),
        )
        return await self.repository.update_job(job_id, payload)

    async def _stats_by_job_id(self, jobs: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        stats: dict[int, dict[str, Any]] = {}
        job_ids = [int(job["id"]) for job in jobs if job.get("id") is not None]
        if not job_ids:
            return stats
        batch_getter = getattr(self.repository, "get_job_stats_many", None)
        if batch_getter is not None:
            return await batch_getter(job_ids)
        getter = getattr(self.repository, "get_job_stats", None)
        if getter is None:
            return stats
        for job_id in job_ids:
            stats[job_id] = await getter(job_id)
        return stats

    async def _growth_project_records(self) -> dict[str, dict[str, Any]]:
        lister = getattr(self.repository, "list_growth_project_records", None)
        if lister is None:
            return {}
        records = await lister(include_archived=True)
        return {_slug(record["name"]): record for record in records}

    async def _growth_project_keywords(self, project_record_id: int) -> list[dict[str, Any]]:
        lister = getattr(self.repository, "list_growth_project_keywords", None)
        if lister is None:
            return []
        return await lister(project_record_id)

    async def _resolve_growth_project_record(self, project_id: str) -> dict[str, Any] | None:
        resolver = getattr(self.repository, "resolve_growth_project_record", None)
        if resolver is not None:
            return await resolver(project_id, include_archived=True)
        if project_id.isdigit():
            getter = getattr(self.repository, "get_growth_project_record", None)
            if getter is not None:
                return await getter(int(project_id))
        records = await self._growth_project_records()
        return records.get(project_id)

    async def _project_jobs(self, project_keys: list[str]) -> list[dict[str, Any]]:
        lister = getattr(self.repository, "list_jobs_for_project", None)
        if lister is None:
            jobs = await self.repository.list_jobs()
            key_set = set(project_keys)
            return [job for job in jobs if project_key_for_job(job) in key_set]
        project_jobs = await lister(project_keys)
        if project_jobs:
            return project_jobs
        jobs = await self.repository.list_jobs()
        key_set = set(project_keys)
        return [job for job in jobs if project_key_for_job(job) in key_set]

    async def _merge_growth_project_records(
        self,
        summaries: list[dict[str, Any]],
        jobs: list[dict[str, Any]],
        stats_by_job_id: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        records = await self._growth_project_records()
        if not records:
            return summaries
        jobs_by_project: dict[str, list[dict[str, Any]]] = {}
        for job in jobs:
            jobs_by_project.setdefault(project_key_for_job(job), []).append(job)
        merged = []
        seen: set[str] = set()
        for summary in summaries:
            record = records.get(summary["id"]) or records.get(_slug(summary["name"]))
            if record and record.get("archived"):
                continue
            scoped_summary = summary
            if record:
                scoped_jobs = _scoped_jobs_for_record(record, jobs_by_project.get(summary["id"], []))
                scoped_detail = build_growth_project_detail(summary["id"], scoped_jobs, stats_by_job_id)
                if scoped_detail is not None:
                    scoped_summary = scoped_detail["project"]
            merged.append(_apply_growth_project_record(scoped_summary, record) if record else scoped_summary)
            seen.add(summary["id"])
        for project_id, record in records.items():
            if project_id in seen or record.get("archived"):
                continue
            merged.append(_record_only_growth_project_summary(project_id, record))
        return merged


def _scoped_jobs_for_record(
    record: dict[str, Any],
    jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not jobs:
        return jobs
    explicit_key = _growth_project_job_key(int(record["id"]))
    explicit_jobs = [
        job
        for job in jobs
        if _job_growth_project_key(job) == explicit_key
    ]
    if explicit_jobs:
        return explicit_jobs
    created_at = _to_datetime(record.get("created_at"))
    if created_at is None:
        return jobs
    recent_jobs = [
        job
        for job in jobs
        if (job_created_at := _to_datetime(job.get("created_at"))) is not None
        and job_created_at >= created_at
    ]
    return recent_jobs or jobs


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def _job_growth_project_key(job: dict[str, Any]) -> str | None:
    comment_policy = job.get("comment_policy") or {}
    value = comment_policy.get("growth_project_key")
    if not value:
        return None
    return str(value).strip() or None


def _growth_project_job_key(project_record_id: int) -> str:
    return f"growth_project_record_{project_record_id}"


def _apply_growth_project_record(
    summary: dict[str, Any],
    record: dict[str, Any] | None,
) -> dict[str, Any]:
    if not record:
        return summary
    next_summary = dict(summary)
    next_summary["project_record_id"] = record["id"]
    next_summary["name"] = record["name"]
    next_summary["primary_goal"] = record["primary_goal"]
    next_summary["platforms"] = record["platforms"] or next_summary["platforms"]
    next_summary["opportunity_score"] = record.get("opportunity_score") or next_summary.get("opportunity_score")
    next_summary["last_collected_at"] = record.get("last_collected_at") or next_summary.get("last_collected_at")
    return next_summary


def _record_only_growth_project_summary(project_id: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": project_id,
        "project_record_id": record["id"],
        "name": record["name"],
        "primary_goal": record["primary_goal"],
        "platforms": record.get("platforms") or [],
        "status": record.get("sample_status") or "sample_insufficient",
        "sample_status": {
            "kind": record.get("sample_status") or "sample_insufficient",
            "label": "Post sample is insufficient",
            "project_state": "sample_insufficient",
        },
        "recommended_action": {
            "kind": record.get("recommended_action") or "start_collection",
            "label": "Start collection",
        },
        "opportunity_score": record.get("opportunity_score"),
        "last_collected_at": record.get("last_collected_at"),
        "metrics": {
            "jobs": 0,
            "posts": 0,
            "comments": 0,
            "raw_records": 0,
            "creators": 0,
            "failed_jobs": 0,
            "running_jobs": 0,
            "pending_jobs": 0,
        },
        "job_ids": [],
    }


def _record_only_growth_project_detail(project_id: str, record: dict[str, Any]) -> dict[str, Any]:
    project = _record_only_growth_project_summary(project_id, record)
    return {
        "project": project,
        "status_bar": {
            "recommended_action": project["recommended_action"]["label"],
            "sample_status": project["sample_status"]["label"],
            "opportunity_score": project["opportunity_score"],
        },
        "overview": {
            "current_judgment": "The project is ready for collection setup.",
            "recommended_actions": [project["recommended_action"]],
            "sample_status": project["sample_status"],
            "collection_health": project["metrics"],
        },
        "ai_insights": {
            "summary": "AI insight has not been generated for this project.",
            "missing_data": ["post samples", "comment samples"],
        },
        "sample_data": {
            "posts": 0,
            "comments": 0,
            "creators": 0,
            "raw_records": 0,
        },
        "keywords": [],
        "collection_records": [],
        "settings": {
            "primary_goal": project["primary_goal"],
            "platforms": project["platforms"],
            "scene_pack_id": record.get("scene_pack_id"),
            "comment_collection_enabled": record.get("comment_collection_enabled", True),
            "refresh_cadence": record.get("refresh_cadence") or "off",
            "custom_interval_value": record.get("custom_interval_value"),
            "custom_interval_unit": record.get("custom_interval_unit"),
            "refresh_time_utc8": record.get("refresh_time_utc8"),
            "daily_collection_limit_per_platform": int(
                record.get("daily_collection_limit_per_platform") or 50
            ),
        },
    }


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", value.strip().lower())
    return slug.strip("_") or "unclassified_collection_records"
