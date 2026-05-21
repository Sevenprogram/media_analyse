from __future__ import annotations

from datetime import date, timedelta
from typing import Any


class MonitorPoolService:
    def __init__(self, repository, execution_callback=None):
        self.repository = repository
        self.execution_callback = execution_callback

    async def add_creators(
        self,
        *,
        pool_id: int,
        creators: list[dict[str, Any]],
        crawl_now: bool = False,
    ) -> dict[str, Any]:
        pool = await self.repository.get_monitor_pool(pool_id)
        if pool is None:
            raise ValueError(f"Monitor pool not found: {pool_id}")
        normalized = [_normalize_creator(item) for item in creators]
        if hasattr(self.repository, "add_account_profile_to_monitor_pool"):
            for item in normalized:
                profile_id = item.get("account_profile_id")
                if profile_id:
                    await self.repository.add_account_profile_to_monitor_pool(
                        pool_id,
                        int(profile_id),
                        crawl_now=crawl_now,
                    )
        added = await self.repository.add_monitor_pool_creators(pool_id, normalized)
        members = await self.repository.list_monitor_pool_creators(
            pool_id,
            enabled_only=True,
        )
        job = await self._ensure_creator_job(pool, members)
        executed = None
        if crawl_now and self.execution_callback is not None:
            executed = await self.execution_callback(job["id"])
        return {"pool": pool, "added": added, "job": job, "executed": executed}

    async def sync_pool_job(self, pool_id: int) -> dict[str, Any]:
        pool = await self.repository.get_monitor_pool(pool_id)
        if pool is None:
            raise ValueError(f"Monitor pool not found: {pool_id}")
        job = None
        if pool.get("research_job_id"):
            members = await self.repository.list_monitor_pool_creators(
                pool_id,
                enabled_only=True,
            )
            job = await self._ensure_creator_job(pool, members)
        return {"pool": pool, "job": job}

    async def _ensure_creator_job(
        self,
        pool: dict[str, Any],
        members: list[dict[str, Any]],
    ) -> dict[str, Any]:
        enabled_members = [item for item in members if item.get("enabled", True)]
        creator_ids = sorted({item["creator_id"] for item in enabled_members})
        platforms = sorted({item["platform"] for item in enabled_members})
        payload = {
            "name": f"{pool['name']} - creator monitor",
            "topic": pool["name"],
            "platforms": platforms,
            "collection_mode": "creator",
            "keywords": [],
            "target_ids": [],
            "creator_ids": creator_ids,
            "start_date": date.today(),
            "end_date": date.today() + timedelta(days=365),
            "status": "pending",
            "comment_policy": pool.get("comment_policy")
            or pool.get("comment_policy_json")
            or {"enable_comments": True, "enable_sub_comments": False},
            "raw_record_mode": "minimal",
            "anonymize_authors": True,
            "schedule_enabled": True,
            "schedule_interval_minutes": int(pool.get("schedule_interval_minutes") or 720),
        }
        if pool.get("research_job_id"):
            job = await self.repository.update_job(pool["research_job_id"], payload)
        else:
            create_job = getattr(self.repository, "create_research_job", None)
            if create_job is None:
                create_job = getattr(self.repository, "create_job")
            job = await create_job(payload)
            await self.repository.update_monitor_pool(
                pool["id"],
                {"research_job_id": job["id"]},
            )
        return job


def automation_select_candidates(
    candidates: list[dict[str, Any]], rules: dict[str, Any]
) -> list[dict[str, Any]]:
    limit = int(rules.get("top_n") or 10)
    min_score = float(rules.get("min_match_score") or 80)
    min_recent_posts = int(rules.get("min_recent_post_count_30d") or 3)
    exclude_monitored = bool(rules.get("exclude_monitored", True))
    filtered = [
        item
        for item in candidates
        if float(item.get("match_score") or 0) >= min_score
        and int(item.get("recent_post_count_30d") or 0) >= min_recent_posts
        and not (exclude_monitored and item.get("monitored"))
    ]
    return sorted(filtered, key=lambda item: item["match_score"], reverse=True)[:limit]


def _normalize_creator(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": item["platform"],
        "creator_id": item["creator_id"],
        "display_name": item.get("display_name"),
        "match_score": item.get("match_score"),
        "source": item.get("source") or "manual",
        "enabled": item.get("enabled", True),
        "notes": item.get("notes"),
        "account_profile_id": item.get("account_profile_id"),
    }
