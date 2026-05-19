import asyncio

import pytest

from research.enums import JOB_CANCELLED, JOB_COMPLETED, JOB_FAILED, JOB_RUNNING
from research.execution import (
    ResearchExecutionOptions,
    ResearchExecutionManager,
    build_crawler_start_requests,
    execution_plan_to_dict,
)


def test_build_crawler_start_requests_uses_backend_keywords():
    job = {
        "id": 1,
        "platforms": ["wb", "zhihu"],
        "keywords": ["政策", "治理"],
        "comment_policy": {
            "enable_comments": True,
            "enable_sub_comments": False,
        },
    }

    requests = build_crawler_start_requests(job)

    assert [request.platform.value for request in requests] == ["wb", "zhihu"]
    assert requests[0].keywords == "政策,治理"
    assert requests[0].save_option.value == "postgres"


def test_execution_plan_to_dict_hides_cookies():
    job = {
        "id": 1,
        "platforms": ["wb"],
        "keywords": ["政策"],
        "comment_policy": {"enable_comments": False, "enable_sub_comments": False},
    }
    options = ResearchExecutionOptions(cookies="secret-cookie", headless=True)

    plan = execution_plan_to_dict(build_crawler_start_requests(job, options=options))

    assert plan == [
        {
            "platform": "wb",
            "crawler_type": "search",
            "keywords": "政策",
            "start_page": 1,
            "enable_comments": False,
            "enable_sub_comments": False,
            "save_option": "postgres",
            "headless": True,
            "login_type": "qrcode",
        }
    ]


def test_build_crawler_start_requests_supports_video_platforms():
    job = {
        "id": 1,
        "platforms": ["xhs", "dy", "ks", "bili"],
        "keywords": ["topic"],
        "comment_policy": {"enable_comments": True, "enable_sub_comments": False},
    }

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


class CancellingCrawlerManager:
    process = None

    async def start(self, config):
        raise asyncio.CancelledError()


def _job():
    return {
        "id": 1,
        "platforms": ["wb"],
        "keywords": ["topic"],
        "comment_policy": {"enable_comments": True, "enable_sub_comments": False},
    }
