from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from api.deps.auth import require_current_user
from api.routers.research import require_research_database, schedule_and_execute_research_job
from database.db_session import create_tables
from research.backtesting import run_backtest
from research.repository import ResearchRepository

router = APIRouter(
    prefix="/backtests",
    tags=["backtests"],
    dependencies=[Depends(require_current_user)],
)
_schema_ready = False


class BacktestCreateRequest(BaseModel):
    scenario: str = Field(min_length=1, max_length=255)
    keywords: list[str] = Field(min_length=1)
    platforms: list[str] = Field(default_factory=list)
    start_date: date
    end_date: date
    vertical_id: int | None = Field(default=None, ge=1)
    scene_pack_id: int | None = Field(default=None, ge=1)
    use_local_data: bool = True
    use_tikhub_backfill: bool = False
    replay_daily: bool = True

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > 90:
            raise ValueError("Backtest window cannot exceed 90 days")
        self.keywords = [item.strip() for item in self.keywords if item.strip()]
        if not self.keywords:
            raise ValueError("At least one keyword is required")
        return self


class BacktestRunRequest(BaseModel):
    execute_supplemental_crawl: bool = False


@router.post("")
async def create_backtest(request: BacktestCreateRequest):
    require_research_database()
    await ensure_backtest_schema()
    return await ResearchRepository().create_backtest(request.model_dump(mode="python"))


@router.get("")
async def list_backtests(limit: int = 50):
    require_research_database()
    await ensure_backtest_schema()
    return {"backtests": await ResearchRepository().list_backtests(limit=min(max(limit, 1), 100))}


@router.get("/{backtest_id}")
async def get_backtest(backtest_id: int):
    require_research_database()
    await ensure_backtest_schema()
    backtest = await ResearchRepository().get_backtest(backtest_id)
    if backtest is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return backtest


@router.post("/{backtest_id}/run")
async def run_backtest_endpoint(backtest_id: int, request: BacktestRunRequest):
    require_research_database()
    await ensure_backtest_schema()
    repository = ResearchRepository()
    backtest = await repository.get_backtest(backtest_id)
    if backtest is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    await repository.update_backtest(backtest_id, {"status": "running", "error_message": None})
    backtest = await repository.get_backtest(backtest_id)
    try:
        if backtest and backtest.get("use_tikhub_backfill") and not backtest.get("research_job_id"):
            job = await _create_supplemental_job(repository, backtest)
            await repository.update_backtest(backtest_id, {"research_job_id": job["id"]})
            if request.execute_supplemental_crawl:
                await schedule_and_execute_research_job(
                    job["id"],
                    background=True,
                    force_schedule=True,
                )
            backtest = await repository.get_backtest(backtest_id)
        report = await run_backtest(repository, backtest or {})
        updated = await repository.update_backtest(
            backtest_id,
            {"status": "completed", "report": report, "error_message": None},
        )
        return {"backtest": updated, "report": report}
    except Exception as exc:
        await repository.update_backtest(
            backtest_id,
            {"status": "failed", "error_message": f"{type(exc).__name__}: {exc}"},
        )
        raise


@router.get("/{backtest_id}/report")
async def get_backtest_report(backtest_id: int):
    require_research_database()
    await ensure_backtest_schema()
    backtest = await ResearchRepository().get_backtest(backtest_id)
    if backtest is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return {"backtest_id": backtest_id, "status": backtest["status"], "report": backtest["report"]}


async def _create_supplemental_job(
    repository: ResearchRepository,
    backtest: dict,
) -> dict:
    return await repository.create_job(
        {
            "name": f"historical backtest - {backtest['scenario']}",
            "topic": "historical_backtest",
            "platforms": backtest.get("platforms") or [],
            "collection_mode": "search",
            "keywords": backtest.get("keywords") or [],
            "target_ids": [],
            "creator_ids": [],
            "start_date": backtest["start_date"],
            "end_date": backtest["end_date"],
            "status": "pending",
            "comment_policy": {
                "enable_comments": False,
                "enable_sub_comments": False,
            },
            "raw_record_mode": "minimal",
            "anonymize_authors": True,
        }
    )


async def ensure_backtest_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    await create_tables()
    _schema_ready = True
