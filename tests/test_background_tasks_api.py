from fastapi.testclient import TestClient

import api.routers.creator_search as creator_search_router
import api.routers.research as research_router
import api.services.background_task_center as task_center
from api.main import app


class FakeRepository:
    def __init__(self):
        self.updated_jobs = []
        self.events = []
        self.ai_statuses = []
        self.jobs = []

    async def get_job(self, job_id):
        return {
            "id": job_id,
            "name": f"Job {job_id}",
            "topic": "content_realtime_discovery" if job_id == 20 else "project-alpha",
            "platforms": ["xhs"],
            "collection_mode": "search",
            "status": "queued",
        }

    async def list_jobs(self):
        return self.jobs

    async def update_job(self, job_id, payload):
        self.updated_jobs.append((job_id, payload))
        return {
            "id": job_id,
            "name": f"Job {job_id}",
            "topic": "project-alpha",
            "status": payload.get("status"),
        }

    async def create_event(self, **payload):
        self.events.append(payload)
        return payload

    async def list_growth_project_records(self, include_archived=False):
        return []

    async def update_ai_analysis_job_status(self, analysis_job_id, status):
        self.ai_statuses.append((analysis_job_id, status))
        return {"id": analysis_job_id, "status": status}


class FakeLiveTask:
    def __init__(self):
        self.cancelled = False

    def done(self):
        return False

    def cancel(self):
        self.cancelled = True


def setup_function():
    research_router._research_execution_queue.clear()
    research_router._research_executions.clear()
    research_router._research_execution_task = None
    research_router._research_execution_job_id = None
    research_router._research_execution_concurrency = 1
    research_router.AI_ANALYSIS_TASKS.clear()
    creator_search_router.CREATOR_SEARCH_TASKS.clear()


def test_background_tasks_lists_research_queue_and_creator_search(monkeypatch):
    fake_repository = FakeRepository()
    monkeypatch.setattr(task_center, "ResearchRepository", lambda: fake_repository)
    research_router._research_execution_queue.append(
        {"job_id": 20, "project_id": None, "queue_position": 1, "enqueued_at": "2026-05-22"}
    )
    creator_search_router.CREATOR_SEARCH_TASKS["abc123"] = {
        "task_id": "abc123",
        "status": "running",
        "request": {"raw_query": "AI creators"},
        "progress": {"stage": "realtime", "label": "Searching realtime platforms", "percent": 50},
        "result": None,
        "error": None,
        "created_at": "2026-05-22T00:00:00Z",
        "updated_at": "2026-05-22T00:01:00Z",
    }

    response = TestClient(app).get("/api/background-tasks")

    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body["tasks"]}
    assert "research-queue:20" in ids
    assert "creator-search:abc123" in ids
    assert body["summary"]["queued"] == 1
    assert body["summary"]["running"] == 1
    research_item = next(item for item in body["tasks"] if item["id"] == "research-queue:20")
    assert research_item["source"] == "content_search"
    assert research_item["cancellable"] is True


def test_background_tasks_lists_multiple_running_research_jobs(monkeypatch):
    fake_repository = FakeRepository()
    monkeypatch.setattr(task_center, "ResearchRepository", lambda: fake_repository)
    research_router._research_executions[20] = {
        "task": FakeLiveTask(),
        "crawler_manager": object(),
        "started_at": "2026-05-22",
    }
    research_router._research_executions[31] = {
        "task": FakeLiveTask(),
        "crawler_manager": object(),
        "started_at": "2026-05-22",
    }

    response = TestClient(app).get("/api/background-tasks")

    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body["tasks"]}
    assert "research-execution:20" in ids
    assert "research-execution:31" in ids
    assert body["summary"]["running"] == 2


def test_background_task_settings_updates_research_execution_concurrency():
    client = TestClient(app)

    response = client.get("/api/background-tasks/settings")

    assert response.status_code == 200
    assert response.json()["research_execution"]["max_concurrent"] == 1

    response = client.put(
        "/api/background-tasks/settings/research-execution-concurrency",
        json={"max_concurrent": 3},
    )

    assert response.status_code == 200
    assert response.json()["research_execution"]["max_concurrent"] == 3
    assert research_router._research_execution_concurrency == 3


def test_background_tasks_cancel_research_queue(monkeypatch):
    fake_repository = FakeRepository()
    monkeypatch.setattr(task_center, "ResearchRepository", lambda: fake_repository)
    research_router._research_execution_queue.append(
        {"job_id": 30, "project_id": "project-alpha", "queue_position": 1, "enqueued_at": "2026-05-22"}
    )

    response = TestClient(app).post("/api/background-tasks/research-queue:30/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert research_router._research_execution_queue == []
    assert fake_repository.updated_jobs == [(30, {"status": "cancelled"})]
    assert fake_repository.events[0]["event_type"] == "background_task_cancelled"


def test_background_tasks_lists_persisted_active_job_without_live_handle(monkeypatch):
    fake_repository = FakeRepository()
    fake_repository.jobs = [
        {
            "id": 95,
            "name": "Creator Realtime Discovery collection 2026-05-22",
            "topic": "creator_realtime_discovery",
            "platforms": ["xhs"],
            "collection_mode": "search",
            "status": "running",
            "last_scheduled_at": "2026-05-22T00:00:00Z",
            "updated_at": "2026-05-22T00:01:00Z",
        }
    ]
    monkeypatch.setattr(task_center, "ResearchRepository", lambda: fake_repository)

    response = TestClient(app).get("/api/background-tasks")

    assert response.status_code == 200
    item = response.json()["tasks"][0]
    assert item["id"] == "research-db:95"
    assert item["status"] == "running"
    assert item["source"] == "creator_search"
    assert item["cancellable"] is False
    assert "No live task handle" in item["cancel_reason"]
    assert item["deletable"] is True


def test_background_tasks_delete_persisted_active_job_marks_cancelled(monkeypatch):
    fake_repository = FakeRepository()
    fake_repository.jobs = [
        {
            "id": 95,
            "name": "Creator Realtime Discovery collection 2026-05-22",
            "topic": "creator_realtime_discovery",
            "platforms": ["xhs"],
            "collection_mode": "search",
            "status": "running",
        }
    ]

    async def get_job(job_id):
        return fake_repository.jobs[0]

    fake_repository.get_job = get_job
    monkeypatch.setattr(task_center, "ResearchRepository", lambda: fake_repository)

    response = TestClient(app).delete("/api/background-tasks/research-db:95")

    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    assert fake_repository.updated_jobs == [(95, {"status": "cancelled"})]
    assert fake_repository.events[0]["event_type"] == "background_task_deleted"


def test_background_tasks_delete_research_queue_removes_queue_and_marks_cancelled(monkeypatch):
    fake_repository = FakeRepository()
    monkeypatch.setattr(task_center, "ResearchRepository", lambda: fake_repository)
    research_router._research_execution_queue.append(
        {"job_id": 30, "project_id": "project-alpha", "queue_position": 1, "enqueued_at": "2026-05-22"}
    )

    response = TestClient(app).delete("/api/background-tasks/research-queue:30")

    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    assert research_router._research_execution_queue == []
    assert fake_repository.updated_jobs == [(30, {"status": "cancelled"})]
    assert fake_repository.events[0]["event_type"] == "background_task_deleted"


def test_background_tasks_delete_running_research_execution_requires_cancel(monkeypatch):
    fake_repository = FakeRepository()
    monkeypatch.setattr(task_center, "ResearchRepository", lambda: fake_repository)
    research_router._research_executions[20] = {
        "task": FakeLiveTask(),
        "crawler_manager": object(),
        "started_at": "2026-05-22",
    }

    response = TestClient(app).delete("/api/background-tasks/research-execution:20")

    assert response.status_code == 409
    assert "cancel" in response.json()["detail"].lower()


def test_background_tasks_delete_terminal_creator_search():
    creator_search_router.CREATOR_SEARCH_TASKS["abc123"] = {
        "task_id": "abc123",
        "status": "cancelled",
        "request": {},
        "progress": {"stage": "cancelled", "label": "Cancelled", "percent": 20},
        "result": None,
        "error": None,
        "created_at": "2026-05-22T00:00:00Z",
        "updated_at": "2026-05-22T00:01:00Z",
    }

    response = TestClient(app).delete("/api/background-tasks/creator-search:abc123")

    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    assert "abc123" not in creator_search_router.CREATOR_SEARCH_TASKS


def test_background_tasks_cancel_creator_search():
    creator_search_router.CREATOR_SEARCH_TASKS["abc123"] = {
        "task_id": "abc123",
        "status": "running",
        "request": {},
        "progress": {"stage": "database", "label": "Searching database", "percent": 20},
        "result": None,
        "error": None,
        "created_at": "2026-05-22T00:00:00Z",
        "updated_at": "2026-05-22T00:01:00Z",
    }

    response = TestClient(app).post("/api/background-tasks/creator-search:abc123/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert creator_search_router.CREATOR_SEARCH_TASKS["abc123"]["status"] == "cancelled"


def test_background_tasks_cancel_ai_analysis(monkeypatch):
    fake_repository = FakeRepository()
    monkeypatch.setattr(task_center, "ResearchRepository", lambda: fake_repository)
    fake_task = FakeLiveTask()
    research_router.AI_ANALYSIS_TASKS[42] = {
        "task": fake_task,
        "status": "running",
        "research_job_id": 7,
        "created_at": "2026-05-22T00:00:00Z",
        "updated_at": "2026-05-22T00:01:00Z",
        "message": "AI analysis running",
    }

    response = TestClient(app).post("/api/background-tasks/ai-analysis:42/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert fake_task.cancelled is True
    assert fake_repository.ai_statuses == [(42, "cancelled")]
    assert fake_repository.events[0]["event_type"] == "ai_analysis_cancelled"
