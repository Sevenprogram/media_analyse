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


def test_gateway_bootstrap_reads_env_and_hides_secret(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "secret-gateway-key")
    monkeypatch.setenv("AI_GATEWAY_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "gateway-model")

    class FakeRepository:
        async def upsert_ai_provider_by_name(self, payload):
            assert payload["name"] == "AI Gateway"
            assert payload["api_key"] == "secret-gateway-key"
            assert payload["base_url"] == "https://gateway.example/v1"
            assert payload["model"] == "gateway-model"
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

    response = client.post("/api/research/ai/providers/gateway/bootstrap")

    assert response.status_code == 200
    assert response.json()["provider"]["base_url"] == "https://gateway.example/v1"
    assert response.json()["provider"]["model"] == "gateway-model"
    assert "secret-gateway-key" not in response.text


def test_default_ai_prompts_bootstrap_upserts_two_templates(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    seen = []

    class FakeRepository:
        async def upsert_prompt_template_by_name(self, payload):
            seen.append(payload)
            return {
                "id": len(seen),
                "name": payload["name"],
                "task_type": payload["task_type"],
                "platform": payload["platform"],
                "version": payload["version"],
                "enabled": payload["enabled"],
            }

    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post("/api/research/ai/prompts/defaults/bootstrap")

    assert response.status_code == 200
    assert response.json()["created_or_updated"] == 2
    assert {item["name"] for item in seen} == {
        "default_post_understanding_v1",
        "default_comment_understanding_v1",
    }
    assert all("summary" in item["output_schema"]["properties"] for item in seen)


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


def test_growth_projects_route_lists_aggregated_projects(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeService:
        async def list_growth_projects(self):
            return [
                {
                    "id": "education_summer_2026",
                    "name": "Education Summer 2026",
                    "primary_goal": "topic_discovery",
                    "platforms": ["dy"],
                    "status": "preliminarily_analyzable",
                    "sample_status": {
                        "kind": "comment_insufficient",
                        "label": "Posts sufficient, comments insufficient",
                    },
                    "recommended_action": {
                        "kind": "backfill_comments",
                        "label": "Backfill comments",
                    },
                    "opportunity_score": 70,
                    "last_collected_at": "2026-05-20T14:00:00Z",
                    "metrics": {
                        "jobs": 1,
                        "posts": 60,
                        "comments": 0,
                        "raw_records": 50,
                        "creators": 5,
                        "failed_jobs": 0,
                        "running_jobs": 0,
                        "pending_jobs": 0,
                    },
                    "job_ids": [1],
                }
            ]

    monkeypatch.setattr(research_router, "get_service", lambda: FakeService())
    client = TestClient(app)

    response = client.get("/api/research/growth-projects")

    assert response.status_code == 200
    assert response.json()["projects"][0]["id"] == "education_summer_2026"


def test_growth_project_detail_route_returns_404_for_unknown_project(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeService:
        async def get_growth_project(self, project_id):
            return None

    monkeypatch.setattr(research_router, "get_service", lambda: FakeService())
    client = TestClient(app)

    response = client.get("/api/research/growth-projects/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Growth project not found"


def test_create_growth_project_creates_initial_research_job(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    created = {}

    class FakeService:
        async def create_job(self, request):
            created["request"] = request
            return {
                "id": 10,
                "name": request.name,
                "topic": request.topic,
                "platforms": request.platforms,
                "keywords": request.keywords,
                "status": "pending",
            }

    monkeypatch.setattr(research_router, "get_service", lambda: FakeService())
    client = TestClient(app)

    response = client.post(
        "/api/research/growth-projects",
        json={
            "name": "2026 summer education topic research",
            "primary_goal": "topic_discovery",
            "platforms": ["dy", "xhs"],
            "keywords": ["K12 education", "summer childcare"],
            "collection_depth": "standard",
            "refresh_cadence": "off",
            "auto_ai_analysis": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "2026_summer_education_topic_research"
    assert body["job"]["topic"] == "2026_summer_education_topic_research"
    assert created["request"].comment_policy.enable_comments is True


def test_run_now_growth_project_queues_collection_job(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    created = {}

    class FakeService:
        async def get_growth_project(self, project_id):
            return {
                "project": {
                    "id": project_id,
                    "name": "Education summer",
                    "platforms": ["dy"],
                },
                "keywords": [{"keyword": "K12 education"}],
                "collection_records": [],
            }

        async def create_job(self, request):
            created["request"] = request
            return {
                "id": 22,
                "name": request.name,
                "topic": request.topic,
                "platforms": request.platforms,
                "keywords": request.keywords,
                "status": "pending",
            }

    class FakeRepository:
        async def list_growth_project_records(self, include_archived=False):
            return [{"id": 7, "name": "Education summer"}]

        async def update_growth_project(self, project_id, payload):
            return {"id": project_id, **payload}

        async def update_growth_project_collection_plans(self, project_id, payload):
            return []

    async def fake_enqueue(job_id, *, project_id=None):
        return {
            "status": "queued",
            "job_id": job_id,
            "queue_position": 2,
            "queue": {"running_job_id": 1, "queued_jobs": [], "queue_length": 1},
        }

    monkeypatch.setattr(research_router, "get_service", lambda: FakeService())
    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(research_router, "enqueue_research_collection_job", fake_enqueue)
    client = TestClient(app)

    response = client.post(
        "/api/research/growth-projects/education_summer/collection/run-now",
        json={"target_posts_per_platform": 25},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["queue_position"] == 2
    assert body["job"]["keywords"] == ["K12 education"]
    assert body["target_posts_per_platform"] == 25
    assert body["target_posts_total"] == 25
    assert body["collection_window_days"] == 3
    assert created["request"].comment_policy.max_posts_per_job == 25
    assert (created["request"].end_date - created["request"].start_date).days == 2


def test_growth_project_collection_progress_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeService:
        async def get_growth_project(self, project_id):
            return {
                "project": {"id": project_id, "name": "Education", "platforms": ["dy"]},
                "keywords": [{"keyword": "K12 education"}],
                "collection_records": [{"id": 31, "status": "running"}],
            }

    class FakeRepository:
        async def get_job(self, job_id):
            return {
                "id": job_id,
                "status": "running",
                "name": "Education collection",
                "platforms": ["dy", "xhs"],
                "comment_policy": {"max_posts_per_job": 30},
            }

        async def list_crawl_units(self, job_id):
            return [
                {"status": "succeeded"},
                {"status": "running"},
                {"status": "pending"},
                {"status": "failed"},
            ]

        async def get_job_stats(self, job_id):
            return {"posts": 12, "comments": 3, "raw_records": 15, "authors": 2}

        async def list_events(self, job_id, limit=1):
            return [{"event_type": "unit_done", "message": "done"}]

    monkeypatch.setattr(research_router, "get_service", lambda: FakeService())
    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(research_router, "_research_execution_job_id", 31)
    monkeypatch.setattr(research_router, "_research_execution_task", object())
    monkeypatch.setattr(research_router, "_execution_busy", lambda: True)
    client = TestClient(app)

    response = client.get("/api/research/growth-projects/education/collection/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["progress"]["percent"] == 20
    assert body["progress"]["sample_percent"] == 20
    assert body["progress"]["step_percent"] == 50
    assert body["progress"]["progress_basis"] == "samples"
    assert body["progress"]["sample_counts"]["posts"] == 12
    assert body["progress"]["target_counts"]["posts"] == 60
    assert body["progress"]["latest_event"]["message"] == "done"
    assert body["progress"]["events"][0]["message"] == "done"


def test_growth_project_collection_progress_marks_orphan_running_job_failed(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeService:
        async def get_growth_project(self, project_id):
            return {
                "project": {"id": project_id, "name": "Education", "platforms": ["xhs"]},
                "keywords": [{"keyword": "K12 education"}],
                "collection_records": [{"id": 76, "status": "running"}],
            }

    class FakeRepository:
        async def get_job(self, job_id):
            return {
                "id": job_id,
                "status": "running",
                "name": "Education collection",
                "platforms": ["xhs"],
                "comment_policy": {"max_posts_per_job": 10},
            }

        async def list_crawl_units(self, job_id):
            return []

        async def get_job_stats(self, job_id):
            return {"posts": 0, "comments": 0, "raw_records": 0, "authors": 0}

        async def list_events(self, job_id, limit=1):
            return []

    monkeypatch.setattr(research_router, "get_service", lambda: FakeService())
    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(research_router, "_research_execution_job_id", None)
    monkeypatch.setattr(research_router, "_research_execution_task", None)
    monkeypatch.setattr(research_router, "_research_execution_queue", [])
    monkeypatch.setattr(research_router, "_execution_busy", lambda: False)
    client = TestClient(app)

    response = client.get("/api/research/growth-projects/education/collection/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["progress"]["sample_counts"]["posts"] == 0
    assert body["progress"]["target_counts"]["posts"] == 10


def test_growth_project_collection_progress_marks_completed_zero_sample_job_empty(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeService:
        async def get_growth_project(self, project_id):
            return {
                "project": {"id": project_id, "name": "Education", "platforms": ["xhs"]},
                "keywords": [{"keyword": "K12 education"}],
                "collection_records": [{"id": 77, "status": "completed"}],
            }

    class FakeRepository:
        async def get_job(self, job_id):
            return {
                "id": job_id,
                "status": "completed",
                "name": "Education collection",
                "platforms": ["xhs"],
                "comment_policy": {"max_posts_per_job": 10},
            }

        async def list_crawl_units(self, job_id):
            return []

        async def get_job_stats(self, job_id):
            return {"posts": 0, "comments": 0, "raw_records": 0, "authors": 1}

        async def list_events(self, job_id, limit=1):
            return [{"event_type": "execution_completed", "message": "Research job execution completed"}]

    monkeypatch.setattr(research_router, "get_service", lambda: FakeService())
    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(research_router, "_research_execution_job_id", None)
    monkeypatch.setattr(research_router, "_research_execution_task", None)
    monkeypatch.setattr(research_router, "_research_execution_queue", [])
    monkeypatch.setattr(research_router, "_execution_busy", lambda: False)
    client = TestClient(app)

    response = client.get("/api/research/growth-projects/education/collection/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "empty"
    assert body["progress"]["sample_counts"]["posts"] == 0
    assert body["progress"]["target_counts"]["posts"] == 10


def test_stop_growth_project_current_run_stops_running_crawler(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    stopped = {"crawler": False, "task": False}

    class FakeService:
        async def get_growth_project(self, project_id):
            return {
                "project": {"id": project_id, "name": "Education", "platforms": ["xhs"]},
                "collection_records": [{"id": 31, "status": "running"}],
            }

    class FakeRepository:
        async def update_job(self, job_id, payload):
            return {"id": job_id, **payload}

        async def list_growth_project_records(self, include_archived=False):
            return [{"id": 7, "name": "Education"}]

        async def update_growth_project(self, project_id, payload):
            return {"id": project_id, **payload}

    class FakeCrawlerManager:
        async def stop(self):
            stopped["crawler"] = True
            return True

    class FakeTask:
        def done(self):
            return False

        def cancel(self):
            stopped["task"] = True

    monkeypatch.setattr(research_router, "get_service", lambda: FakeService())
    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(research_router, "crawler_manager", FakeCrawlerManager())
    monkeypatch.setattr(research_router, "_research_execution_job_id", 31)
    monkeypatch.setattr(research_router, "_research_execution_task", FakeTask())
    client = TestClient(app)

    response = client.post("/api/research/growth-projects/education/collection/stop-current-run")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "stopped"
    assert body["crawler_stopped"] is True
    assert stopped == {"crawler": True, "task": True}


def test_growth_project_posts_route_pages_project_posts(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeService:
        async def get_growth_project(self, project_id):
            return {
                "project": {
                    "id": project_id,
                    "name": "Education",
                    "job_ids": [11, 12],
                }
            }

    class FakeRepository:
        async def list_posts_page(self, *, job_ids=None, job_id=None, limit=20, offset=0):
            assert job_ids == [11, 12]
            assert job_id is None
            assert limit == 20
            assert offset == 20
            return {
                "posts": [
                    {"id": post_id, "platform_post_id": f"p{post_id}"}
                    for post_id in range(21, 27)
                ],
                "total": 26,
                "limit": limit,
                "offset": offset,
            }

    monkeypatch.setattr(research_router, "get_service", lambda: FakeService())
    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/research/growth-projects/education/posts?limit=20&offset=20")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 26
    assert body["limit"] == 20
    assert body["offset"] == 20
    assert body["has_more"] is False
    assert body["posts"][0]["platform_post_id"] == "p21"
    assert body["posts"][-1]["platform_post_id"] == "p26"


def test_update_growth_project_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_growth_project_records(self, include_archived=False):
            return [{"id": 7, "name": "Education Summer"}]

        async def update_growth_project(self, project_id, payload):
            return {"id": project_id, "name": payload["name"], "platforms": payload["platforms"]}

        async def create_growth_project_collection_plan(self, payload):
            return payload

    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.patch(
        "/api/research/growth-projects/education_summer",
        json={"name": "Education Summer 2026", "platforms": ["dy", "xhs"]},
    )

    assert response.status_code == 200
    assert response.json()["project"]["name"] == "Education Summer 2026"
    assert response.json()["project"]["platforms"] == ["dy", "xhs"]


def test_update_growth_project_can_switch_scene_pack_and_replace_keywords(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    calls = {"deleted": 0, "keywords": []}

    class FakeRepository:
        async def list_growth_project_records(self, include_archived=False):
            return [{"id": 7, "name": "Education Summer"}]

        async def get_scene_pack(self, scene_pack_id):
            return {"id": scene_pack_id, "name": "K12", "default_platforms": ["dy"]}

        async def list_scene_pack_keywords(self, scene_pack_ids=None, enabled_only=False):
            return [
                {"keyword": "K12 education", "keyword_type": "primary"},
                {"keyword": "summer childcare", "keyword_type": "secondary"},
            ]

        async def delete_growth_project_keywords(self, project_id):
            calls["deleted"] += 1
            return {"deleted": 2}

        async def create_growth_project_keyword(self, payload):
            calls["keywords"].append(payload)
            return payload

        async def update_growth_project(self, project_id, payload):
            return {"id": project_id, **payload}

    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.patch(
        "/api/research/growth-projects/education_summer",
        json={"scene_pack_id": 3, "scene_pack_keyword_mode": "replace"},
    )

    assert response.status_code == 200
    assert calls["deleted"] == 1
    assert [item["keyword"] for item in calls["keywords"]] == [
        "K12 education",
        "summer childcare",
    ]


def test_delete_growth_project_archives_project(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_growth_project_records(self, include_archived=False):
            return [{"id": 7, "name": "Education Summer"}]

        async def update_growth_project(self, project_id, payload):
            return {"id": project_id, **payload}

    monkeypatch.setattr(research_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.delete("/api/research/growth-projects/education_summer")

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert response.json()["project"]["archived"] is True


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
