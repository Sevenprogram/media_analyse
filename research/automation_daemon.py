from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from research.enums import (
    JOB_CANCELLED,
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_PAUSED_BY_PLATFORM_CONFIG,
)
from research.repository import ResearchRepository


logger = logging.getLogger(__name__)
DEFAULT_AUTOMATION_INTERVAL_SECONDS = 30
RETRYABLE_TERMINAL_STATUSES = {
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_CANCELLED,
    JOB_PAUSED_BY_PLATFORM_CONFIG,
}
EnqueueJob = Callable[[int, str | None, int | None], Awaitable[dict[str, Any]]]


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "off", "no"}


def automation_should_start() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return _env_flag("RESEARCH_AUTOMATION_ENABLED", True)


def automation_interval_seconds() -> int:
    raw = os.getenv("RESEARCH_AUTOMATION_INTERVAL_SECONDS")
    try:
        return max(5, int(raw or DEFAULT_AUTOMATION_INTERVAL_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_AUTOMATION_INTERVAL_SECONDS


def _as_utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        normalized = text
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _job_is_due(job: dict[str, Any], *, now: datetime) -> bool:
    if not job.get("schedule_enabled"):
        return False
    next_run_at = _as_utc_datetime(job.get("next_run_at"))
    if next_run_at is None or next_run_at > now:
        return False
    return str(job.get("status") or "").lower() in RETRYABLE_TERMINAL_STATUSES


def _project_id_for_job(job: dict[str, Any]) -> str | None:
    topic = str(job.get("topic") or "").strip()
    return topic or None


def _org_id_for_job(job: dict[str, Any]) -> int | None:
    raw = job.get("org_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class ResearchAutomationDaemon:
    def __init__(
        self,
        *,
        repository: ResearchRepository | None = None,
        enqueue_job: EnqueueJob,
        interval_seconds: int | None = None,
        sleep=asyncio.sleep,
    ):
        self.repository = repository or ResearchRepository()
        self.enqueue_job = enqueue_job
        self.interval_seconds = interval_seconds or automation_interval_seconds()
        self.sleep = sleep
        self.task: asyncio.Task | None = None
        self.started_at: str | None = None
        self.last_tick_at: str | None = None
        self.last_success_at: str | None = None
        self.last_error: str | None = None
        self.last_enqueued_jobs: list[dict[str, Any]] = []

    def is_running(self) -> bool:
        return self.task is not None and not self.task.done()

    def snapshot(self) -> dict[str, Any]:
        return {
            "configured_enabled": automation_should_start(),
            "running": self.is_running(),
            "mode": "embedded_api_loop",
            "interval_seconds": self.interval_seconds,
            "started_at": self.started_at,
            "last_tick_at": self.last_tick_at,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "last_enqueued_jobs": list(self.last_enqueued_jobs),
        }

    async def run_once(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        self.last_tick_at = now.isoformat()
        jobs = await self.repository.list_jobs()
        due_jobs = [job for job in jobs if _job_is_due(job, now=now)]
        enqueued: list[dict[str, Any]] = []
        for job in due_jobs:
            job_id = int(job["id"])
            org_id = _org_id_for_job(job)
            result = await self.enqueue_job(job_id, _project_id_for_job(job), org_id)
            enqueued.append(
                {
                    "job_id": job_id,
                    "project_id": result.get("project_id"),
                    "org_id": org_id,
                    "queue_position": result.get("queue_position"),
                }
            )
        self.last_success_at = now.isoformat()
        self.last_error = None
        self.last_enqueued_jobs = enqueued
        return {
            "checked_jobs": len(jobs),
            "due_job_ids": [int(job["id"]) for job in due_jobs],
            "enqueued": enqueued,
        }

    async def start(self) -> asyncio.Task:
        if self.is_running():
            return self.task  # type: ignore[return-value]
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.task = asyncio.create_task(self._run_loop(), name="research-automation-daemon")
        return self.task

    async def stop(self) -> None:
        task = self.task
        self.task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_tick_at = datetime.now(timezone.utc).isoformat()
                self.last_error = str(exc)
                logger.exception("Research automation daemon tick failed")
            await self.sleep(self.interval_seconds)


_automation_daemon: ResearchAutomationDaemon | None = None


async def ensure_research_automation_daemon_started(
    *,
    enqueue_job: EnqueueJob,
    interval_seconds: int | None = None,
) -> dict[str, Any]:
    global _automation_daemon
    if not automation_should_start():
        return get_research_automation_status()
    if _automation_daemon is None:
        _automation_daemon = ResearchAutomationDaemon(
            enqueue_job=enqueue_job,
            interval_seconds=interval_seconds,
        )
    await _automation_daemon.start()
    return _automation_daemon.snapshot()


async def stop_research_automation_daemon() -> None:
    global _automation_daemon
    daemon = _automation_daemon
    _automation_daemon = None
    if daemon is not None:
        await daemon.stop()


def get_research_automation_status() -> dict[str, Any]:
    if _automation_daemon is None:
        return {
            "configured_enabled": automation_should_start(),
            "running": False,
            "mode": "embedded_api_loop",
            "interval_seconds": automation_interval_seconds(),
            "started_at": None,
            "last_tick_at": None,
            "last_success_at": None,
            "last_error": None,
            "last_enqueued_jobs": [],
        }
    return _automation_daemon.snapshot()
