import asyncio
from typing import Any, Protocol

from api.schemas import (
    CrawlerStartRequest,
    CrawlerTypeEnum,
    LoginTypeEnum,
    PlatformEnum,
    SaveDataOptionEnum,
)
from research.backfill import ExistingPlatformBackfill
from research.enums import (
    COLLECTION_CREATOR,
    COLLECTION_DETAIL,
    COLLECTION_SEARCH,
    JOB_CANCELLED,
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_PAUSED_BY_PLATFORM_CONFIG,
    JOB_RUNNING,
)
from research.platforms import get_research_platform
from research.postprocess import run_post_crawl_analysis

CRAWLER_PROCESS_POLL_SECONDS = 1
CRAWLER_HEARTBEAT_SECONDS = 15


class EventRepository(Protocol):
    async def update_job_status(self, job_id: int, status: str) -> dict[str, Any] | None:
        ...

    async def create_event(
        self,
        *,
        job_id: int,
        platform: str | None,
        event_type: str,
        message: str,
        stats: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    async def get_job_stats(self, job_id: int) -> dict[str, Any]:
        ...


class CrawlerProcessManager(Protocol):
    process: Any

    async def start(self, config: CrawlerStartRequest) -> bool:
        ...


class ResearchExecutionOptions:
    def __init__(
        self,
        *,
        login_type: LoginTypeEnum = LoginTypeEnum.QRCODE,
        save_option: SaveDataOptionEnum = SaveDataOptionEnum.POSTGRES,
        cookies: str = "",
        headless: bool = False,
        start_page: int = 1,
        backfill_after_crawl: bool = True,
    ):
        self.login_type = login_type
        self.save_option = save_option
        self.cookies = cookies
        self.headless = headless
        self.start_page = start_page
        self.backfill_after_crawl = backfill_after_crawl


def build_crawler_start_requests(
    job: dict[str, Any],
    *,
    options: ResearchExecutionOptions | None = None,
) -> list[CrawlerStartRequest]:
    options = options or ResearchExecutionOptions()
    collection_mode = job.get("collection_mode") or COLLECTION_SEARCH
    crawler_type = _to_crawler_type_enum(collection_mode)
    keywords = ",".join(job.get("keywords") or [])
    specified_ids = ",".join(job.get("target_ids") or [])
    creator_ids = ",".join(job.get("creator_ids") or [])
    comment_policy = job.get("comment_policy") or {}
    enable_comments = bool(comment_policy.get("enable_comments", True))
    enable_sub_comments = bool(comment_policy.get("enable_sub_comments", False))
    max_notes_count = _positive_int(comment_policy.get("max_posts_per_job"))

    requests: list[CrawlerStartRequest] = []
    for platform in job["platforms"]:
        requests.append(
            CrawlerStartRequest(
                platform=_to_platform_enum(platform),
                login_type=options.login_type,
                crawler_type=crawler_type,
                keywords=keywords,
                specified_ids=specified_ids,
                creator_ids=creator_ids,
                start_page=options.start_page,
                enable_comments=enable_comments,
                enable_sub_comments=enable_sub_comments,
                max_notes_count=max_notes_count,
                save_option=options.save_option,
                cookies=options.cookies,
                headless=options.headless,
            )
        )
    return requests


def build_crawler_start_request_for_unit(
    job: dict[str, Any],
    unit: dict[str, Any],
    *,
    options: ResearchExecutionOptions | None = None,
) -> CrawlerStartRequest:
    options = options or ResearchExecutionOptions()
    collection_mode = unit.get("collection_mode") or job.get("collection_mode") or COLLECTION_SEARCH
    crawler_type = _to_crawler_type_enum(collection_mode)
    comment_policy = job.get("comment_policy") or {}
    enable_comments = bool(comment_policy.get("enable_comments", True))
    enable_sub_comments = bool(comment_policy.get("enable_sub_comments", False))
    max_notes_count = _max_notes_count_for_unit(job)

    return CrawlerStartRequest(
        platform=_to_platform_enum(unit["platform"]),
        login_type=options.login_type,
        crawler_type=crawler_type,
        keywords=unit.get("keyword") or "",
        specified_ids=unit.get("target_id") or "",
        creator_ids=unit.get("creator_id") or "",
        start_page=options.start_page,
        enable_comments=enable_comments,
        enable_sub_comments=enable_sub_comments,
        max_notes_count=max_notes_count,
        save_option=options.save_option,
        cookies=options.cookies,
        headless=options.headless,
    )


def execution_plan_to_dict(requests: list[CrawlerStartRequest]) -> list[dict[str, Any]]:
    return [
        {
            "platform": request.platform.value,
            "crawler_type": request.crawler_type.value,
            "keywords": request.keywords,
            "specified_ids": request.specified_ids,
            "creator_ids": request.creator_ids,
            "start_page": request.start_page,
            "enable_comments": request.enable_comments,
            "enable_sub_comments": request.enable_sub_comments,
            "max_notes_count": request.max_notes_count,
            "save_option": request.save_option.value,
            "headless": request.headless,
            "login_type": request.login_type.value,
        }
        for request in requests
    ]


class ResearchExecutionManager:
    def __init__(
        self,
        *,
        crawler_manager: CrawlerProcessManager,
        repository: EventRepository,
        backfill: ExistingPlatformBackfill | None = None,
    ):
        self.crawler_manager = crawler_manager
        self.repository = repository
        self.backfill = backfill
        self._task: asyncio.Task | None = None

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start_background(
        self,
        *,
        job: dict[str, Any],
        options: ResearchExecutionOptions,
    ) -> None:
        if self.is_running():
            raise RuntimeError("A research execution is already running")
        self._task = asyncio.create_task(self.execute(job=job, options=options))

    async def execute(
        self,
        *,
        job: dict[str, Any],
        options: ResearchExecutionOptions,
    ) -> None:
        await self.repository.update_job_status(job["id"], JOB_RUNNING)
        requests = await self._enabled_start_requests(job=job, options=options)
        if not requests:
            await self.repository.update_job_status(job["id"], JOB_PAUSED_BY_PLATFORM_CONFIG)
            await self.repository.create_event(
                job_id=job["id"],
                platform=None,
                event_type="execution_paused_by_platform_config",
                message="No enabled platform capability is available for this job",
                stats={"platforms": job.get("platforms") or []},
            )
            return
        try:
            await self.repository.create_event(
                job_id=job["id"],
                platform=None,
                event_type="execution_started",
                message="Research job execution started",
                stats={
                    "platforms": [request.platform.value for request in requests],
                    "collection_mode": job.get("collection_mode") or COLLECTION_SEARCH,
                },
            )
            for request in requests:
                await self._execute_platform(job=job, request=request, options=options)
        except asyncio.CancelledError:
            await self.repository.update_job_status(job["id"], JOB_CANCELLED)
            await self.repository.create_event(
                job_id=job["id"],
                platform=None,
                event_type="execution_cancelled",
                message="Research job execution cancelled",
                stats=None,
            )
            raise
        except Exception as exc:
            await self.repository.update_job_status(job["id"], JOB_FAILED)
            await self.repository.create_event(
                job_id=job["id"],
                platform=None,
                event_type="execution_failed",
                message=str(exc),
                stats={"error_type": type(exc).__name__},
            )
            raise
        await self.repository.update_job_status(job["id"], JOB_COMPLETED)
        await self.repository.create_event(
            job_id=job["id"],
            platform=None,
            event_type="execution_completed",
            message="Research job execution completed",
            stats=None,
        )

    async def _execute_platform(
        self,
        *,
        job: dict[str, Any],
        request: CrawlerStartRequest,
        options: ResearchExecutionOptions,
    ) -> None:
        platform = request.platform.value
        await self.repository.create_event(
            job_id=job["id"],
            platform=platform,
            event_type="crawler_started",
            message=f"Starting crawler for {platform}",
            stats={
                "crawler_type": request.crawler_type.value,
                "keywords": request.keywords,
                "specified_ids": request.specified_ids,
                "creator_ids": request.creator_ids,
            },
        )
        started = await self.crawler_manager.start(request)
        if not started:
            await self.repository.create_event(
                job_id=job["id"],
                platform=platform,
                event_type="crawler_start_failed",
                message=f"Crawler manager rejected start for {platform}",
                stats=None,
            )
            raise RuntimeError(f"Crawler manager rejected start for {platform}")

        try:
            await self._wait_for_process(job_id=job["id"], platform=platform, request=request)
        except Exception:
            await self._persist_crawler_output(job_id=job["id"], platform=platform)
            raise

        await self._persist_crawler_output(job_id=job["id"], platform=platform)

        await self.repository.create_event(
            job_id=job["id"],
            platform=platform,
            event_type="crawler_finished",
            message=f"Crawler finished for {platform}",
            stats=None,
        )
        if options.backfill_after_crawl and self.backfill:
            stats = await self.backfill.backfill_platform(
                platform,
                job_id=job["id"],
                keywords=job.get("keywords")
                if request.crawler_type == CrawlerTypeEnum.SEARCH
                else None,
                target_ids=job.get("target_ids")
                if request.crawler_type == CrawlerTypeEnum.DETAIL
                else None,
                creator_ids=job.get("creator_ids")
                if request.crawler_type == CrawlerTypeEnum.CREATOR
                else None,
            )
            await self.repository.create_event(
                job_id=job["id"],
                platform=platform,
                event_type="backfill_completed",
                message=f"Backfill completed for {platform}",
                stats=stats,
            )
            postprocess_stats = await run_post_crawl_analysis(
                self.repository,
                job_id=job["id"],
                platform=platform,
            )
            await self.repository.create_event(
                job_id=job["id"],
                platform=platform,
                event_type="post_crawl_analysis_completed",
                message=f"Post-crawl tagging and creator profile refresh completed for {platform}",
                stats=postprocess_stats,
            )

    async def _enabled_start_requests(
        self,
        *,
        job: dict[str, Any],
        options: ResearchExecutionOptions,
    ) -> list[CrawlerStartRequest]:
        requests = build_crawler_start_requests(job, options=options)
        enabled_requests = []
        for request in requests:
            capability_getter = getattr(self.repository, "get_platform_capability", None)
            capability = await capability_getter(request.platform.value) if capability_getter else None
            if capability is None or _capability_allows_mode(
                capability,
                request.crawler_type.value,
            ):
                enabled_requests.append(request)
                continue
            await self.repository.create_event(
                job_id=job["id"],
                platform=request.platform.value,
                event_type="platform_capability_skipped",
                message=f"Skipped {request.platform.value} because platform capability is disabled",
                stats={"crawler_type": request.crawler_type.value},
            )
        return enabled_requests

    async def _wait_for_process(
        self,
        *,
        job_id: int,
        platform: str,
        request: CrawlerStartRequest,
    ) -> None:
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        last_heartbeat_at = started_at
        process = self.crawler_manager.process
        while process and process.poll() is None:
            await asyncio.sleep(CRAWLER_PROCESS_POLL_SECONDS)
            now = loop.time()
            if now - last_heartbeat_at >= CRAWLER_HEARTBEAT_SECONDS:
                await self._create_crawler_heartbeat(
                    job_id=job_id,
                    platform=platform,
                    request=request,
                    elapsed_seconds=round(now - started_at),
                )
                last_heartbeat_at = now
        if process and process.returncode not in (0, None):
            raise RuntimeError(_crawler_exit_message(int(process.returncode)))

    async def _create_crawler_heartbeat(
        self,
        *,
        job_id: int,
        platform: str,
        request: CrawlerStartRequest,
        elapsed_seconds: int,
    ) -> None:
        stats = await self._heartbeat_stats(job_id)
        latest_log = _latest_log_message(getattr(self.crawler_manager, "logs", None) or [])
        await self.repository.create_event(
            job_id=job_id,
            platform=platform,
            event_type="crawler_heartbeat",
            message=_crawler_heartbeat_message(
                platform=platform,
                elapsed_seconds=elapsed_seconds,
                stats=stats,
                latest_log=latest_log,
            ),
            stats={
                "elapsed_seconds": elapsed_seconds,
                "crawler_type": request.crawler_type.value,
                "keywords": request.keywords,
                "specified_ids": request.specified_ids,
                "creator_ids": request.creator_ids,
                "latest_log": latest_log,
                "sample_counts": stats,
            },
        )

    async def _heartbeat_stats(self, job_id: int) -> dict[str, Any]:
        get_stats = getattr(self.repository, "get_job_stats", None)
        if get_stats is None:
            return {}
        try:
            return await get_stats(job_id)
        except Exception:
            return {}

    async def _persist_crawler_output(self, *, job_id: int, platform: str) -> None:
        raw_logs = getattr(self.crawler_manager, "logs", None) or []
        lines = [_log_entry_to_dict(item) for item in raw_logs]
        if not lines:
            return
        warning_or_error_lines = [
            item
            for item in lines
            if str(item.get("level") or "").lower() in {"warning", "error"}
        ]
        tail = lines[-50:]
        await self.repository.create_event(
            job_id=job_id,
            platform=platform,
            event_type="crawler_output_captured",
            message=_crawler_output_summary(lines),
            stats={
                "line_count": len(lines),
                "warning_or_error_count": len(warning_or_error_lines),
                "tail": tail,
                "warning_or_error_tail": warning_or_error_lines[-20:],
            },
        )


def _to_platform_enum(platform: str) -> PlatformEnum:
    research_platform = get_research_platform(platform)
    if research_platform is None or not research_platform.execution_supported:
        raise ValueError(f"Unsupported research execution platform: {platform}")
    enum_by_value = {item.value: item for item in PlatformEnum}
    crawler_platform = enum_by_value.get(research_platform.crawler_platform)
    if crawler_platform is not None:
        return crawler_platform
    raise ValueError(f"Unsupported research execution platform: {platform}")


def _crawler_exit_message(returncode: int) -> str:
    if returncode == 3221225786:
        return (
            "Crawler was interrupted by a Windows control event "
            "(exit code 3221225786 / 0xC000013A). "
            "This usually means the API terminal was interrupted, closed, or reloaded while the crawler was running."
        )
    return f"Crawler exited with code: {returncode}"


def _log_entry_to_dict(entry: Any) -> dict[str, Any]:
    if hasattr(entry, "model_dump"):
        dumped = entry.model_dump()
        return {
            "timestamp": dumped.get("timestamp"),
            "level": dumped.get("level"),
            "message": dumped.get("message"),
        }
    if isinstance(entry, dict):
        return {
            "timestamp": entry.get("timestamp"),
            "level": entry.get("level"),
            "message": entry.get("message"),
        }
    return {"timestamp": None, "level": "info", "message": str(entry)}


def _crawler_output_summary(lines: list[dict[str, Any]]) -> str:
    for item in reversed(lines):
        message = str(item.get("message") or "").strip()
        level = str(item.get("level") or "").lower()
        if message and level in {"warning", "error"}:
            return message
    for item in reversed(lines):
        message = str(item.get("message") or "").strip()
        if message:
            return message
    return "Crawler output captured"


def _latest_log_message(raw_logs: list[Any]) -> str | None:
    for item in reversed(raw_logs):
        message = str(_log_entry_to_dict(item).get("message") or "").strip()
        if message:
            return message
    return None


def _crawler_heartbeat_message(
    *,
    platform: str,
    elapsed_seconds: int,
    stats: dict[str, Any],
    latest_log: str | None,
) -> str:
    parts = [f"{platform} 采集仍在运行，已等待 {elapsed_seconds}s"]
    if stats:
        parts.append(
            "当前样本 "
            f"posts={int(stats.get('posts') or 0)}, "
            f"comments={int(stats.get('comments') or 0)}, "
            f"raw={int(stats.get('raw_records') or 0)}"
        )
    if latest_log:
        parts.append(f"最新输出：{latest_log}")
    return "; ".join(parts)


def _max_notes_count_for_unit(job: dict[str, Any]) -> int | None:
    per_platform_target = _positive_int((job.get("comment_policy") or {}).get("max_posts_per_job"))
    if per_platform_target is None:
        return None
    collection_mode = job.get("collection_mode") or COLLECTION_SEARCH
    if collection_mode == COLLECTION_SEARCH:
        value_count = len([item for item in job.get("keywords") or [] if str(item).strip()])
    elif collection_mode == COLLECTION_DETAIL:
        value_count = len([item for item in job.get("target_ids") or [] if str(item).strip()])
    elif collection_mode == COLLECTION_CREATOR:
        value_count = len([item for item in job.get("creator_ids") or [] if str(item).strip()])
    else:
        value_count = 1
    return max(1, -(-per_platform_target // max(1, value_count)))


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _to_crawler_type_enum(collection_mode: str) -> CrawlerTypeEnum:
    if collection_mode == COLLECTION_SEARCH:
        return CrawlerTypeEnum.SEARCH
    if collection_mode == COLLECTION_DETAIL:
        return CrawlerTypeEnum.DETAIL
    if collection_mode == COLLECTION_CREATOR:
        return CrawlerTypeEnum.CREATOR
    raise ValueError(f"Unsupported research collection mode: {collection_mode}")


def _capability_allows_mode(capability: dict[str, Any], crawler_type: str) -> bool:
    if not capability.get("enabled", True):
        return False
    if crawler_type == COLLECTION_SEARCH:
        return bool(capability.get("crawl_search_enabled", True))
    if crawler_type == COLLECTION_DETAIL:
        return bool(capability.get("crawl_detail_enabled", True))
    if crawler_type == COLLECTION_CREATOR:
        return bool(capability.get("crawl_creator_enabled", True))
    return True
