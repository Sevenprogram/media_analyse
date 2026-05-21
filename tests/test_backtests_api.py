from datetime import date

from fastapi.testclient import TestClient

import config
from api.main import app


def test_backtest_api_create_run_report(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    store = {}

    class FakeRepository:
        async def create_backtest(self, payload):
            item = {
                "id": 1,
                "scenario": payload["scenario"],
                "vertical_id": payload.get("vertical_id"),
                "scene_pack_id": payload.get("scene_pack_id"),
                "keywords": payload["keywords"],
                "platforms": payload["platforms"],
                "start_date": payload["start_date"],
                "end_date": payload["end_date"],
                "use_local_data": payload.get("use_local_data", True),
                "use_tikhub_backfill": payload.get("use_tikhub_backfill", False),
                "replay_daily": payload.get("replay_daily", True),
                "status": "pending",
                "research_job_id": None,
                "report": {},
                "error_message": None,
            }
            store[1] = item
            return item

        async def list_backtests(self, limit=50):
            del limit
            return list(store.values())

        async def get_backtest(self, backtest_id):
            return store.get(backtest_id)

        async def update_backtest(self, backtest_id, payload):
            item = store[backtest_id]
            if "report" in payload:
                item["report"] = payload["report"]
            for key in ("status", "research_job_id", "error_message"):
                if key in payload:
                    item[key] = payload[key]
            return item

        async def list_all_posts(self, platform=None, start_at=None, end_at=None, limit=None):
            del platform, start_at, end_at, limit
            return []

    import api.routers.backtests as backtests_router

    monkeypatch.setattr(backtests_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(backtests_router, "ensure_backtest_schema", lambda: _noop())
    client = TestClient(app)

    response = client.post(
        "/api/backtests",
        json={
            "scenario": "K12教育+单亲妈妈",
            "keywords": ["K12教育", "单亲妈妈"],
            "platforms": ["xhs", "dy"],
            "start_date": "2026-05-18",
            "end_date": "2026-05-20",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"

    run_response = client.post("/api/backtests/1/run", json={})
    assert run_response.status_code == 200
    assert run_response.json()["backtest"]["status"] == "completed"

    report_response = client.get("/api/backtests/1/report")
    assert report_response.status_code == 200
    assert report_response.json()["report"]["scenario"] == "K12教育+单亲妈妈"


def test_backtest_create_rejects_invalid_date_range(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    import api.routers.backtests as backtests_router

    monkeypatch.setattr(backtests_router, "ensure_backtest_schema", lambda: _noop())
    client = TestClient(app)

    response = client.post(
        "/api/backtests",
        json={
            "scenario": "K12教育",
            "keywords": ["K12教育"],
            "platforms": ["xhs"],
            "start_date": "2026-05-20",
            "end_date": "2026-05-18",
        },
    )

    assert response.status_code == 422


async def _noop():
    return None
