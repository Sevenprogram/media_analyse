from types import SimpleNamespace

import pytest

from research.worker import ResearchWorker


@pytest.mark.asyncio
async def test_fetch_now_retries_immediately_until_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.routers import competitors as competitors_router

    calls: list[dict] = []

    async def fake_run_worker_once(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return {"status": "retrying", "unit_id": 10, "error": "temporary upstream error"}
        return {"status": "succeeded", "unit_id": 10}

    monkeypatch.setattr(competitors_router, "run_worker_once", fake_run_worker_once)
    monkeypatch.setattr(competitors_router, "FETCH_NOW_IMMEDIATE_RETRY_DELAY_SECONDS", 0)

    result = await competitors_router._run_fetch_now_worker_until_done(
        competitor_id=7,
        request=competitors_router.CompetitorFetchNowRequest(max_attempts=2),
        job_id=99,
    )

    assert result == {"status": "succeeded", "unit_id": 10}
    assert len(calls) == 2
    assert calls[0]["ignore_schedule"] is False
    assert calls[1]["ignore_schedule"] is True
    assert calls[0]["job_id"] == 99
    assert calls[1]["job_id"] == 99


@pytest.mark.asyncio
async def test_worker_failure_message_includes_crawler_log_tail() -> None:
    repository = FakeWorkerRepository()
    crawler_manager = FakeCrawlerManager()
    worker = ResearchWorker(
        repository=repository,
        crawler_manager=crawler_manager,
        worker_id="worker-1",
    )

    result = await worker.run_once()

    assert result["status"] == "retrying"
    assert (
        result["error"]
        == "Crawler exited with code: 1; latest crawler error: TikHub upstream timeout"
    )
    assert repository.status_updates[-1]["last_error"] == result["error"]
    assert any(
        event["event_type"] == "crawler_output_captured"
        and event["message"] == "TikHub upstream timeout"
        for event in repository.events
    )
    assert repository.events[-1]["message"] == result["error"]


class FakeWorkerRepository:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.status_updates: list[dict] = []
        self.claim_kwargs: dict | None = None

    async def claim_next_crawl_unit(self, **kwargs):
        self.claim_kwargs = kwargs
        return {
            "id": 10,
            "job_id": 99,
            "unit_key": "unit-key",
            "platform": "xhs",
            "collection_mode": "creator",
            "keyword": None,
            "target_id": None,
            "creator_id": "creator-1",
            "attempt_count": 1,
            "max_attempts": 2,
        }

    async def get_job(self, job_id: int):
        return {
            "id": job_id,
            "collection_mode": "creator",
            "comment_policy": {"enable_comments": False, "enable_sub_comments": False},
        }

    async def update_job_status(self, job_id: int, status: str):
        return {"id": job_id, "status": status}

    async def update_crawl_unit_status(
        self,
        unit_id: int,
        status: str,
        *,
        last_error: str | None = None,
    ):
        update = {"unit_id": unit_id, "status": status, "last_error": last_error}
        self.status_updates.append(update)
        return update

    async def create_event(
        self,
        *,
        job_id: int,
        platform: str | None,
        event_type: str,
        message: str,
        stats: dict | None = None,
    ):
        event = {
            "job_id": job_id,
            "platform": platform,
            "event_type": event_type,
            "message": message,
            "stats_json": stats or {},
        }
        self.events.append(event)
        return event

    async def get_enabled_auth_profile(self, platform: str, include_secret: bool = False):
        return None

    async def get_platform_rate_limit(self, platform: str):
        return None

    async def upsert_worker_heartbeat(self, **kwargs):
        return kwargs


class FakeCrawlerManager:
    def __init__(self) -> None:
        self.process = None
        self.logs = [
            {"timestamp": "00:00:00", "level": "info", "message": "Starting crawler"},
            {
                "timestamp": "00:00:01",
                "level": "error",
                "message": "TikHub upstream timeout",
            },
        ]

    async def start(self, config) -> bool:
        self.process = SimpleNamespace(returncode=1, poll=lambda: 1)
        return True
