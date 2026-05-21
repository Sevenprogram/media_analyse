from __future__ import annotations

from typing import Any

from research.candidate_tiering import tier_creator_candidate
from research.monitor_pools import MonitorPoolService


DEFAULT_DAILY_AUTO_POOL_CAP = 20


async def auto_pool_a_tier_candidates(
    repository,
    *,
    pool_id: int,
    candidates: list[dict[str, Any]] | None = None,
    daily_cap: int = DEFAULT_DAILY_AUTO_POOL_CAP,
    crawl_now: bool = False,
) -> dict[str, Any]:
    pool = await repository.get_monitor_pool(pool_id)
    if pool is None:
        raise ValueError(f"Monitor pool not found: {pool_id}")
    if candidates is None:
        candidates = await repository.list_creator_candidates()
    existing = {
        (item["platform"], item["creator_id"])
        for item in await repository.list_monitor_pool_creators(pool_id, enabled_only=True)
    }
    selected = []
    skipped = []
    for candidate in candidates:
        tiering = (candidate.get("evidence") or candidate.get("evidence_json") or {}).get("tiering")
        if not tiering:
            tiering = tier_creator_candidate(candidate)
        key = (candidate.get("platform"), candidate.get("creator_id"))
        if key in existing:
            skipped.append({**candidate, "skip_reason": "already_monitored"})
            continue
        if not tiering.get("auto_pool_eligible"):
            skipped.append({**candidate, "skip_reason": "not_a_tier"})
            continue
        if len(selected) >= daily_cap:
            skipped.append({**candidate, "skip_reason": "daily_cap_reached"})
            continue
        selected.append(
            {
                "platform": candidate["platform"],
                "creator_id": candidate["creator_id"],
                "display_name": candidate.get("display_name"),
                "match_score": candidate.get("match_score") or tiering.get("tier_score"),
                "source": "auto_a_tier",
                "notes": tiering.get("tier_reason"),
            }
        )
    added = []
    job = None
    executed = None
    if selected:
        result = await MonitorPoolService(repository).add_creators(
            pool_id=pool_id,
            creators=selected,
            crawl_now=crawl_now,
        )
        added = result["added"]
        job = result["job"]
        executed = result.get("executed")
    return {
        "pool": pool,
        "selected": selected,
        "added": added,
        "skipped": skipped,
        "job": job,
        "executed": executed,
        "daily_cap": daily_cap,
    }
