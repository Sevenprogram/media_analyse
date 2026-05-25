import asyncio
from datetime import date, datetime
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
    CRAWL_UNIT_CANCELLED,
    CRAWL_UNIT_FAILED,
    CRAWL_UNIT_PENDING,
    CRAWL_UNIT_RETRYING,
    CRAWL_UNIT_RUNNING,
    CRAWL_UNIT_SUCCEEDED,
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
SEARCH_SORT_MODES = {
    "relevance",
    "latest",
    "most_liked",
    "most_commented",
    "most_collected",
}
SEARCH_TIME_PRESETS = {"all", "1d", "7d", "30d", "180d"}
SEARCH_FILL_STRATEGIES = {"prefer_fill"}


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
    comment_policy = job.get("comment_policy") or {}
    daily_limit = _daily_collection_limit(comment_policy)
    values = _collection_values_for_mode(job, collection_mode)
    if daily_limit is not None:
        values = values[:daily_limit]
    keywords = ",".join(values if collection_mode == COLLECTION_SEARCH else (job.get("keywords") or []))
    specified_ids = ",".join(values if collection_mode == COLLECTION_DETAIL else (job.get("target_ids") or []))
    creator_ids = ",".join(values if collection_mode == COLLECTION_CREATOR else (job.get("creator_ids") or []))
    enable_comments = bool(comment_policy.get("enable_comments", True))
    enable_sub_comments = bool(comment_policy.get("enable_sub_comments", False))
    max_notes_count = _positive_int(comment_policy.get("max_posts_per_job"))
    prefer_latest_posts = bool(comment_policy.get("prefer_latest_posts"))
    collection_window_days = _collection_window_days_for_job(job, comment_policy=comment_policy)
    search_controls = _search_controls_for_policy(
        comment_policy,
        prefer_latest_posts=prefer_latest_posts,
        collection_window_days=collection_window_days,
    )
    if daily_limit is not None:
        max_notes_count = daily_limit
        search_controls["max_results_per_keyword_per_platform"] = _per_value_limit(
            daily_limit,
            len(values),
        )

    requests: list[CrawlerStartRequest] = []
    for platform in job["platforms"]:
        platform_value = str(platform)
        latest_search = _latest_search_config(
            platform=platform_value,
            prefer_latest_posts=prefer_latest_posts,
            collection_window_days=collection_window_days,
        )
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
                prefer_latest_posts=latest_search["prefer_latest_posts"],
                sort_type=latest_search["sort_type"],
                filter_note_time=latest_search["filter_note_time"],
                collection_window_days=collection_window_days,
                **search_controls,
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
    max_notes_count = _max_notes_count_for_unit(job, unit=unit, comment_policy=comment_policy)
    collection_window_days = _collection_window_days_for_job(job, comment_policy=comment_policy)
    prefer_latest_posts = bool(comment_policy.get("prefer_latest_posts"))
    search_controls = _search_controls_for_policy(
        comment_policy,
        prefer_latest_posts=prefer_latest_posts,
        collection_window_days=collection_window_days,
    )
    daily_limit = _daily_collection_limit(comment_policy)
    if daily_limit is not None and max_notes_count is not None:
        search_controls["max_results_per_keyword_per_platform"] = max_notes_count
    latest_search = _latest_search_config(
        platform=str(unit["platform"]),
        prefer_latest_posts=prefer_latest_posts,
        collection_window_days=collection_window_days,
    )

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
        prefer_latest_posts=latest_search["prefer_latest_posts"],
        sort_type=latest_search["sort_type"],
        filter_note_time=latest_search["filter_note_time"],
        collection_window_days=collection_window_days,
        **search_controls,
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
            "prefer_latest_posts": request.prefer_latest_posts,
            "sort_type": request.sort_type,
            "filter_note_time": request.filter_note_time,
            "collection_window_days": request.collection_window_days,
            "sort_mode": request.sort_mode,
            "time_preset": request.time_preset,
            "time_start": request.time_start.isoformat() if request.time_start else None,
            "time_end": request.time_end.isoformat() if request.time_end else None,
            "max_results_per_keyword_per_platform": request.max_results_per_keyword_per_platform,
            "fill_strategy": request.fill_strategy,
            "max_extra_pages": request.max_extra_pages,
        }
        for request in requests
    ]


def _latest_search_config(
    *,
    platform: str,
    prefer_latest_posts: bool,
    collection_window_days: int | None,
) -> dict[str, Any]:
    if not prefer_latest_posts or platform != "xhs":
        return {"prefer_latest_posts": False, "sort_type": "", "filter_note_time": ""}
    return {
        "prefer_latest_posts": True,
        "sort_type": "time_descending",
        "filter_note_time": _xhs_filter_note_time(collection_window_days),
    }


def _xhs_filter_note_time(collection_window_days: int | None) -> str:
    if collection_window_days is None:
        return ""
    if collection_window_days <= 1:
        return "\u4e00\u5929\u5185"
    if collection_window_days <= 7:
        return "\u4e00\u5468\u5185"
    return "\u534a\u5e74\u5185"


def _search_controls_for_policy(
    comment_policy: dict[str, Any],
    *,
    prefer_latest_posts: bool,
    collection_window_days: int | None,
) -> dict[str, Any]:
    raw_sort_mode = comment_policy.get("sort_mode")
    sort_mode = _validated_choice(
        raw_sort_mode or ("latest" if prefer_latest_posts else "relevance"),
        valid=SEARCH_SORT_MODES,
        default="relevance",
    )
    time_preset = _validated_choice(
        comment_policy.get("time_preset")
        or _time_preset_from_window(
            collection_window_days,
            prefer_latest_posts=prefer_latest_posts,
        ),
        valid=SEARCH_TIME_PRESETS,
        default="all",
    )
    fill_strategy = _validated_choice(
        comment_policy.get("fill_strategy") or "prefer_fill",
        valid=SEARCH_FILL_STRATEGIES,
        default="prefer_fill",
    )
    max_extra_pages = _positive_int(comment_policy.get("max_extra_pages"))
    return {
        "sort_mode": sort_mode,
        "time_preset": time_preset,
        "time_start": comment_policy.get("time_start"),
        "time_end": comment_policy.get("time_end"),
        "max_results_per_keyword_per_platform": _positive_int(
            comment_policy.get("max_results_per_keyword_per_platform")
        ),
        "fill_strategy": fill_strategy,
        "max_extra_pages": max_extra_pages if max_extra_pages is not None else 5,
    }


def _validated_choice(value: Any, *, valid: set[str], default: str) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in valid else default


def _time_preset_from_window(
    collection_window_days: int | None,
    *,
    prefer_latest_posts: bool,
) -> str:
    if collection_window_days is None or not prefer_latest_posts:
        return "all"
    if collection_window_days <= 1:
        return "1d"
    if collection_window_days <= 7:
        return "7d"
    if collection_window_days <= 30:
        return "30d"
    if collection_window_days <= 180:
        return "180d"
    return "all"


def _collection_window_days_for_job(
    job: dict[str, Any],
    *,
    comment_policy: dict[str, Any],
) -> int | None:
    if comment_policy.get("disable_time_window"):
        return None
    start_date = _coerce_date(job.get("start_date"))
    end_date = _coerce_date(job.get("end_date"))
    if start_date is None or end_date is None:
        return None
    return max(1, (end_date - start_date).days + 1)


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


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
            failed_platforms: list[dict[str, str]] = []
            succeeded_platforms: list[str] = []
            for index, request in enumerate(requests):
                platform = request.platform.value
                await self._set_platform_unit_status(
                    job_id=job["id"],
                    platform=platform,
                    status=CRAWL_UNIT_RUNNING,
                    from_statuses=(CRAWL_UNIT_PENDING, CRAWL_UNIT_RETRYING),
                )
                try:
                    result = await self._execute_platform(job=job, request=request, options=options)
                except Exception as exc:
                    await self._set_platform_unit_status(
                        job_id=job["id"],
                        platform=platform,
                        status=CRAWL_UNIT_FAILED,
                        from_statuses=(
                            CRAWL_UNIT_PENDING,
                            CRAWL_UNIT_RETRYING,
                            CRAWL_UNIT_RUNNING,
                        ),
                        last_error=str(exc),
                    )
                    failed_platforms.append(
                        {
                            "platform": platform,
                            "error_type": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
                    await self.repository.create_event(
                        job_id=job["id"],
                        platform=platform,
                        event_type="platform_execution_failed",
                        message=f"{platform} crawler failed: {exc}",
                        stats={
                            "platform": platform,
                            "error_type": type(exc).__name__,
                            "message": str(exc),
                        },
                    )
                    continue
                await self._set_platform_unit_status(
                    job_id=job["id"],
                    platform=platform,
                    status=CRAWL_UNIT_SUCCEEDED,
                    from_statuses=(
                        CRAWL_UNIT_PENDING,
                        CRAWL_UNIT_RETRYING,
                        CRAWL_UNIT_RUNNING,
                    ),
                )
                succeeded_platforms.append(platform)
                sample_target = result if result else await self._sample_target_state(job=job)
                if sample_target is not None:
                    cancelled_platforms = await self._cancel_remaining_platform_units(
                        job_id=job["id"],
                        platforms=[item.platform.value for item in requests[index + 1 :]],
                    )
                    await self.repository.update_job_status(job["id"], JOB_COMPLETED)
                    await self.repository.create_event(
                        job_id=job["id"],
                        platform=None,
                        event_type="execution_completed",
                        message="Research job execution completed after sample target reached",
                        stats={
                            "completion_reason": "sample_target_reached",
                            "posts_count": int(sample_target.get("posts_count") or 0),
                            "target_posts_total": int(
                                sample_target.get("target_posts_total") or 0
                            ),
                            "succeeded_platforms": succeeded_platforms,
                            "failed_platforms": failed_platforms,
                            "cancelled_platforms": cancelled_platforms,
                        },
                    )
                    return
            if failed_platforms and not succeeded_platforms:
                failed_names = ", ".join(item["platform"] for item in failed_platforms)
                raise RuntimeError(f"All platform crawler executions failed: {failed_names}")
            if failed_platforms:
                await self.repository.update_job_status(job["id"], JOB_COMPLETED)
                await self.repository.create_event(
                    job_id=job["id"],
                    platform=None,
                    event_type="execution_completed_with_platform_failures",
                    message="Research job completed with platform failures",
                    stats={
                        "succeeded_platforms": succeeded_platforms,
                        "failed_platforms": failed_platforms,
                        "error": _platform_failures_summary(failed_platforms),
                    },
                )
                return
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
    ) -> dict[str, Any] | None:
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
                "prefer_latest_posts": request.prefer_latest_posts,
                "sort_type": request.sort_type,
                "filter_note_time": request.filter_note_time,
                "collection_window_days": request.collection_window_days,
                "sort_mode": request.sort_mode,
                "time_preset": request.time_preset,
                "time_start": request.time_start.isoformat() if request.time_start else None,
                "time_end": request.time_end.isoformat() if request.time_end else None,
                "max_results_per_keyword_per_platform": request.max_results_per_keyword_per_platform,
                "fill_strategy": request.fill_strategy,
                "max_extra_pages": request.max_extra_pages,
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
            stop_context = await self._wait_for_process(
                job=job,
                job_id=job["id"],
                platform=platform,
                request=request,
            )
        except Exception as exc:
            output_event = await self._persist_crawler_output(job_id=job["id"], platform=platform)
            message = _enhanced_crawler_failure_message(exc, output_event)
            raise RuntimeError(message) from exc

        await self._persist_crawler_output(job_id=job["id"], platform=platform)

        await self.repository.create_event(
            job_id=job["id"],
            platform=platform,
            event_type="crawler_finished",
            message=f"Crawler finished for {platform}",
            stats={
                **(stop_context or {}),
                "stopped_early": bool(stop_context),
            }
            if stop_context
            else None,
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
                limit=backfill_limit_for_request(request),
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
        return stop_context

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
        job: dict[str, Any],
        job_id: int,
        platform: str,
        request: CrawlerStartRequest,
    ) -> dict[str, Any] | None:
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        last_heartbeat_at = started_at
        process = self.crawler_manager.process
        while process and process.poll() is None:
            await asyncio.sleep(CRAWLER_PROCESS_POLL_SECONDS)
            now = loop.time()
            if now - last_heartbeat_at >= CRAWLER_HEARTBEAT_SECONDS:
                await self._sync_running_backfill(
                    job_id=job_id,
                    platform=platform,
                    request=request,
                )
                stats = await self._heartbeat_stats(job_id)
                stop_context = await self._stop_process_if_sample_target_reached(
                    job=job,
                    stats=stats,
                )
                if stop_context is not None:
                    return stop_context
                await self._create_crawler_heartbeat(
                    job_id=job_id,
                    platform=platform,
                    request=request,
                    elapsed_seconds=round(now - started_at),
                    stats=stats,
                )
                last_heartbeat_at = now
        if process and process.returncode not in (0, None):
            raise RuntimeError(_crawler_exit_message(int(process.returncode)))
        return None

    async def _create_crawler_heartbeat(
        self,
        *,
        job_id: int,
        platform: str,
        request: CrawlerStartRequest,
        elapsed_seconds: int,
        stats: dict[str, Any] | None = None,
    ) -> None:
        stats = stats if stats is not None else await self._heartbeat_stats(job_id)
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
                "sort_mode": request.sort_mode,
                "time_preset": request.time_preset,
                "time_start": request.time_start.isoformat() if request.time_start else None,
                "time_end": request.time_end.isoformat() if request.time_end else None,
                "max_results_per_keyword_per_platform": request.max_results_per_keyword_per_platform,
                "fill_strategy": request.fill_strategy,
                "max_extra_pages": request.max_extra_pages,
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

    async def _sync_running_backfill(
        self,
        *,
        job_id: int,
        platform: str,
        request: CrawlerStartRequest,
    ) -> None:
        if self.backfill is None:
            return
        keywords = [item.strip() for item in str(request.keywords or "").split(",") if item.strip()]
        target_ids = [item.strip() for item in str(request.specified_ids or "").split(",") if item.strip()]
        creator_ids = [item.strip() for item in str(request.creator_ids or "").split(",") if item.strip()]
        try:
            await self.backfill.backfill_platform(
                platform,
                job_id=job_id,
                keywords=keywords if request.crawler_type == CrawlerTypeEnum.SEARCH else None,
                target_ids=target_ids if request.crawler_type == CrawlerTypeEnum.DETAIL else None,
                creator_ids=creator_ids if request.crawler_type == CrawlerTypeEnum.CREATOR else None,
                limit=backfill_limit_for_request(request),
            )
        except Exception as exc:
            await self.repository.create_event(
                job_id=job_id,
                platform=platform,
                event_type="running_backfill_failed",
                message=f"Incremental backfill failed for {platform}: {exc}",
                stats={"error_type": type(exc).__name__},
            )

    async def _stop_process_if_sample_target_reached(
        self,
        *,
        job: dict[str, Any],
        stats: dict[str, Any],
    ) -> dict[str, Any] | None:
        target_posts_total = _job_target_posts_total(job)
        if target_posts_total <= 0:
            return None
        posts_count = int(stats.get("posts") or 0)
        if posts_count < target_posts_total:
            return None
        stopped = await self.crawler_manager.stop()
        if not stopped:
            return None
        return {
            "sample_target_reached": True,
            "posts_count": posts_count,
            "target_posts_total": target_posts_total,
        }

    async def _sample_target_state(self, *, job: dict[str, Any]) -> dict[str, Any] | None:
        target_posts_total = _job_target_posts_total(job)
        if target_posts_total <= 0:
            return None
        stats = await self._heartbeat_stats(int(job["id"]))
        posts_count = int(stats.get("posts") or 0)
        if posts_count < target_posts_total:
            return None
        return {
            "sample_target_reached": True,
            "posts_count": posts_count,
            "target_posts_total": target_posts_total,
        }

    async def _set_platform_unit_status(
        self,
        *,
        job_id: int,
        platform: str,
        status: str,
        from_statuses: tuple[str, ...],
        last_error: str | None = None,
    ) -> int:
        updater = getattr(self.repository, "bulk_update_crawl_unit_status", None)
        if updater is None:
            return 0
        return int(
            await updater(
                job_id=job_id,
                platform=platform,
                status=status,
                from_statuses=from_statuses,
                last_error=last_error,
            )
            or 0
        )

    async def _cancel_remaining_platform_units(
        self,
        *,
        job_id: int,
        platforms: list[str],
    ) -> list[dict[str, Any]]:
        cancelled: list[dict[str, Any]] = []
        seen: set[str] = set()
        for platform in platforms:
            platform_key = str(platform or "").strip()
            if not platform_key or platform_key in seen:
                continue
            seen.add(platform_key)
            cancelled_units = await self._set_platform_unit_status(
                job_id=job_id,
                platform=platform_key,
                status=CRAWL_UNIT_CANCELLED,
                from_statuses=(
                    CRAWL_UNIT_PENDING,
                    CRAWL_UNIT_RETRYING,
                    CRAWL_UNIT_RUNNING,
                ),
                last_error="Sample target reached before this unit started",
            )
            if cancelled_units <= 0:
                continue
            cancelled.append(
                {
                    "platform": platform_key,
                    "cancelled_units": cancelled_units,
                }
            )
            await self.repository.create_event(
                job_id=job_id,
                platform=platform_key,
                event_type="crawl_unit_cancelled",
                message="Skipped remaining crawl units because sample target was reached",
                stats={
                    "reason": "sample_target_reached",
                    "cancelled_units": cancelled_units,
                },
            )
        return cancelled

    async def _persist_crawler_output(self, *, job_id: int, platform: str) -> dict[str, Any] | None:
        raw_logs = getattr(self.crawler_manager, "logs", None) or []
        lines = [_log_entry_to_dict(item) for item in raw_logs]
        if not lines:
            return None
        warning_or_error_lines = [
            item
            for item in lines
            if str(item.get("level") or "").lower() in {"warning", "error"}
        ]
        tail = lines[-50:]
        stats = {
            "line_count": len(lines),
            "warning_or_error_count": len(warning_or_error_lines),
            "tail": tail,
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


def _enhanced_crawler_failure_message(exc: Exception, output_event: dict[str, Any] | None) -> str:
    base_message = str(exc).strip() or type(exc).__name__
    output_message = str((output_event or {}).get("message") or "").strip()
    if not output_message or output_message == base_message:
        output_message = _crawler_output_warning_tail_message(output_event)
    if output_message and output_message != base_message:
        return f"{base_message}; latest crawler error: {output_message}"
    return base_message


def _crawler_output_warning_tail_message(output_event: dict[str, Any] | None) -> str:
    stats = (output_event or {}).get("stats_json") or (output_event or {}).get("stats") or {}
    if not isinstance(stats, dict):
        return ""
    warning_tail = stats.get("warning_or_error_tail")
    if not isinstance(warning_tail, list):
        return ""
    for item in reversed(warning_tail):
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or "").strip()
        if message:
            return message
    return ""


def _platform_failures_summary(failed_platforms: list[dict[str, str]]) -> str:
    parts = []
    for item in failed_platforms:
        platform = item.get("platform") or "unknown"
        message = item.get("message") or item.get("error_type") or "failed"
        parts.append(f"{platform}: {message}")
    return "; ".join(parts)


def _latest_log_message(raw_logs: list[Any]) -> str | None:
    for item in reversed(raw_logs):
        message = str(_log_entry_to_dict(item).get("message") or "").strip()
        if message:
            return message
    return None


def backfill_limit_for_request(request: CrawlerStartRequest) -> int | None:
    unit_limit = request.max_results_per_keyword_per_platform or request.max_notes_count
    if not unit_limit:
        return None
    return max(1, int(unit_limit)) * max(1, _request_value_count(request))


def _request_value_count(request: CrawlerStartRequest) -> int:
    if request.crawler_type == CrawlerTypeEnum.SEARCH:
        return _comma_value_count(request.keywords)
    if request.crawler_type == CrawlerTypeEnum.DETAIL:
        return _comma_value_count(request.specified_ids)
    if request.crawler_type == CrawlerTypeEnum.CREATOR:
        return _comma_value_count(request.creator_ids)
    return 1


def _job_target_posts_total(job: dict[str, Any]) -> int:
    comment_policy = job.get("comment_policy") or {}
    unit_limit = _max_notes_count_for_unit(job, comment_policy=comment_policy)
    if unit_limit is None:
        return 0
    platform_count = len([item for item in job.get("platforms") or [] if str(item).strip()])
    return unit_limit * max(1, _job_value_count(job)) * max(1, platform_count)


def _job_value_count(job: dict[str, Any]) -> int:
    collection_mode = job.get("collection_mode") or COLLECTION_SEARCH
    if collection_mode == COLLECTION_SEARCH:
        values = job.get("keywords") or []
    elif collection_mode == COLLECTION_DETAIL:
        values = job.get("target_ids") or []
    elif collection_mode == COLLECTION_CREATOR:
        values = job.get("creator_ids") or []
    else:
        return 0
    return len([item for item in values if str(item).strip()])


def _comma_value_count(value: str) -> int:
    return len([item for item in str(value or "").split(",") if item.strip()])


def _daily_collection_limit(comment_policy: dict[str, Any]) -> int | None:
    return _positive_int(comment_policy.get("daily_collection_limit_per_platform"))


def _collection_values_for_mode(job: dict[str, Any], collection_mode: str) -> list[str]:
    if collection_mode == COLLECTION_SEARCH:
        return [str(item).strip() for item in job.get("keywords") or [] if str(item).strip()]
    if collection_mode == COLLECTION_DETAIL:
        return [str(item).strip() for item in job.get("target_ids") or [] if str(item).strip()]
    if collection_mode == COLLECTION_CREATOR:
        return [str(item).strip() for item in job.get("creator_ids") or [] if str(item).strip()]
    return []


def _per_value_limit(total_limit: int, value_count: int) -> int:
    return max(1, int(total_limit) // max(1, int(value_count)))


def _distributed_unit_limit(
    job: dict[str, Any],
    unit: dict[str, Any],
    total_limit: int,
) -> int:
    collection_mode = unit.get("collection_mode") or job.get("collection_mode") or COLLECTION_SEARCH
    values = _collection_values_for_mode(job, collection_mode)
    if total_limit < len(values):
        values = values[:total_limit]
    if not values:
        return max(1, int(total_limit))

    if collection_mode == COLLECTION_SEARCH:
        unit_value = str(unit.get("keyword") or "").strip()
    elif collection_mode == COLLECTION_DETAIL:
        unit_value = str(unit.get("target_id") or "").strip()
    elif collection_mode == COLLECTION_CREATOR:
        unit_value = str(unit.get("creator_id") or "").strip()
    else:
        unit_value = None

    try:
        index = values.index(unit_value)
    except ValueError:
        index = 0

    base, remainder = divmod(max(1, int(total_limit)), max(1, len(values)))
    quota = base + (1 if index < remainder else 0)
    return max(1, quota)


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


def _max_notes_count_for_unit(
    job: dict[str, Any],
    *,
    unit: dict[str, Any] | None = None,
    comment_policy: dict[str, Any] | None = None,
) -> int | None:
    comment_policy = comment_policy or job.get("comment_policy") or {}
    daily_limit = _daily_collection_limit(comment_policy)
    if daily_limit is not None:
        return _distributed_unit_limit(job, unit or {}, daily_limit)
    per_keyword_target = _positive_int(
        comment_policy.get("max_results_per_keyword_per_platform")
    )
    collection_mode = job.get("collection_mode") or COLLECTION_SEARCH
    if collection_mode == COLLECTION_SEARCH and per_keyword_target is not None:
        return per_keyword_target
    per_platform_target = _positive_int(comment_policy.get("max_posts_per_job"))
    if per_platform_target is None:
        return None
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
