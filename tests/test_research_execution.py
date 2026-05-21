import asyncio

import pytest

from research.enums import JOB_CANCELLED, JOB_COMPLETED, JOB_FAILED, JOB_RUNNING
from research.execution import (
    ResearchExecutionManager,
    ResearchExecutionOptions,
    build_crawler_start_requests,
    execution_plan_to_dict,
)


def test_build_crawler_start_requests_uses_backend_keywords():
    job = _job(platforms=["wb", "zhihu"], keywords=["policy", "governance"])

    requests = build_crawler_start_requests(job)

    assert [request.platform.value for request in requests] == ["wb", "zhihu"]
    assert requests[0].crawler_type.value == "search"
    assert requests[0].keywords == "policy,governance"
    assert requests[0].specified_ids == ""
    assert requests[0].creator_ids == ""
    assert requests[0].save_option.value == "postgres"


def test_build_crawler_start_requests_supports_detail_mode():
    job = _job(
        collection_mode="detail",
        keywords=[],
        target_ids=["1001", "1002"],
    )

    requests = build_crawler_start_requests(job)

    assert requests[0].crawler_type.value == "detail"
    assert requests[0].keywords == ""
    assert requests[0].specified_ids == "1001,1002"


def test_build_crawler_start_requests_supports_creator_mode():
    job = _job(
        collection_mode="creator",
        keywords=[],
        creator_ids=["author-a", "author-b"],
    )

    requests = build_crawler_start_requests(job)

    assert requests[0].crawler_type.value == "creator"
    assert requests[0].creator_ids == "author-a,author-b"


def test_execution_plan_to_dict_hides_cookies():
    job = _job(keywords=["policy"], comment_policy={"enable_comments": False, "enable_sub_comments": False})
    options = ResearchExecutionOptions(cookies="secret-cookie", headless=True)

    plan = execution_plan_to_dict(build_crawler_start_requests(job, options=options))

    assert plan == [
        {
            "platform": "wb",
            "crawler_type": "search",
            "keywords": "policy",
            "specified_ids": "",
            "creator_ids": "",
            "start_page": 1,
            "enable_comments": False,
            "enable_sub_comments": False,
            "save_option": "postgres",
            "headless": True,
            "login_type": "qrcode",
        }
    ]


def test_build_crawler_start_requests_supports_video_platforms():
    job = _job(platforms=["xhs", "dy", "ks", "bili"])

    requests = build_crawler_start_requests(job)

    assert [request.platform.value for request in requests] == ["xhs", "dy", "ks", "bili"]


@pytest.mark.asyncio
async def test_execute_updates_job_status_to_completed():
    repository = FakeExecutionRepository()
    manager = ResearchExecutionManager(
        crawler_manager=FakeCrawlerManager(),
        repository=repository,
        backfill=None,
    )

    await manager.execute(job=_job(), options=ResearchExecutionOptions(backfill_after_crawl=False))

    assert repository.statuses == [JOB_RUNNING, JOB_COMPLETED]
    assert [event["event_type"] for event in repository.events] == [
        "execution_started",
        "crawler_started",
        "crawler_finished",
        "execution_completed",
    ]


@pytest.mark.asyncio
async def test_execute_passes_mode_filters_to_backfill():
    repository = FakeExecutionRepository()
    backfill = FakeBackfill()
    manager = ResearchExecutionManager(
        crawler_manager=FakeCrawlerManager(),
        repository=repository,
        backfill=backfill,
    )

    await manager.execute(
        job=_job(collection_mode="detail", keywords=[], target_ids=["1001"]),
        options=ResearchExecutionOptions(backfill_after_crawl=True),
    )

    assert backfill.calls == [
        {
            "platform": "wb",
            "job_id": 1,
            "keywords": None,
            "target_ids": ["1001"],
            "creator_ids": None,
        }
    ]


@pytest.mark.asyncio
async def test_execute_updates_job_status_to_failed():
    repository = FakeExecutionRepository()
    manager = ResearchExecutionManager(
        crawler_manager=FailingCrawlerManager(),
        repository=repository,
        backfill=None,
    )

    with pytest.raises(RuntimeError):
        await manager.execute(job=_job(), options=ResearchExecutionOptions(backfill_after_crawl=False))

    assert repository.statuses == [JOB_RUNNING, JOB_FAILED]
    assert repository.events[-1]["event_type"] == "execution_failed"


@pytest.mark.asyncio
async def test_execute_marks_job_failed_when_crawler_start_is_rejected():
    repository = FakeExecutionRepository()
    manager = ResearchExecutionManager(
        crawler_manager=RejectingCrawlerManager(),
        repository=repository,
        backfill=None,
    )

    with pytest.raises(RuntimeError, match="Crawler manager rejected start"):
        await manager.execute(job=_job(), options=ResearchExecutionOptions(backfill_after_crawl=False))

    assert repository.statuses == [JOB_RUNNING, JOB_FAILED]
    assert [event["event_type"] for event in repository.events] == [
        "execution_started",
        "crawler_started",
        "crawler_start_failed",
        "execution_failed",
    ]


@pytest.mark.asyncio
async def test_execute_updates_job_status_to_cancelled():
    repository = FakeExecutionRepository()
    manager = ResearchExecutionManager(
        crawler_manager=CancellingCrawlerManager(),
        repository=repository,
        backfill=None,
    )

    with pytest.raises(asyncio.CancelledError):
        await manager.execute(job=_job(), options=ResearchExecutionOptions(backfill_after_crawl=False))

    assert repository.statuses == [JOB_RUNNING, JOB_CANCELLED]
    assert repository.events[-1]["event_type"] == "execution_cancelled"


class FakeExecutionRepository:
    def __init__(self):
        self.statuses = []
        self.events = []

    async def update_job_status(self, job_id, status):
        self.statuses.append(status)
        return {"id": job_id, "status": status}

    async def create_event(self, **payload):
        self.events.append(payload)
        return payload


class FakeCrawlerManager:
    process = None

    async def start(self, config):
        return True


class FailingCrawlerManager:
    process = None

    async def start(self, config):
        raise RuntimeError("crawler failed")


class RejectingCrawlerManager:
    process = None

    async def start(self, config):
        return False


class CancellingCrawlerManager:
    process = None

    async def start(self, config):
        raise asyncio.CancelledError()


class FakeBackfill:
    def __init__(self):
        self.calls = []

    async def backfill_platform(self, platform, **kwargs):
        self.calls.append({"platform": platform, **kwargs})
        return {"posts": 1}


def _job(
    *,
    platforms=None,
    collection_mode="search",
    keywords=None,
    target_ids=None,
    creator_ids=None,
    comment_policy=None,
):
    return {
        "id": 1,
        "platforms": platforms or ["wb"],
        "collection_mode": collection_mode,
        "keywords": keywords if keywords is not None else ["topic"],
        "target_ids": target_ids or [],
        "creator_ids": creator_ids or [],
        "comment_policy": comment_policy
        if comment_policy is not None
        else {"enable_comments": True, "enable_sub_comments": False},
    }
