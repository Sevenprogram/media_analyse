import hashlib
from typing import Any

from research.enums import (
    COLLECTION_CREATOR,
    COLLECTION_DETAIL,
    COLLECTION_SEARCH,
    CRAWL_UNIT_PENDING,
)


def build_crawl_units_for_job(
    job: dict[str, Any],
    *,
    max_attempts: int = 3,
    run_key: str = "default",
) -> list[dict[str, Any]]:
    collection_mode = job.get("collection_mode") or COLLECTION_SEARCH
    values = _collection_values(job, collection_mode)
    daily_limit = _daily_collection_limit(job.get("comment_policy") or {})
    if daily_limit is not None:
        values = values[:daily_limit]
    units: list[dict[str, Any]] = []

    for platform in _clean_values(job.get("platforms") or []):
        for value in values:
            unit = {
                "job_id": job["id"],
                "run_key": run_key,
                "platform": platform,
                "collection_mode": collection_mode,
                "keyword": value if collection_mode == COLLECTION_SEARCH else None,
                "target_id": value if collection_mode == COLLECTION_DETAIL else None,
                "creator_id": value if collection_mode == COLLECTION_CREATOR else None,
                "status": CRAWL_UNIT_PENDING,
                "priority": 100,
                "attempt_count": 0,
                "max_attempts": max_attempts,
            }
            unit["unit_key"] = build_crawl_unit_key(unit)
            units.append(unit)
    return units


def build_crawl_unit_key(unit: dict[str, Any]) -> str:
    parts = [
        str(unit.get("run_key") or "default"),
        str(unit.get("platform") or ""),
        str(unit.get("collection_mode") or ""),
        str(unit.get("keyword") or ""),
        str(unit.get("target_id") or ""),
        str(unit.get("creator_id") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def unit_filter_kwargs(unit: dict[str, Any]) -> dict[str, list[str] | None]:
    collection_mode = unit.get("collection_mode")
    return {
        "keywords": [unit["keyword"]]
        if collection_mode == COLLECTION_SEARCH and unit.get("keyword")
        else None,
        "target_ids": [unit["target_id"]]
        if collection_mode == COLLECTION_DETAIL and unit.get("target_id")
        else None,
        "creator_ids": [unit["creator_id"]]
        if collection_mode == COLLECTION_CREATOR and unit.get("creator_id")
        else None,
    }


def _collection_values(job: dict[str, Any], collection_mode: str) -> list[str]:
    if collection_mode == COLLECTION_SEARCH:
        return _clean_values(job.get("keywords") or [])
    if collection_mode == COLLECTION_DETAIL:
        return _clean_values(job.get("target_ids") or [])
    if collection_mode == COLLECTION_CREATOR:
        return _clean_values(job.get("creator_ids") or [])
    raise ValueError(f"Unsupported research collection mode: {collection_mode}")


def _clean_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _daily_collection_limit(comment_policy: dict[str, Any]) -> int | None:
    value = comment_policy.get("daily_collection_limit_per_platform")
    if value is None:
        return None
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, limit)
