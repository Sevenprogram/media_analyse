from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from api.schemas import CrawlerTypeEnum
from research.enums import (
    CRAWL_UNIT_CANCELLED,
    CRAWL_UNIT_RUNNING,
    CRAWL_UNIT_SUCCEEDED,
    JOB_COMPLETED,
)
from research.execution import (
    ResearchExecutionManager,
    ResearchExecutionOptions,
    backfill_limit_for_request,
    build_crawler_start_request_for_unit,
    build_crawler_start_requests,
    execution_plan_to_dict,
)


def test_research_job_propagates_search_controls_to_crawler_requests() -> None:
    job = _job(
        {
            "max_posts_per_job": 200,
            "prefer_latest_posts": True,
            "sort_mode": "latest",
            "time_preset": "7d",
            "time_start": "2026-05-01T00:00:00+00:00",
            "time_end": "2026-05-07T23:59:59+00:00",
            "max_results_per_keyword_per_platform": 200,
            "fill_strategy": "prefer_fill",
            "max_extra_pages": 6,
        }
    )

    requests = build_crawler_start_requests(job)
    by_platform = {request.platform.value: request for request in requests}

    assert set(by_platform) == {"xhs", "dy"}
    assert by_platform["xhs"].sort_mode == "latest"
    assert by_platform["dy"].sort_mode == "latest"
    assert by_platform["xhs"].time_preset == "7d"
    assert by_platform["xhs"].time_start.isoformat() == "2026-05-01T00:00:00+00:00"
    assert by_platform["xhs"].time_end.isoformat() == "2026-05-07T23:59:59+00:00"
    assert by_platform["xhs"].max_results_per_keyword_per_platform == 200
    assert by_platform["xhs"].max_extra_pages == 6
    assert by_platform["xhs"].filter_note_time == "\u4e00\u5468\u5185"
    assert backfill_limit_for_request(by_platform["xhs"]) == 400

    plan = execution_plan_to_dict(requests)
    assert plan[0]["sort_mode"] == "latest"
    assert plan[0]["max_results_per_keyword_per_platform"] == 200
    assert plan[0]["fill_strategy"] == "prefer_fill"


def test_research_unit_uses_per_keyword_limit_without_dividing_by_keyword_count() -> None:
    job = _job(
        {
            "max_posts_per_job": 200,
            "sort_mode": "latest",
            "max_results_per_keyword_per_platform": 200,
        }
    )
    unit = {
        "platform": "xhs",
        "collection_mode": "search",
        "keyword": "cat food",
    }

    request = build_crawler_start_request_for_unit(job, unit)

    assert request.keywords == "cat food"
    assert request.max_notes_count == 200
    assert request.max_results_per_keyword_per_platform == 200
    assert backfill_limit_for_request(request) == 200


def test_daily_platform_limit_is_split_across_keywords_for_plan_request() -> None:
    job = _job(
        {
            "max_posts_per_job": 50,
            "max_results_per_keyword_per_platform": 50,
            "daily_collection_limit_per_platform": 50,
        }
    )

    request = build_crawler_start_requests(job)[0]

    assert request.max_notes_count == 50
    assert request.max_results_per_keyword_per_platform == 25
    assert backfill_limit_for_request(request) == 50


def test_daily_platform_limit_is_distributed_across_crawl_units() -> None:
    job = _job(
        {
            "max_posts_per_job": 50,
            "max_results_per_keyword_per_platform": 50,
            "daily_collection_limit_per_platform": 50,
        }
    )
    job["keywords"] = ["alpha", "beta", "gamma"]

    beta_request = build_crawler_start_request_for_unit(
        job,
        {"platform": "xhs", "collection_mode": "search", "keyword": "beta"},
    )
    gamma_request = build_crawler_start_request_for_unit(
        job,
        {"platform": "xhs", "collection_mode": "search", "keyword": "gamma"},
    )

    assert beta_request.max_notes_count == 17
    assert beta_request.max_results_per_keyword_per_platform == 17
    assert gamma_request.max_notes_count == 16
    assert gamma_request.max_results_per_keyword_per_platform == 16


@pytest.mark.asyncio
async def test_execution_continues_after_one_platform_fails() -> None:
    repository = FakeExecutionRepository()
    manager = PlatformFailureExecutionManager(
        repository=repository,
        platforms=["xhs", "dy", "bili"],
        failing_platforms={"dy"},
    )

    await manager.execute(job={"id": 7, "collection_mode": "search"}, options=ResearchExecutionOptions())

    assert manager.executed_platforms == ["xhs", "dy", "bili"]
    assert repository.statuses[-1] == (7, JOB_COMPLETED)
    event_types = [event["event_type"] for event in repository.events]
    assert "platform_execution_failed" in event_types
    assert event_types[-1] == "execution_completed_with_platform_failures"
    completion_event = repository.events[-1]
    assert completion_event["stats"]["succeeded_platforms"] == ["xhs", "bili"]
    assert completion_event["stats"]["failed_platforms"][0]["platform"] == "dy"


@pytest.mark.asyncio
async def test_running_backfill_uses_request_scope_filters() -> None:
    repository = FakeExecutionRepository()
    backfill = FakeBackfill()
    manager = ResearchExecutionManager(
        repository=repository,
        crawler_manager=SimpleNamespace(process=None),
        backfill=backfill,
    )
    request = SimpleNamespace(
        crawler_type=CrawlerTypeEnum.SEARCH,
        keywords="cat food,kitten food",
        specified_ids="",
        creator_ids="",
        max_results_per_keyword_per_platform=200,
        max_notes_count=200,
    )

    await manager._sync_running_backfill(
        job_id=9,
        platform="dy",
        request=request,
    )

    assert backfill.calls == [
        {
            "platform": "dy",
            "job_id": 9,
            "keywords": ["cat food", "kitten food"],
            "target_ids": None,
            "creator_ids": None,
            "limit": 400,
        }
    ]
    assert repository.events == []


@pytest.mark.asyncio
async def test_execution_stops_remaining_units_after_sample_target_reached() -> None:
    repository = FakeExecutionRepository(unit_counts_by_platform={"xhs": 2, "dy": 2})
    manager = SampleTargetExecutionManager(
        repository=repository,
        platforms=["xhs", "dy"],
        target_posts=40,
    )

    await manager.execute(
        job=_job({"max_posts_per_job": 20, "max_results_per_keyword_per_platform": 10}) | {"id": 7},
        options=ResearchExecutionOptions(),
    )

    assert manager.executed_platforms == ["xhs"]
    assert repository.statuses[-1] == (7, JOB_COMPLETED)
    assert repository.bulk_status_updates == [
        {
            "job_id": 7,
            "platform": "xhs",
            "status": CRAWL_UNIT_RUNNING,
            "from_statuses": ("pending", "retrying"),
            "last_error": None,
        },
        {
            "job_id": 7,
            "platform": "xhs",
            "status": CRAWL_UNIT_SUCCEEDED,
            "from_statuses": ("pending", "retrying", "running"),
            "last_error": None,
        },
        {
            "job_id": 7,
            "platform": "dy",
            "status": CRAWL_UNIT_CANCELLED,
            "from_statuses": ("pending", "retrying", "running"),
            "last_error": "Sample target reached before this unit started",
        },
    ]
    assert repository.events[-2]["event_type"] == "crawl_unit_cancelled"
    assert repository.events[-2]["stats"]["cancelled_units"] == 2
    assert repository.events[-1]["event_type"] == "execution_completed"
    assert repository.events[-1]["stats"]["completion_reason"] == "sample_target_reached"
    assert repository.events[-1]["stats"]["posts_count"] == 40


def _job(comment_policy: dict) -> dict:
    return {
        "id": 1,
        "platforms": ["xhs", "dy"],
        "collection_mode": "search",
        "keywords": ["cat food", "cat litter"],
        "target_ids": [],
        "creator_ids": [],
        "start_date": date(2026, 5, 1),
        "end_date": date(2026, 5, 7),
        "comment_policy": {
            "enable_comments": True,
            "enable_sub_comments": False,
            **comment_policy,
        },
    }


class FakeExecutionRepository:
    def __init__(self, *, unit_counts_by_platform: dict[str, int] | None = None) -> None:
        self.statuses: list[tuple[int, str]] = []
        self.events: list[dict] = []
        self.stats_by_job: dict[int, dict] = {}
        self.unit_counts_by_platform = unit_counts_by_platform or {}
        self.bulk_status_updates: list[dict] = []

    async def update_job_status(self, job_id: int, status: str) -> dict | None:
        self.statuses.append((job_id, status))
        return {"id": job_id, "status": status}

    async def create_event(
        self,
        *,
        job_id: int,
        platform: str | None,
        event_type: str,
        message: str,
        stats: dict | None = None,
    ) -> dict:
        event = {
            "job_id": job_id,
            "platform": platform,
            "event_type": event_type,
            "message": message,
            "stats": stats,
        }
        self.events.append(event)
        return event

    async def get_job_stats(self, job_id: int) -> dict:
        return self.stats_by_job.get(job_id, {})

    async def bulk_update_crawl_unit_status(
        self,
        *,
        job_id: int,
        platform: str | None,
        status: str,
        from_statuses: tuple[str, ...],
        last_error: str | None = None,
    ) -> int:
        self.bulk_status_updates.append(
            {
                "job_id": job_id,
                "platform": platform,
                "status": status,
                "from_statuses": from_statuses,
                "last_error": last_error,
            }
        )
        if platform is None:
            return 0
        return int(self.unit_counts_by_platform.get(platform, 0))


class PlatformFailureExecutionManager(ResearchExecutionManager):
    def __init__(
        self,
        *,
        repository: FakeExecutionRepository,
        platforms: list[str],
        failing_platforms: set[str],
    ) -> None:
        super().__init__(
            repository=repository,
            crawler_manager=SimpleNamespace(process=None),
            backfill=None,
        )
        self.platforms = platforms
        self.failing_platforms = failing_platforms
        self.executed_platforms: list[str] = []

    async def _enabled_start_requests(
        self,
        *,
        job: dict,
        options: ResearchExecutionOptions,
    ) -> list[SimpleNamespace]:
        return [SimpleNamespace(platform=SimpleNamespace(value=platform)) for platform in self.platforms]

    async def _execute_platform(
        self,
        *,
        job: dict,
        request: SimpleNamespace,
        options: ResearchExecutionOptions,
    ) -> None:
        platform = request.platform.value
        self.executed_platforms.append(platform)
        if platform in self.failing_platforms:
            raise RuntimeError("simulated crawler failure")


class FakeBackfill:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def backfill_platform(
        self,
        platform: str,
        *,
        job_id: int,
        keywords: list[str] | None = None,
        target_ids: list[str] | None = None,
        creator_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> dict:
        self.calls.append(
            {
                "platform": platform,
                "job_id": job_id,
                "keywords": keywords,
                "target_ids": target_ids,
                "creator_ids": creator_ids,
                "limit": limit,
            }
        )
        return {"posts": 1, "comments": 0, "raw_records": 1}


class SampleTargetExecutionManager(ResearchExecutionManager):
    def __init__(
        self,
        *,
        repository: FakeExecutionRepository,
        platforms: list[str],
        target_posts: int,
    ) -> None:
        super().__init__(
            repository=repository,
            crawler_manager=SimpleNamespace(process=None),
            backfill=None,
        )
        self.platforms = platforms
        self.target_posts = target_posts
        self.executed_platforms: list[str] = []

    async def _enabled_start_requests(
        self,
        *,
        job: dict,
        options: ResearchExecutionOptions,
    ) -> list[SimpleNamespace]:
        return [SimpleNamespace(platform=SimpleNamespace(value=platform)) for platform in self.platforms]

    async def _execute_platform(
        self,
        *,
        job: dict,
        request: SimpleNamespace,
        options: ResearchExecutionOptions,
    ) -> dict | None:
        platform = request.platform.value
        self.executed_platforms.append(platform)
        if platform == "xhs":
            self.repository.stats_by_job[job["id"]] = {"posts": self.target_posts}
            return {
                "sample_target_reached": True,
                "posts_count": self.target_posts,
                "target_posts_total": self.target_posts,
            }
        raise AssertionError("Execution should stop before running the next platform")
