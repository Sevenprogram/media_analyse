import pytest

from api.schemas import SaveDataOptionEnum
from research.crawl_units import build_crawl_units_for_job, unit_filter_kwargs
from research.enums import (
    CRAWL_UNIT_FAILED,
    CRAWL_UNIT_RETRYING,
    CRAWL_UNIT_SUCCEEDED,
    JOB_COMPLETED,
    JOB_QUEUED,
    JOB_RUNNING,
)
from research.execution import (
    ResearchExecutionOptions,
    build_crawler_start_request_for_unit,
)
from research.scheduler import ResearchScheduler
from research.repository import retry_backoff_seconds
from research.validation import build_validation_checklist
from research.worker import ResearchWorker


def test_build_crawl_units_expands_platform_keyword_matrix():
    job = _job(platforms=["wb", "zhihu"], keywords=["policy", "policy", "governance"])

    units = build_crawl_units_for_job(job)

    assert [(unit["platform"], unit["keyword"]) for unit in units] == [
        ("wb", "policy"),
        ("wb", "governance"),
        ("zhihu", "policy"),
        ("zhihu", "governance"),
    ]
    assert len({unit["unit_key"] for unit in units}) == 4
    assert {unit["status"] for unit in units} == {"pending"}


def test_build_crawler_start_request_for_unit_uses_single_keyword():
    job = _job(keywords=["policy", "governance"])
    unit = build_crawl_units_for_job(job)[0]

    request = build_crawler_start_request_for_unit(
        job,
        unit,
        options=ResearchExecutionOptions(
            save_option=SaveDataOptionEnum.POSTGRES,
            headless=True,
        ),
    )

    assert request.platform.value == "wb"
    assert request.crawler_type.value == "search"
    assert request.keywords == "policy"
    assert request.specified_ids == ""
    assert request.creator_ids == ""
    assert request.save_option.value == "postgres"
    assert request.headless is True


def test_build_crawler_start_request_for_unit_splits_platform_target_across_keywords():
    job = _job(
        keywords=["policy", "governance", "school"],
        comment_policy={
            "enable_comments": True,
            "enable_sub_comments": False,
            "max_posts_per_job": 50,
        },
    )
    unit = build_crawl_units_for_job(job)[0]

    request = build_crawler_start_request_for_unit(job, unit)

    assert request.max_notes_count == 17


def test_unit_filter_kwargs_matches_collection_mode():
    detail_job = _job(collection_mode="detail", keywords=[], target_ids=["post-1"])
    unit = build_crawl_units_for_job(detail_job)[0]

    assert unit_filter_kwargs(unit) == {
        "keywords": None,
        "target_ids": ["post-1"],
        "creator_ids": None,
    }


def test_retry_backoff_seconds_progressively_increases():
    assert retry_backoff_seconds(1) == 60
    assert retry_backoff_seconds(2) == 300
    assert retry_backoff_seconds(3) == 1800
    assert retry_backoff_seconds(99) == 1800


def test_validation_checklist_scopes_platforms():
    checklist = build_validation_checklist(["wb"])

    assert checklist["mode"] == "small_real_collection_validation"
    assert checklist["platforms"][0]["platform"] == "wb"
    assert checklist["platforms"][0]["steps"][0]["key"] == "auth_profile_configured"


@pytest.mark.asyncio
async def test_scheduler_creates_units_and_event():
    repository = FakeSchedulerRepository(job=_job())
    scheduler = ResearchScheduler(repository)

    result = await scheduler.schedule_job(1)

    assert result["created"] == 1
    assert repository.units[0]["keyword"] == "topic"
    assert repository.statuses == [JOB_QUEUED]
    assert repository.events[0]["event_type"] == "crawl_units_scheduled"


@pytest.mark.asyncio
async def test_scheduler_skips_job_with_active_units():
    repository = FakeSchedulerRepository(job=_job(), active=True)
    scheduler = ResearchScheduler(repository)

    result = await scheduler.schedule_job(1)

    assert result["active"] is True
    assert repository.units == []


@pytest.mark.asyncio
async def test_worker_runs_claimed_unit_to_completion():
    unit = build_crawl_units_for_job(_job())[0] | {
        "id": 10,
        "attempt_count": 1,
        "max_attempts": 3,
    }
    repository = FakeWorkerRepository(job=_job(), unit=unit, all_finished=True)
    worker = ResearchWorker(
        repository=repository,
        crawler_manager=FakeCrawlerManager(),
        worker_id="worker-1",
        backfill=FakeBackfill(),
    )

    result = await worker.run_once(
        options=ResearchExecutionOptions(save_option=SaveDataOptionEnum.POSTGRES)
    )

    assert result == {"status": CRAWL_UNIT_SUCCEEDED, "unit_id": 10}
    assert repository.job_statuses == [JOB_RUNNING, JOB_COMPLETED]
    assert repository.unit_statuses == [(10, CRAWL_UNIT_SUCCEEDED, None)]
    assert repository.events[-1]["event_type"] == "research_job_completed"


@pytest.mark.asyncio
async def test_worker_can_scope_claim_to_specific_job():
    unit = build_crawl_units_for_job(_job())[0] | {
        "id": 10,
        "attempt_count": 1,
        "max_attempts": 3,
    }
    repository = FakeWorkerRepository(job=_job(), unit=unit, all_finished=True)
    worker = ResearchWorker(
        repository=repository,
        crawler_manager=FakeCrawlerManager(),
        worker_id="worker-1",
        backfill=FakeBackfill(),
    )

    await worker.run_once(job_id=123)

    assert repository.claimed_job_id == 123


@pytest.mark.asyncio
async def test_worker_retries_failed_unit_until_max_attempts():
    unit = build_crawl_units_for_job(_job())[0] | {
        "id": 10,
        "attempt_count": 2,
        "max_attempts": 3,
    }
    repository = FakeWorkerRepository(job=_job(), unit=unit, all_finished=False)
    worker = ResearchWorker(
        repository=repository,
        crawler_manager=RejectingCrawlerManager(),
        worker_id="worker-1",
    )

    result = await worker.run_once()

    assert result["status"] == CRAWL_UNIT_RETRYING
    assert repository.unit_statuses == [
        (10, CRAWL_UNIT_RETRYING, "Crawler manager rejected crawl unit")
    ]

    unit["attempt_count"] = 3
    repository = FakeWorkerRepository(job=_job(), unit=unit, all_finished=False)
    worker = ResearchWorker(
        repository=repository,
        crawler_manager=RejectingCrawlerManager(),
        worker_id="worker-1",
    )

    result = await worker.run_once()

    assert result["status"] == CRAWL_UNIT_FAILED
    assert repository.unit_statuses == [
        (10, CRAWL_UNIT_FAILED, "Crawler manager rejected crawl unit")
    ]


class FakeSchedulerRepository:
    def __init__(self, job, active=False):
        self.job = job
        self.active = active
        self.units = []
        self.events = []
        self.statuses = []

    async def get_job(self, job_id):
        return self.job if job_id == self.job["id"] else None

    async def list_jobs(self):
        return [self.job]

    async def create_crawl_units(self, units):
        self.units.extend(units)
        return {"created": len(units), "existing": 0, "units": units}

    async def has_active_crawl_units(self, job_id):
        return self.active

    async def get_crawl_unit_summary(self, job_id):
        return {}

    async def list_crawl_units(self, job_id):
        return self.units

    async def create_event(self, **payload):
        self.events.append(payload)
        return payload

    async def update_job_status(self, job_id, status):
        self.statuses.append(status)
        return {"id": job_id, "status": status}

    async def update_job(self, job_id, payload):
        self.statuses.append(payload["status"])
        return {"id": job_id, **payload}


class FakeWorkerRepository:
    def __init__(self, *, job, unit, all_finished):
        self.job = job
        self.unit = unit
        self.all_finished = all_finished
        self.job_statuses = []
        self.unit_statuses = []
        self.events = []
        self.heartbeats = []

    async def claim_next_crawl_unit(self, *, worker_id, job_id=None):
        self.claimed_job_id = job_id
        return self.unit

    async def get_job(self, job_id):
        return self.job if job_id == self.job["id"] else None

    async def update_job_status(self, job_id, status):
        self.job_statuses.append(status)
        return {"id": job_id, "status": status}

    async def update_crawl_unit_status(self, unit_id, status, *, last_error=None):
        self.unit_statuses.append((unit_id, status, last_error))
        return {"id": unit_id, "status": status, "last_error": last_error}

    async def create_event(self, **payload):
        self.events.append(payload)
        return payload

    async def all_crawl_units_finished(self, job_id):
        return self.all_finished

    async def get_crawl_unit_summary(self, job_id):
        return {CRAWL_UNIT_SUCCEEDED: 1}

    async def get_enabled_auth_profile(self, platform, *, include_secret=False):
        return None

    async def get_platform_rate_limit(self, platform):
        return None

    async def upsert_worker_heartbeat(self, **payload):
        self.heartbeats.append(payload)
        return payload


class FakeCrawlerManager:
    process = None

    async def start(self, config):
        return True


class RejectingCrawlerManager:
    process = None

    async def start(self, config):
        return False


class FakeBackfill:
    async def backfill_platform(self, platform, **kwargs):
        return {"posts": 1, "comments": 2}


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
