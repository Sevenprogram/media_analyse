from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


POST_THRESHOLD = 50
COMMENT_THRESHOLD = 20


def build_growth_project_summaries(
    jobs: list[dict[str, Any]],
    stats_by_job_id: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    stats_by_job_id = stats_by_job_id or {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for job in jobs:
        grouped[project_key_for_job(job)].append(job)

    projects = [
        _build_project_summary(project_id, project_jobs, stats_by_job_id)
        for project_id, project_jobs in grouped.items()
    ]
    return sorted(
        projects,
        key=lambda item: (item.get("last_collected_at") or "", item["name"]),
        reverse=True,
    )


def build_growth_project_detail(
    project_id: str,
    jobs: list[dict[str, Any]],
    stats_by_job_id: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    stats_by_job_id = stats_by_job_id or {}
    project_jobs = [job for job in jobs if project_key_for_job(job) == project_id]
    if not project_jobs:
        return None

    project = _build_project_summary(project_id, project_jobs, stats_by_job_id)
    return {
        "project": project,
        "status_bar": {
            "recommended_action": project["recommended_action"]["label"],
            "sample_status": project["sample_status"]["label"],
            "opportunity_score": project["opportunity_score"],
        },
        "overview": {
            "current_judgment": _current_judgment(project),
            "recommended_actions": _recommended_actions(project),
            "sample_status": project["sample_status"],
            "collection_health": project["metrics"],
        },
        "ai_insights": {
            "summary": "AI insight has not been generated for this aggregated project.",
            "missing_data": _missing_data(project),
        },
        "sample_data": {
            "posts": project["metrics"]["posts"],
            "comments": project["metrics"]["comments"],
            "creators": project["metrics"]["creators"],
            "raw_records": project["metrics"]["raw_records"],
        },
        "keywords": _keyword_assets(project_jobs),
        "collection_records": [
            _collection_record(job, stats_by_job_id) for job in project_jobs
        ],
        "settings": {
            "primary_goal": project["primary_goal"],
            "platforms": project["platforms"],
            "refresh_cadence": "off",
        },
    }


def project_key_for_job(job: dict[str, Any]) -> str:
    explicit = job.get("project_key") or job.get("growth_project_id")
    if explicit:
        return _slug(str(explicit))

    topic = str(job.get("topic") or "").strip()
    if topic:
        return _slug(topic)

    name = str(job.get("name") or f"job-{job.get('id', 'unclassified')}")
    return _slug(name)


def _build_project_summary(
    project_id: str,
    jobs: list[dict[str, Any]],
    stats_by_job_id: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    metrics = _metrics(jobs, stats_by_job_id)
    sample_status = _sample_status(metrics)
    return {
        "id": project_id,
        "name": _title_from_project_id(project_id),
        "primary_goal": _primary_goal(project_id, jobs),
        "platforms": sorted(
            {
                platform
                for job in jobs
                for platform in (job.get("platforms") or [])
            }
        ),
        "status": sample_status["project_state"],
        "sample_status": sample_status,
        "recommended_action": _recommended_action(sample_status["kind"]),
        "opportunity_score": _opportunity_score(sample_status["kind"], metrics),
        "last_collected_at": _last_collected_at(jobs),
        "metrics": metrics,
        "job_ids": [job["id"] for job in jobs if "id" in job],
    }


def _metrics(
    jobs: list[dict[str, Any]],
    stats_by_job_id: dict[int, dict[str, Any]],
) -> dict[str, int]:
    totals = {
        "jobs": len(jobs),
        "posts": 0,
        "comments": 0,
        "raw_records": 0,
        "creators": 0,
        "failed_jobs": 0,
        "running_jobs": 0,
        "pending_jobs": 0,
    }

    for job in jobs:
        status = str(job.get("status") or "")
        if status in {"failed", "error"}:
            totals["failed_jobs"] += 1
        if status == "running":
            totals["running_jobs"] += 1
        if status in {"pending", "queued"}:
            totals["pending_jobs"] += 1

        stats = _stats_for_job(job, stats_by_job_id)
        totals["posts"] += _int(stats.get("posts"))
        totals["comments"] += _int(stats.get("comments"))
        totals["raw_records"] += _int(stats.get("raw_records"))
        totals["creators"] += _int(stats.get("authors") or stats.get("creators"))

    return totals


def _sample_status(metrics: dict[str, int]) -> dict[str, str]:
    if metrics["failed_jobs"]:
        return {
            "kind": "collection_issue",
            "label": "Collection issue needs attention",
            "project_state": "collection_issue",
        }
    if metrics["running_jobs"] or metrics["pending_jobs"]:
        return {
            "kind": "collecting",
            "label": "Collection is still running",
            "project_state": "collecting",
        }
    if metrics["posts"] < POST_THRESHOLD:
        return {
            "kind": "sample_insufficient",
            "label": "Post sample is insufficient",
            "project_state": "sample_insufficient",
        }
    if metrics["comments"] < COMMENT_THRESHOLD:
        return {
            "kind": "comment_insufficient",
            "label": "Sample is ready for preliminary analysis",
            "project_state": "preliminarily_analyzable",
        }
    return {
        "kind": "ready_for_insight",
        "label": "Sample is ready for preliminary analysis",
        "project_state": "deeply_analyzable",
    }


def _recommended_action(kind: str) -> dict[str, str]:
    actions = {
        "collection_issue": {"kind": "view_failed_jobs", "label": "View failed jobs"},
        "collecting": {"kind": "wait_for_collection", "label": "Wait for collection"},
        "sample_insufficient": {"kind": "backfill_posts", "label": "Backfill posts"},
        "comment_insufficient": {
            "kind": "backfill_comments",
            "label": "Backfill comments",
        },
        "ready_for_insight": {"kind": "generate_insight", "label": "Generate insight"},
    }
    return actions[kind]


def _opportunity_score(kind: str, metrics: dict[str, int]) -> int | None:
    if kind in {"collection_issue", "collecting", "sample_insufficient"}:
        return None

    base = 40 + metrics["posts"] // 5 + metrics["comments"] // 10
    return max(0, min(100, min(80, base)))


def _primary_goal(project_id: str, jobs: list[dict[str, Any]]) -> str:
    text = " ".join([project_id, *[str(job.get("name") or "") for job in jobs]]).lower()
    key_text = project_id.lower()
    if "creator" in text or "达人" in text:
        return "creator_discovery"
    if "competitor" in text or "竞品" in text:
        return "competitor_monitoring"
    if "expansion" in key_text or "keyword" in key_text or "关键词" in key_text:
        return "keyword_expansion"
    return "topic_discovery"


def _last_collected_at(jobs: list[dict[str, Any]]) -> str | None:
    values = [
        str(job.get("last_scheduled_at") or job.get("updated_at") or job.get("created_at") or "")
        for job in jobs
    ]
    values = [value for value in values if value]
    return max(values) if values else None


def _keyword_assets(jobs: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    assets: list[dict[str, str]] = []
    for job in jobs:
        for keyword in job.get("keywords") or []:
            item = str(keyword).strip()
            if item and item not in seen:
                seen.add(item)
                assets.append(
                    {"keyword": item, "type": "core", "source": "research_job"}
                )
    return assets


def _collection_record(
    job: dict[str, Any],
    stats_by_job_id: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    stats = _stats_for_job(job, stats_by_job_id)
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "platforms": job.get("platforms") or [],
        "collection_mode": job.get("collection_mode") or "search",
        "keywords": job.get("keywords") or [],
        "status": job.get("status") or "unknown",
        "posts": _int(stats.get("posts")),
        "comments": _int(stats.get("comments")),
        "raw_records": _int(stats.get("raw_records")),
        "updated_at": job.get("updated_at"),
    }


def _current_judgment(project: dict[str, Any]) -> str:
    kind = project["sample_status"]["kind"]
    if kind == "collection_issue":
        return "Collection has issues. Review failed jobs before making a business decision."
    if kind == "comment_insufficient":
        return "Post samples are usable, but comments are insufficient for strong topic judgment."
    if kind == "ready_for_insight":
        return "Samples are ready for insight generation."
    if kind == "sample_insufficient":
        return "The project needs more post samples before analysis."
    return "Collection is in progress."


def _recommended_actions(project: dict[str, Any]) -> list[dict[str, str]]:
    primary = project["recommended_action"]
    if primary["kind"] == "backfill_comments":
        return [primary, {"kind": "generate_insight", "label": "Generate preliminary insight"}]
    return [primary]


def _missing_data(project: dict[str, Any]) -> list[str]:
    missing = []
    if project["metrics"]["posts"] < POST_THRESHOLD:
        missing.append("post samples")
    if project["metrics"]["comments"] < COMMENT_THRESHOLD:
        missing.append("comment samples")
    return missing


def _stats_for_job(
    job: dict[str, Any],
    stats_by_job_id: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    if job.get("id") is None:
        return {}
    return stats_by_job_id.get(_int(job["id"]), {})


def _title_from_project_id(project_id: str) -> str:
    return project_id.replace("-", " ").replace("_", " ").title()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", value.strip().lower())
    return slug.strip("_") or "unclassified_collection_records"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
