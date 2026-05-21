import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from research.crawl_units import build_crawl_units_for_job
from research.enums import JOB_COMPLETED, JOB_PAUSED_BY_PLATFORM_CONFIG, JOB_PENDING, JOB_QUEUED
from research.repository import ResearchRepository


class ResearchScheduler:
    def __init__(self, repository: ResearchRepository):
        self.repository = repository

    async def schedule_job(
        self,
        job_id: int,
        *,
        max_attempts: int = 4,
        force: bool = False,
    ) -> dict[str, Any]:
        job = await self.repository.get_job(job_id)
        if job is None:
            raise ValueError(f"Research job not found: {job_id}")

        if not force and await self.repository.has_active_crawl_units(job_id):
            return {
                "job_id": job_id,
                "created": 0,
                "existing": 0,
                "active": True,
                "summary": await self.repository.get_crawl_unit_summary(job_id),
                "units": await self.repository.list_crawl_units(job_id),
            }

        now = datetime.now(timezone.utc)
        run_key = f"run-{now.strftime('%Y%m%d%H%M%S')}"
        units = build_crawl_units_for_job(job, max_attempts=max_attempts, run_key=run_key)
        allowed_units = []
        skipped_units = []
        for unit in units:
            if await self._platform_allows_unit(unit):
                allowed_units.append(unit)
            else:
                skipped_units.append(unit)
        units = allowed_units
        if skipped_units and not units:
            await self.repository.update_job_status(job_id, JOB_PAUSED_BY_PLATFORM_CONFIG)
            await self.repository.create_event(
                job_id=job_id,
                platform=None,
                event_type="platform_capability_paused",
                message="All crawl units skipped by platform capability configuration",
                stats={"skipped": len(skipped_units)},
            )
            return {"job_id": job_id, "created": 0, "existing": 0, "units": [], "skipped": len(skipped_units)}
        result = await self.repository.create_crawl_units(units)
        schedule_payload: dict[str, Any] = {
            "status": JOB_QUEUED,
            "last_scheduled_at": now,
        }
        if job.get("schedule_enabled") and job.get("schedule_interval_minutes"):
            schedule_payload["next_run_at"] = now + timedelta(
                minutes=int(job["schedule_interval_minutes"])
            )
        await self.repository.update_job(job_id, schedule_payload)
        await self.repository.create_event(
            job_id=job_id,
            platform=None,
            event_type="crawl_units_scheduled",
            message="Research crawl units scheduled",
            stats={
                "run_key": run_key,
                "created": result["created"],
                "existing": result["existing"],
                "total_units": len(result["units"]),
                "skipped_by_platform_config": len(skipped_units),
            },
        )
        return {"job_id": job_id, **result, "skipped": len(skipped_units)}

    async def _platform_allows_unit(self, unit: dict[str, Any]) -> bool:
        capability_getter = getattr(self.repository, "get_platform_capability", None)
        if capability_getter is None:
            return True
        capability = await capability_getter(unit["platform"])
        if capability is None:
            return True
        if not capability["enabled"]:
            return False
        mode = unit.get("collection_mode")
        if mode == "search":
            return bool(capability["crawl_search_enabled"])
        if mode == "creator":
            return bool(capability["crawl_creator_enabled"])
        if mode == "detail":
            return bool(capability["crawl_detail_enabled"])
        return True

    async def schedule_pending_jobs(self, *, max_attempts: int = 4) -> list[dict[str, Any]]:
        jobs = await self.repository.list_jobs()
        now = datetime.now(timezone.utc)
        results: list[dict[str, Any]] = []
        for job in jobs:
            due = (
                job.get("schedule_enabled")
                and job.get("next_run_at")
                and _as_utc(job["next_run_at"]) <= now
                and job.get("status") == JOB_COMPLETED
            )
            if job.get("status") == JOB_PENDING or due:
                results.append(await self.schedule_job(job["id"], max_attempts=max_attempts))
        return results


async def run_scheduler_loop(interval: int, *, max_attempts: int = 4) -> None:
    scheduler = ResearchScheduler(ResearchRepository())
    while True:
        await scheduler.schedule_pending_jobs(max_attempts=max_attempts)
        await asyncio.sleep(interval)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Research crawl unit scheduler")
    parser.add_argument("--job-id", type=int, default=None)
    parser.add_argument("--interval", type=int, default=0)
    parser.add_argument("--max-attempts", type=int, default=4)
    args = parser.parse_args()

    scheduler = ResearchScheduler(ResearchRepository())
    if args.job_id is not None:
        result = asyncio.run(
            scheduler.schedule_job(args.job_id, max_attempts=args.max_attempts)
        )
        print(result)
        return

    if args.interval > 0:
        asyncio.run(run_scheduler_loop(args.interval, max_attempts=args.max_attempts))
        return

    result = asyncio.run(scheduler.schedule_pending_jobs(max_attempts=args.max_attempts))
    print(result)


if __name__ == "__main__":
    main()
