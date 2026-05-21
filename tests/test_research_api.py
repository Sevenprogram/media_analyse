from fastapi.testclient import TestClient

import config
import api.routers.research as research_router
from api.main import app


def test_research_health_route():
    client = TestClient(app)
    response = client.get("/api/research/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": "research"}


def test_research_console_page_is_served():
    client = TestClient(app)
    response = client.get("/research")

    assert response.status_code == 200
    assert "Research Console" in response.text


def test_research_job_validation_runs_before_persistence():
    client = TestClient(app)
    response = client.post(
        "/api/research/jobs",
        json={
            "name": "Bad platform",
            "topic": "topic",
            "platforms": ["unknown"],
            "keywords": ["topic"],
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "comment_policy": {"enable_comments": True},
        },
    )

    assert response.status_code == 422


def test_research_chart_kinds_route():
    client = TestClient(app)
    response = client.get("/api/research/charts/kinds")

    assert response.status_code == 200
    assert "platform_counts" in response.json()["kinds"]
    assert "sentiment_distribution" in response.json()["kinds"]


def test_research_config_options_include_keyword_platforms():
    client = TestClient(app)
    response = client.get("/api/research/config/options")

    assert response.status_code == 200
    platform_values = {item["value"] for item in response.json()["platforms"]}
    collection_modes = {item["value"] for item in response.json()["collection_modes"]}
    assert {"wb", "zhihu", "xhs", "dy", "ks", "bili"}.issubset(platform_values)
    assert collection_modes == {"search", "detail", "creator"}


def test_research_setup_status_route():
    client = TestClient(app)
    response = client.get("/api/research/setup/status")

    assert response.status_code == 200
    assert response.json()["database"]["research_tables_registered"] is True


def test_research_database_routes_require_sql_storage(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "jsonl", raising=False)
    client = TestClient(app)

    response = client.get("/api/research/jobs")

    assert response.status_code == 400
    assert "SQL storage" in response.json()["detail"]


def test_research_ai_routes_require_sql_storage(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "jsonl", raising=False)
    client = TestClient(app)

    response = client.get("/api/research/ai/providers")

    assert response.status_code == 400
    assert "Current value: jsonl" in response.json()["detail"]


def test_4router_bootstrap_reads_env_and_hides_secret(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setenv("FOUR_ROUTER_API_KEY", "secret-4router-key")

    class FakeRepository:
        async def upsert_ai_provider_by_name(self, payload):
            assert payload["api_key"] == "secret-4router-key"
            return {
                "id": 1,
                "name": payload["name"],
                "base_url": payload["base_url"],
                "model": payload["model"],
                "enabled": payload["enabled"],
                "api_key_set": True,
            }

    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post("/api/research/ai/providers/4router/bootstrap")

    assert response.status_code == 200
    assert response.json()["provider"]["base_url"] == "https://4router.net/v1"
    assert response.json()["provider"]["model"] == "gpt-5.4-mini"
    assert "secret-4router-key" not in response.text


def test_backfill_requires_author_hash_salt(monkeypatch):
    monkeypatch.delenv("RESEARCH_AUTHOR_HASH_SALT", raising=False)
    client = TestClient(app)

    response = client.post("/api/research/jobs/1/backfill/weibo", json={"limit": 10})

    assert response.status_code == 400
    assert "RESEARCH_AUTHOR_HASH_SALT" in response.json()["detail"]


def test_execute_requires_author_hash_salt_when_backfill_enabled(monkeypatch):
    monkeypatch.delenv("RESEARCH_AUTHOR_HASH_SALT", raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/research/jobs/999/execute",
        json={"backfill_after_crawl": True},
    )

    assert response.status_code in {400, 404}


def test_research_execution_status_route():
    client = TestClient(app)
    response = client.get("/api/research/execution/status")

    assert response.status_code == 200
    assert "research_execution_running" in response.json()


def test_schedule_research_job_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeScheduler:
        def __init__(self, repository):
            self.repository = repository

        async def schedule_job(self, job_id):
            return {"job_id": job_id, "created": 1, "existing": 0, "units": []}

    monkeypatch.setattr(research_router, "ResearchScheduler", FakeScheduler)
    client = TestClient(app)

    response = client.post("/api/research/jobs/1/schedule")

    assert response.status_code == 200
    assert response.json()["created"] == 1


def test_list_research_job_crawl_units_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_crawl_units(self, job_id, status=None):
            return [{"job_id": job_id, "status": status or "pending"}]

    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/research/jobs/1/crawl-units?status=pending")

    assert response.status_code == 200
    assert response.json() == {"units": [{"job_id": 1, "status": "pending"}]}


def test_worker_status_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_worker_heartbeats(self, *, stale_after_seconds=60):
            return [{"worker_id": "worker-1", "online": True, "status": "idle"}]

    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/research/workers/status")

    assert response.status_code == 200
    assert response.json()["online"] == 1


def test_platform_rate_limit_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def upsert_platform_rate_limit(self, payload):
            return {"id": 1, **payload}

    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.put(
        "/api/research/platform-rate-limits/wb",
        json={
            "platform": "wb",
            "requests_per_minute": 10,
            "min_sleep_seconds": 1,
            "max_sleep_seconds": 3,
            "enabled": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["requests_per_minute"] == 10


def test_auth_profile_routes_hide_cookie(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def create_auth_profile(self, payload):
            assert payload["cookies"] == "secret-cookie"
            return {
                "id": 1,
                "name": payload["name"],
                "platform": payload["platform"],
                "login_type": payload["login_type"],
                "enabled": True,
                "cookie_set": True,
            }

    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/research/auth-profiles",
        json={
            "name": "wb-default",
            "platform": "wb",
            "login_type": "cookie",
            "cookies": "secret-cookie",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    assert "cookies" not in response.json()
    assert response.json()["cookie_set"] is True


def test_validation_checklist_route():
    client = TestClient(app)

    response = client.get("/api/research/validation/checklist?platform=wb")

    assert response.status_code == 200
    assert response.json()["platforms"][0]["platform"] == "wb"


def test_platform_capability_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def upsert_platform_capability(self, payload):
            return {"id": 1, **payload}

    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.put(
        "/api/research/platform-capabilities/wb",
        json={
            "platform": "wb",
            "enabled": True,
            "crawl_search_enabled": True,
            "crawl_creator_enabled": False,
            "crawl_detail_enabled": True,
            "comments_enabled": True,
            "analysis_enabled": True,
            "daily_monitor_enabled": True,
            "keyword_heat_enabled": True,
            "rate_limit_per_minute": 12,
            "notes": "微博默认采集能力",
        },
    )

    assert response.status_code == 200
    assert response.json()["platform"] == "wb"
    assert response.json()["crawl_creator_enabled"] is False


def test_global_defaults_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def upsert_global_setting(self, key, value):
            return {"key": key, "value": value, "updated_at": "2026-05-20T10:00:00"}

    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.put(
        "/api/research/global-settings/defaults",
        json={
            "default_platforms": ["wb", "xhs"],
            "default_collection_mode": "search",
            "default_raw_record_mode": "minimal",
            "default_comment_mode": "limited",
            "default_comment_limit_per_post": 80,
            "default_anonymize_authors": True,
            "default_schedule_enabled": False,
            "default_schedule_interval_minutes": 720,
        },
    )

    assert response.status_code == 200
    assert response.json()["key"] == "research_defaults"
    assert response.json()["value"]["default_platforms"] == ["wb", "xhs"]


def test_keyword_set_create_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def create_keyword_set(self, payload):
            return {"id": 1, **payload}

    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/research/keyword-sets",
        json={
            "name": "新能源汽车口碑",
            "description": "行业监测默认词库",
            "platforms": ["wb", "xhs"],
            "keywords": ["新能源", "智驾", "续航"],
            "negative_keywords": ["广告"],
            "synonyms": ["电车"],
            "topic": "新能源汽车",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["keywords"] == ["新能源", "智驾", "续航"]
