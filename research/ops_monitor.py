from __future__ import annotations

import argparse
import asyncio
import os
import socket
from collections.abc import Awaitable, Callable
from typing import Any

from api.schemas import SaveDataOptionEnum
from research.competitor_public_flow import (
    DEFAULT_LATEST_LIMIT,
    DEFAULT_MONITOR_INTERVAL_MINUTES,
    create_competitor_monitor_jobs,
)
from research.execution import ResearchExecutionOptions
from research.repository import ResearchRepository
from research.scheduler import ResearchScheduler
from research.worker import ResearchWorker


CompetitorJobSync = Callable[..., Awaitable[dict[str, Any]]]


class OpsMonitorService:
    def __init__(
        self,
        *,
        repository,
        scheduler,
        worker,
        sync_competitor_jobs: CompetitorJobSync = create_competitor_monitor_jobs,
    ):
        self.repository = repository
        self.scheduler = scheduler
        self.worker = worker
        self.sync_competitor_jobs = sync_competitor_jobs

    async def run_once(
        self,
        *,
        monitor_interval_minutes: int = DEFAULT_MONITOR_INTERVAL_MINUTES,
        latest_limit: int = DEFAULT_LATEST_LIMIT,
        max_attempts: int = 4,
        worker_iterations: int = 1,
        save_option: SaveDataOptionEnum = SaveDataOptionEnum.POSTGRES,
        headless: bool = False,
        sync_competitors: bool = True,
        run_scheduler: bool = True,
        run_worker: bool = True,
    ) -> dict[str, Any]:
        competitor_jobs = None
        if sync_competitors:
            competitor_jobs = await self.sync_competitor_jobs(
                self.repository,
                interval_minutes=monitor_interval_minutes,
                latest_limit=latest_limit,
            )

        scheduled = []
        if run_scheduler:
            scheduled = await self.scheduler.schedule_pending_jobs(max_attempts=max_attempts)

        worker_runs = []
        if run_worker:
            options = ResearchExecutionOptions(save_option=save_option, headless=headless)
            for _ in range(max(0, worker_iterations)):
                worker_runs.append(await self.worker.run_once(options=options))

        return {
            "competitor_jobs": competitor_jobs,
            "scheduled": scheduled,
            "worker_runs": worker_runs,
        }


def build_default_ops_monitor_service(*, worker_id: str) -> OpsMonitorService:
    from api.services.crawler_manager import crawler_manager
    from research.backfill import ExistingPlatformBackfill

    repository = ResearchRepository()
    salt = os.getenv("RESEARCH_AUTHOR_HASH_SALT")
    backfill = ExistingPlatformBackfill(repository, author_hash_salt=salt) if salt else None
    worker = ResearchWorker(
        repository=repository,
        crawler_manager=crawler_manager,
        worker_id=worker_id,
        backfill=backfill,
    )
    return OpsMonitorService(
        repository=repository,
        scheduler=ResearchScheduler(repository),
        worker=worker,
    )


async def run_ops_monitor_loop(
    service: OpsMonitorService,
    *,
    interval: int,
    monitor_interval_minutes: int = DEFAULT_MONITOR_INTERVAL_MINUTES,
    latest_limit: int = DEFAULT_LATEST_LIMIT,
    max_attempts: int = 4,
    worker_iterations: int = 1,
    save_option: SaveDataOptionEnum = SaveDataOptionEnum.POSTGRES,
    headless: bool = False,
) -> None:
    while True:
        result = await service.run_once(
            monitor_interval_minutes=monitor_interval_minutes,
            latest_limit=latest_limit,
            max_attempts=max_attempts,
            worker_iterations=worker_iterations,
            save_option=save_option,
            headless=headless,
        )
        print(result, flush=True)
        await asyncio.sleep(interval)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operations growth monitor daemon")
    parser.add_argument("--once", action="store_true", help="Run one sync/schedule/worker cycle and exit")
    parser.add_argument("--interval", type=int, default=60, help="Loop interval in seconds")
    parser.add_argument("--worker-id", default=f"ops-monitor-{socket.gethostname()}-{os.getpid()}")
    parser.add_argument("--worker-iterations", type=int, default=1, help="Worker run_once calls per cycle")
    parser.add_argument("--monitor-interval-minutes", type=int, default=DEFAULT_MONITOR_INTERVAL_MINUTES)
    parser.add_argument("--latest-limit", type=int, default=DEFAULT_LATEST_LIMIT)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--save-option", default=SaveDataOptionEnum.POSTGRES.value)
    parser.add_argument("--headless", action="store_true")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    save_option = SaveDataOptionEnum(args.save_option)
    service = build_default_ops_monitor_service(worker_id=args.worker_id)
    if args.once:
        result = asyncio.run(
            service.run_once(
                monitor_interval_minutes=args.monitor_interval_minutes,
                latest_limit=args.latest_limit,
                max_attempts=args.max_attempts,
                worker_iterations=args.worker_iterations,
                save_option=save_option,
                headless=args.headless,
            )
        )
        print(result)
        return

    asyncio.run(
        run_ops_monitor_loop(
            service,
            interval=args.interval,
            monitor_interval_minutes=args.monitor_interval_minutes,
            latest_limit=args.latest_limit,
            max_attempts=args.max_attempts,
            worker_iterations=args.worker_iterations,
            save_option=save_option,
            headless=args.headless,
        )
    )


if __name__ == "__main__":
    main()
