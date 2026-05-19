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


class EventRepository(Protocol):
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
    keywords = ",".join(job["keywords"])
    comment_policy = job.get("comment_policy") or {}
    enable_comments = bool(comment_policy.get("enable_comments", True))
    enable_sub_comments = bool(comment_policy.get("enable_sub_comments", False))

    requests: list[CrawlerStartRequest] = []
    for platform in job["platforms"]:
        requests.append(
            CrawlerStartRequest(
                platform=_to_platform_enum(platform),
                login_type=options.login_type,
                crawler_type=CrawlerTypeEnum.SEARCH,
                keywords=keywords,
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
        requests = build_crawler_start_requests(job, options=options)
        await self.repository.create_event(
            job_id=job["id"],
            platform=None,
            event_type="execution_started",
            message="Research job execution started",
            stats={"platforms": [request.platform.value for request in requests]},
        )
        for request in requests:
            await self._execute_platform(job=job, request=request, options=options)
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
            stats={"keywords": request.keywords},
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
            if platform == "wb":
                stats = await self.backfill.backfill_weibo(
                    job_id=job["id"], keywords=job["keywords"]
                )
            elif platform == "zhihu":
                stats = await self.backfill.backfill_zhihu(
                    job_id=job["id"], keywords=job["keywords"]
                )
            else:
                stats = {}
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
    if platform == "wb":
        return PlatformEnum.WEIBO
    if platform == "zhihu":
        return PlatformEnum.ZHIHU
    raise ValueError(f"Unsupported research execution platform: {platform}")
