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
    JOB_RUNNING,
)
from research.platforms import get_research_platform


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
                save_option=options.save_option,
                cookies=options.cookies,
                headless=options.headless,
            )
        )
    return requests


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
        requests = build_crawler_start_requests(job, options=options)
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
            return

        await self._wait_for_process()

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

    async def _wait_for_process(self) -> None:
        while self.crawler_manager.process and self.crawler_manager.process.poll() is None:
            await asyncio.sleep(1)


def _to_platform_enum(platform: str) -> PlatformEnum:
    research_platform = get_research_platform(platform)
    if research_platform is None or not research_platform.execution_supported:
        raise ValueError(f"Unsupported research execution platform: {platform}")
    enum_by_value = {item.value: item for item in PlatformEnum}
    crawler_platform = enum_by_value.get(research_platform.crawler_platform)
    if crawler_platform is not None:
        return crawler_platform
    raise ValueError(f"Unsupported research execution platform: {platform}")


def _to_crawler_type_enum(collection_mode: str) -> CrawlerTypeEnum:
    if collection_mode == COLLECTION_SEARCH:
        return CrawlerTypeEnum.SEARCH
    if collection_mode == COLLECTION_DETAIL:
        return CrawlerTypeEnum.DETAIL
    if collection_mode == COLLECTION_CREATOR:
        return CrawlerTypeEnum.CREATOR
    raise ValueError(f"Unsupported research collection mode: {collection_mode}")
