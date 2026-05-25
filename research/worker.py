import argparse
import asyncio
import os
import random
import socket
from datetime import datetime, timezone
from typing import Any, Protocol

from api.schemas import LoginTypeEnum, SaveDataOptionEnum
from research.backfill import ExistingPlatformBackfill
from research.crawl_units import unit_filter_kwargs
from research.enums import (
    CRAWL_UNIT_FAILED,
    CRAWL_UNIT_RETRYING,
    CRAWL_UNIT_SUCCEEDED,
    JOB_COMPLETED,
    JOB_RUNNING,
)
from research.execution import (
    ResearchExecutionOptions,
    _crawler_exit_message,
    _crawler_output_summary,
    _enhanced_crawler_failure_message,
    _log_entry_to_dict,
    backfill_limit_for_request,
    build_crawler_start_request_for_unit,
)
from research.postprocess import run_post_crawl_analysis
from research.repository import ResearchRepository


class UnitCrawlerManager(Protocol):
    process: Any

    async def start(self, config) -> bool:
        ...


class ResearchWorker:
    def __init__(
        self,
        *,
        repository: ResearchRepository,
        crawler_manager: UnitCrawlerManager,
        worker_id: str,
        backfill: ExistingPlatformBackfill | None = None,
        sleep=asyncio.sleep,
    ):
        self.repository = repository
        self.crawler_manager = crawler_manager
        self.worker_id = worker_id
        self.backfill = backfill
        self.sleep = sleep
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        self.started_at = datetime.now(timezone.utc)

    async def run_once(
        self,
        *,
        options: ResearchExecutionOptions | None = None,
        job_id: int | None = None,
        ignore_schedule: bool = False,
    ) -> dict[str, Any]:
        options = options or ResearchExecutionOptions()
        await self._heartbeat(status="idle")
        unit = await self.repository.claim_next_crawl_unit(
            worker_id=self.worker_id,
            job_id=job_id,
            ignore_schedule=ignore_schedule,
        )
        if unit is None:
            return {"status": "idle", "worker_id": self.worker_id}
        await self._heartbeat(status="running", current_unit_id=unit["id"])

        job = await self.repository.get_job(unit["job_id"])
        if job is None:
            await self.repository.update_crawl_unit_status(
                unit["id"], CRAWL_UNIT_FAILED, last_error="Research job not found"
            )
            return {"status": "failed", "unit_id": unit["id"], "error": "job_not_found"}

        await self.repository.update_job_status(job["id"], JOB_RUNNING)
        await self.repository.create_event(
            job_id=job["id"],
            platform=unit["platform"],
            event_type="crawl_unit_started",
            message="Research crawl unit started",
            stats={"unit_id": unit["id"], "unit_key": unit["unit_key"]},
        )

        try:
            effective_options = await self._options_for_unit(unit, options)
            await self._apply_rate_limit(unit["platform"])
            request = build_crawler_start_request_for_unit(job, unit, options=effective_options)
            started = await self.crawler_manager.start(request)
            if not started:
                raise RuntimeError("Crawler manager rejected crawl unit")
            await self._wait_for_process(unit_id=unit["id"])
            await self._run_backfill(job=job, unit=unit, request=request)
        except Exception as exc:
            try:
                output_event = await self._persist_crawler_output(
                    job_id=job["id"],
                    platform=unit["platform"],
                )
            except Exception:
                output_event = None
            error_message = _enhanced_crawler_failure_message(exc, output_event)
            status = (
                CRAWL_UNIT_FAILED
                if unit["attempt_count"] >= unit["max_attempts"]
                else CRAWL_UNIT_RETRYING
            )
            await self.repository.update_crawl_unit_status(
                unit["id"], status, last_error=error_message
            )
            await self.repository.create_event(
                job_id=job["id"],
                platform=unit["platform"],
                event_type="crawl_unit_failed",
                message=error_message,
                stats={
                    "unit_id": unit["id"],
                    "status": status,
                    "error_type": type(exc).__name__,
                },
            )
            await self._heartbeat(status="idle")
            return {
                "status": status,
                "unit_id": unit["id"],
                "error": error_message,
            }

        await self.repository.update_crawl_unit_status(unit["id"], CRAWL_UNIT_SUCCEEDED)
        await self.repository.create_event(
            job_id=job["id"],
            platform=unit["platform"],
            event_type="crawl_unit_succeeded",
            message="Research crawl unit completed",
            stats={"unit_id": unit["id"]},
        )

        if await self.repository.all_crawl_units_finished(job["id"]):
            await self.repository.update_job_status(job["id"], JOB_COMPLETED)
            await self.repository.create_event(
                job_id=job["id"],
                platform=None,
                event_type="research_job_completed",
                message="All research crawl units completed",
                stats=await self.repository.get_crawl_unit_summary(job["id"]),
            )

        await self._heartbeat(status="idle")
        return {"status": CRAWL_UNIT_SUCCEEDED, "unit_id": unit["id"]}

    async def _wait_for_process(self, *, unit_id: int) -> None:
        process = self.crawler_manager.process
        heartbeat_tick = 0
        while process and process.poll() is None:
            await self.sleep(1)
            heartbeat_tick += 1
            if heartbeat_tick >= 10:
                heartbeat_tick = 0
                await self._heartbeat(status="running", current_unit_id=unit_id)
        if process and process.returncode not in (0, None):
            raise RuntimeError(_crawler_exit_message(int(process.returncode)))

    async def _persist_crawler_output(
        self,
        *,
        job_id: int,
        platform: str,
    ) -> dict[str, Any] | None:
        raw_logs = getattr(self.crawler_manager, "logs", None) or []
        lines = [_log_entry_to_dict(item) for item in raw_logs]
        if not lines:
            return None
        warning_or_error_lines = [
            item
            for item in lines
            if str(item.get("level") or "").lower() in {"warning", "error"}
        ]
        stats = {
            "line_count": len(lines),
            "warning_or_error_count": len(warning_or_error_lines),
            "tail": lines[-50:],
            "warning_or_error_tail": warning_or_error_lines[-20:],
        }
        message = _crawler_output_summary(lines)
        event = await self.repository.create_event(
            job_id=job_id,
            platform=platform,
            event_type="crawler_output_captured",
            message=message,
            stats=stats,
        )
        if event is None:
            return {"message": message, "stats_json": stats}
        return event

    async def _run_backfill(
        self,
        *,
        job: dict[str, Any],
        unit: dict[str, Any],
        request,
    ) -> None:
        if self.backfill is None:
            return
        stats = await self.backfill.backfill_platform(
            unit["platform"],
            job_id=job["id"],
            limit=backfill_limit_for_request(request),
            **unit_filter_kwargs(unit),
        )
        await self.repository.create_event(
            job_id=job["id"],
            platform=unit["platform"],
            event_type="crawl_unit_backfill_completed",
            message="Research crawl unit backfill completed",
            stats={"unit_id": unit["id"], **stats},
        )
        postprocess_stats = await run_post_crawl_analysis(
            self.repository,
            job_id=job["id"],
            platform=unit["platform"],
        )
        await self.repository.create_event(
            job_id=job["id"],
            platform=unit["platform"],
            event_type="crawl_unit_postprocess_completed",
            message="Research crawl unit tagging and creator profile refresh completed",
            stats={"unit_id": unit["id"], **postprocess_stats},
        )

    async def _options_for_unit(
        self, unit: dict[str, Any], options: ResearchExecutionOptions
    ) -> ResearchExecutionOptions:
        if options.cookies:
            return options
        profile = await self.repository.get_enabled_auth_profile(
            unit["platform"], include_secret=True
        )
        if not profile:
            return options
        return ResearchExecutionOptions(
            login_type=LoginTypeEnum(profile["login_type"]),
            save_option=options.save_option,
            cookies=profile.get("cookies") or "",
            headless=options.headless,
            start_page=options.start_page,
            backfill_after_crawl=options.backfill_after_crawl,
        )

    async def _apply_rate_limit(self, platform: str) -> None:
        rate_limit = await self.repository.get_platform_rate_limit(platform)
        if not rate_limit or not rate_limit.get("enabled", True):
            return
        rpm_delay = 60 / max(1, int(rate_limit["requests_per_minute"]))
        min_sleep = max(float(rate_limit["min_sleep_seconds"]), rpm_delay)
        max_sleep = max(float(rate_limit["max_sleep_seconds"]), min_sleep)
        await self.sleep(random.uniform(min_sleep, max_sleep))

    async def _heartbeat(
        self,
        *,
        status: str,
        current_unit_id: int | None = None,
    ) -> None:
        await self.repository.upsert_worker_heartbeat(
            worker_id=self.worker_id,
            hostname=self.hostname,
            pid=self.pid,
            status=status,
            current_unit_id=current_unit_id,
            started_at=self.started_at,
            metadata={"component": "research.worker"},
        )


async def run_worker_loop(
    *,
    interval: int,
    worker_id: str,
    save_option: SaveDataOptionEnum,
    headless: bool,
) -> None:
    from api.services.crawler_manager import crawler_manager

    repository = ResearchRepository()
    salt = os.getenv("RESEARCH_AUTHOR_HASH_SALT")
    backfill = ExistingPlatformBackfill(repository, author_hash_salt=salt) if salt else None
    worker = ResearchWorker(
        repository=repository,
        crawler_manager=crawler_manager,
        worker_id=worker_id,
        backfill=backfill,
    )
    options = ResearchExecutionOptions(save_option=save_option, headless=headless)
    while True:
        await worker.run_once(options=options)
        await asyncio.sleep(interval)


async def run_worker_once(
    *,
    worker_id: str,
    save_option: SaveDataOptionEnum,
    headless: bool,
    job_id: int | None = None,
    ignore_schedule: bool = False,
) -> dict[str, Any]:
    from api.services.crawler_manager import crawler_manager

    repository = ResearchRepository()
    salt = os.getenv("RESEARCH_AUTHOR_HASH_SALT")
    backfill = ExistingPlatformBackfill(repository, author_hash_salt=salt) if salt else None
    worker = ResearchWorker(
        repository=repository,
        crawler_manager=crawler_manager,
        worker_id=worker_id,
        backfill=backfill,
    )
    return await worker.run_once(
        options=ResearchExecutionOptions(save_option=save_option, headless=headless),
        job_id=job_id,
        ignore_schedule=ignore_schedule,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Research crawl unit worker")
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}-{os.getpid()}")
    parser.add_argument("--save-option", default="postgres")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    save_option = SaveDataOptionEnum(args.save_option)
    if args.once:
        print(
            asyncio.run(
                run_worker_once(
                    worker_id=args.worker_id,
                    save_option=save_option,
                    headless=args.headless,
                )
            )
        )
        return

    asyncio.run(
        run_worker_loop(
            interval=args.interval,
            worker_id=args.worker_id,
            save_option=save_option,
            headless=args.headless,
        )
    )


if __name__ == "__main__":
    main()
