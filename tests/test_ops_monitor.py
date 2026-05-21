import pytest

from api.schemas import SaveDataOptionEnum
from research.ops_monitor import OpsMonitorService, build_arg_parser


@pytest.mark.asyncio
async def test_ops_monitor_run_once_syncs_schedules_and_runs_worker():
    repository = FakeRepository()
    scheduler = FakeScheduler()
    worker = FakeWorker()

    service = OpsMonitorService(
        repository=repository,
        scheduler=scheduler,
        worker=worker,
        sync_competitor_jobs=repository.sync_competitor_jobs,
    )

    result = await service.run_once(
        monitor_interval_minutes=480,
        latest_limit=50,
        max_attempts=3,
        worker_iterations=2,
    )

    assert result["competitor_jobs"] == {"created_or_updated": 1}
    assert result["scheduled"] == [{"job_id": 1, "created": 1}]
    assert result["worker_runs"] == [
        {"status": "succeeded", "unit_id": 10},
        {"status": "idle", "worker_id": "worker-1"},
    ]
    assert repository.sync_args == {"interval_minutes": 480, "latest_limit": 50}
    assert scheduler.max_attempts == 3
    assert worker.options[0].save_option == SaveDataOptionEnum.POSTGRES


@pytest.mark.asyncio
async def test_ops_monitor_run_once_can_skip_sync_and_worker():
    repository = FakeRepository()
    scheduler = FakeScheduler()
    worker = FakeWorker()
    service = OpsMonitorService(
        repository=repository,
        scheduler=scheduler,
        worker=worker,
        sync_competitor_jobs=repository.sync_competitor_jobs,
    )

    result = await service.run_once(sync_competitors=False, run_worker=False)

    assert result["competitor_jobs"] is None
    assert result["scheduled"] == [{"job_id": 1, "created": 1}]
    assert result["worker_runs"] == []
    assert repository.sync_args is None


def test_ops_monitor_arg_parser_defaults_match_first_version_policy():
    args = build_arg_parser().parse_args(["--once"])

    assert args.once is True
    assert args.interval == 60
    assert args.monitor_interval_minutes == 480
    assert args.latest_limit == 50
    assert args.worker_iterations == 1
    assert args.save_option == "postgres"


class FakeRepository:
    def __init__(self):
        self.sync_args = None

    async def sync_competitor_jobs(self, repository, *, interval_minutes, latest_limit):
        assert repository is self
        self.sync_args = {
            "interval_minutes": interval_minutes,
            "latest_limit": latest_limit,
        }
        return {"created_or_updated": 1}


class FakeScheduler:
    def __init__(self):
        self.max_attempts = None

    async def schedule_pending_jobs(self, *, max_attempts):
        self.max_attempts = max_attempts
        return [{"job_id": 1, "created": 1}]


class FakeWorker:
    def __init__(self):
        self.calls = 0
        self.options = []

    async def run_once(self, *, options):
        self.calls += 1
        self.options.append(options)
        if self.calls == 1:
            return {"status": "succeeded", "unit_id": 10}
        return {"status": "idle", "worker_id": "worker-1"}
