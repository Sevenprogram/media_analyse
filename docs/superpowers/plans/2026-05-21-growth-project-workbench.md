# Growth Project Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat collection task workbench with a growth-project workbench that groups existing research jobs into business-level projects and keeps job records available as drill-down diagnostics.

**Architecture:** Use a soft aggregation layer first. Existing `research_jobs`, crawler execution, scheduler, and worker code remain unchanged; a new backend aggregation module turns jobs plus per-job stats into project cards. The React workbench consumes the new endpoint, renders one project card per business project, and shows the original job list inside project detail tabs.

**Tech Stack:** FastAPI, Pydantic-style dict payloads, async repository methods, pytest, React 19, TypeScript, Vite, lucide-react, existing local UI components.

---

## File Structure

- Create `research/growth_projects.py`
  - Pure aggregation logic for project keys, sample status, recommended actions, project cards, and project detail payloads.
  - No database imports.

- Modify `research/service.py`
  - Extend the repository protocol with optional stats methods.
  - Add `list_growth_projects()` and `get_growth_project(project_id)`.

- Modify `api/routers/research.py`
  - Add `GET /api/research/growth-projects`.
  - Add `GET /api/research/growth-projects/{project_id}`.
  - Add `POST /api/research/growth-projects`.

- Modify `research/schemas.py`
  - Add `GrowthProjectCreate` request schema for the soft create flow.

- Create `tests/test_growth_projects.py`
  - Unit tests for aggregation rules.

- Modify `tests/test_research_service.py`
  - Service-level tests for project aggregation and soft creation.

- Modify `tests/test_research_api.py`
  - API tests for list, detail, and create endpoints.

- Modify `api/webui/src/types.ts`
  - Add frontend types for growth project list/detail/create payloads.

- Modify `api/webui/src/main.tsx`
  - Load growth projects.
  - Pass them into the workbench.
  - Keep existing selected job loading for data/AI tabs.

- Create `api/webui/src/pages/GrowthProjectWorkbenchPage.tsx`
  - Render project cards, detail tabs, collection records, and the create form.

- Modify `api/webui/src/pages/ResearchModulePages.tsx`
  - Remove or stop exporting the old `TaskWorkbenchPage` from active use.
  - Keep shared helpers untouched unless moved intentionally.

- Modify `api/webui/src/styles.css`
  - Add restrained workbench layout styles.

---

### Task 1: Add Pure Growth Project Aggregation

**Files:**
- Create: `research/growth_projects.py`
- Test: `tests/test_growth_projects.py`

- [ ] **Step 1: Write failing aggregation tests**

Create `tests/test_growth_projects.py` with:

```python
from research.growth_projects import build_growth_project_detail, build_growth_project_summaries


def test_groups_jobs_by_topic_and_generates_project_summary():
    jobs = [
        {
            "id": 1,
            "name": "TikHub backfill Douyin education keywords 2026-05-20",
            "topic": "education_summer_2026",
            "platforms": ["dy"],
            "keywords": ["K12 education", "summer childcare"],
            "status": "completed",
            "collection_mode": "search",
            "updated_at": "2026-05-20T14:20:00Z",
        },
        {
            "id": 2,
            "name": "TikHub backfill Xiaohongshu education keywords 2026-05-20",
            "topic": "education_summer_2026",
            "platforms": ["xhs"],
            "keywords": ["K12 education", "enrollment"],
            "status": "completed",
            "collection_mode": "search",
            "updated_at": "2026-05-20T15:00:00Z",
        },
    ]
    stats = {
        1: {"posts": 120, "comments": 0, "raw_records": 80, "authors": 15},
        2: {"posts": 24, "comments": 0, "raw_records": 20, "authors": 3},
    }

    projects = build_growth_project_summaries(jobs, stats)

    assert len(projects) == 1
    project = projects[0]
    assert project["id"] == "education_summer_2026"
    assert project["name"] == "Education Summer 2026"
    assert project["primary_goal"] == "topic_discovery"
    assert project["platforms"] == ["dy", "xhs"]
    assert project["metrics"] == {
        "jobs": 2,
        "posts": 144,
        "comments": 0,
        "raw_records": 100,
        "creators": 18,
        "failed_jobs": 0,
        "running_jobs": 0,
        "pending_jobs": 0,
    }
    assert project["sample_status"]["kind"] == "comment_insufficient"
    assert project["recommended_action"]["kind"] == "backfill_comments"
    assert project["recommended_action"]["label"] == "Backfill comments"


def test_failed_jobs_take_priority_over_ai_recommendations():
    jobs = [
        {
            "id": 3,
            "name": "Failed competitor creator crawl",
            "topic": "education_competitors",
            "platforms": ["dy"],
            "keywords": ["education"],
            "status": "failed",
            "collection_mode": "creator",
            "updated_at": "2026-05-20T12:00:00Z",
        }
    ]
    stats = {3: {"posts": 200, "comments": 50, "raw_records": 100, "authors": 20}}

    projects = build_growth_project_summaries(jobs, stats)

    assert projects[0]["sample_status"]["kind"] == "collection_issue"
    assert projects[0]["recommended_action"]["kind"] == "view_failed_jobs"
    assert projects[0]["opportunity_score"] is None


def test_detail_contains_jobs_keywords_and_status_bar():
    jobs = [
        {
            "id": 5,
            "name": "Douyin keyword search",
            "topic": "ai_tools_keyword_expansion",
            "platforms": ["dy"],
            "keywords": ["AI tools", "workflow automation"],
            "status": "completed",
            "collection_mode": "search",
            "updated_at": "2026-05-20T09:00:00Z",
        }
    ]
    stats = {5: {"posts": 80, "comments": 15, "raw_records": 70, "authors": 10}}

    detail = build_growth_project_detail("ai_tools_keyword_expansion", jobs, stats)

    assert detail["project"]["id"] == "ai_tools_keyword_expansion"
    assert detail["status_bar"]["sample_status"] == "Sample is ready for preliminary analysis"
    assert detail["keywords"] == [
        {"keyword": "AI tools", "type": "core", "source": "research_job"},
        {"keyword": "workflow automation", "type": "core", "source": "research_job"},
    ]
    assert detail["collection_records"][0]["id"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_growth_projects.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'research.growth_projects'`.

- [ ] **Step 3: Implement aggregation module**

Create `research/growth_projects.py`:

```python
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any


POST_THRESHOLD = 50
COMMENT_THRESHOLD = 20


def build_growth_project_summaries(
    jobs: list[dict[str, Any]],
    stats_by_job_id: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    stats_by_job_id = stats_by_job_id or {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for job in jobs:
        grouped[project_key_for_job(job)].append(job)

    projects = [
        _build_project_summary(project_id, project_jobs, stats_by_job_id)
        for project_id, project_jobs in grouped.items()
    ]
    return sorted(
        projects,
        key=lambda item: (item.get("last_collected_at") or "", item["name"]),
        reverse=True,
    )


def build_growth_project_detail(
    project_id: str,
    jobs: list[dict[str, Any]],
    stats_by_job_id: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    stats_by_job_id = stats_by_job_id or {}
    project_jobs = [job for job in jobs if project_key_for_job(job) == project_id]
    if not project_jobs:
        return None
    project = _build_project_summary(project_id, project_jobs, stats_by_job_id)
    keywords = _keyword_assets(project_jobs)
    return {
        "project": project,
        "status_bar": {
            "recommended_action": project["recommended_action"]["label"],
            "sample_status": project["sample_status"]["label"],
            "opportunity_score": project["opportunity_score"],
        },
        "overview": {
            "current_judgment": _current_judgment(project),
            "recommended_actions": _recommended_actions(project),
            "sample_status": project["sample_status"],
            "collection_health": project["metrics"],
        },
        "ai_insights": {
            "summary": "AI insight has not been generated for this aggregated project.",
            "missing_data": _missing_data(project),
        },
        "sample_data": {
            "posts": project["metrics"]["posts"],
            "comments": project["metrics"]["comments"],
            "creators": project["metrics"]["creators"],
            "raw_records": project["metrics"]["raw_records"],
        },
        "keywords": keywords,
        "collection_records": [_collection_record(job, stats_by_job_id) for job in project_jobs],
        "settings": {
            "primary_goal": project["primary_goal"],
            "platforms": project["platforms"],
            "refresh_cadence": "off",
        },
    }


def project_key_for_job(job: dict[str, Any]) -> str:
    explicit = job.get("project_key") or job.get("growth_project_id")
    if explicit:
        return _slug(str(explicit))
    topic = str(job.get("topic") or "").strip()
    if topic:
        return _slug(topic)
    name = str(job.get("name") or f"job-{job.get('id', 'unclassified')}")
    return _slug(name)


def _build_project_summary(
    project_id: str,
    jobs: list[dict[str, Any]],
    stats_by_job_id: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    metrics = _metrics(jobs, stats_by_job_id)
    sample_status = _sample_status(metrics)
    recommended_action = _recommended_action(sample_status["kind"])
    platforms = sorted({platform for job in jobs for platform in job.get("platforms", [])})
    return {
        "id": project_id,
        "name": _title_from_project_id(project_id),
        "primary_goal": _primary_goal(project_id, jobs),
        "platforms": platforms,
        "status": sample_status["project_state"],
        "sample_status": sample_status,
        "recommended_action": recommended_action,
        "opportunity_score": _opportunity_score(sample_status["kind"], metrics),
        "last_collected_at": _last_collected_at(jobs),
        "metrics": metrics,
        "job_ids": [job["id"] for job in jobs if "id" in job],
    }


def _metrics(jobs: list[dict[str, Any]], stats_by_job_id: dict[int, dict[str, Any]]) -> dict[str, int]:
    totals = {
        "jobs": len(jobs),
        "posts": 0,
        "comments": 0,
        "raw_records": 0,
        "creators": 0,
        "failed_jobs": 0,
        "running_jobs": 0,
        "pending_jobs": 0,
    }
    for job in jobs:
        status = str(job.get("status") or "")
        if status in {"failed", "error"}:
            totals["failed_jobs"] += 1
        if status == "running":
            totals["running_jobs"] += 1
        if status in {"pending", "queued"}:
            totals["pending_jobs"] += 1
        stats = stats_by_job_id.get(int(job["id"]), {}) if job.get("id") is not None else {}
        totals["posts"] += _int(stats.get("posts"))
        totals["comments"] += _int(stats.get("comments"))
        totals["raw_records"] += _int(stats.get("raw_records"))
        totals["creators"] += _int(stats.get("authors") or stats.get("creators"))
    return totals


def _sample_status(metrics: dict[str, int]) -> dict[str, str]:
    if metrics["failed_jobs"]:
        return {
            "kind": "collection_issue",
            "label": "Collection issue needs attention",
            "project_state": "collection_issue",
        }
    if metrics["running_jobs"] or metrics["pending_jobs"]:
        return {
            "kind": "collecting",
            "label": "Collection is still running",
            "project_state": "collecting",
        }
    if metrics["posts"] < POST_THRESHOLD:
        return {
            "kind": "sample_insufficient",
            "label": "Post sample is insufficient",
            "project_state": "sample_insufficient",
        }
    if metrics["comments"] < COMMENT_THRESHOLD:
        return {
            "kind": "comment_insufficient",
            "label": "Posts sufficient, comments insufficient",
            "project_state": "preliminarily_analyzable",
        }
    return {
        "kind": "ready_for_insight",
        "label": "Sample is ready for preliminary analysis",
        "project_state": "deeply_analyzable",
    }


def _recommended_action(kind: str) -> dict[str, str]:
    actions = {
        "collection_issue": {"kind": "view_failed_jobs", "label": "View failed jobs"},
        "collecting": {"kind": "wait_for_collection", "label": "Wait for collection"},
        "sample_insufficient": {"kind": "backfill_posts", "label": "Backfill posts"},
        "comment_insufficient": {"kind": "backfill_comments", "label": "Backfill comments"},
        "ready_for_insight": {"kind": "generate_insight", "label": "Generate insight"},
    }
    return actions[kind]


def _opportunity_score(kind: str, metrics: dict[str, int]) -> int | None:
    if kind in {"collection_issue", "collecting", "sample_insufficient"}:
        return None
    base = min(80, 40 + metrics["posts"] // 5 + metrics["comments"] // 10)
    return max(0, min(100, base))


def _primary_goal(project_id: str, jobs: list[dict[str, Any]]) -> str:
    text = " ".join([project_id, *[str(job.get("name") or "") for job in jobs]]).lower()
    if "creator" in text or "达人" in text:
        return "creator_discovery"
    if "competitor" in text or "竞品" in text:
        return "competitor_monitoring"
    if "expansion" in text or "keyword" in text or "扩" in text:
        return "keyword_expansion"
    return "topic_discovery"


def _last_collected_at(jobs: list[dict[str, Any]]) -> str | None:
    values = [
        str(job.get("last_scheduled_at") or job.get("updated_at") or job.get("created_at") or "")
        for job in jobs
    ]
    values = [value for value in values if value]
    return max(values) if values else None


def _keyword_assets(jobs: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    assets: list[dict[str, str]] = []
    for job in jobs:
        for keyword in job.get("keywords") or []:
            item = str(keyword).strip()
            if item and item not in seen:
                seen.add(item)
                assets.append({"keyword": item, "type": "core", "source": "research_job"})
    return assets


def _collection_record(
    job: dict[str, Any],
    stats_by_job_id: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    stats = stats_by_job_id.get(int(job["id"]), {}) if job.get("id") is not None else {}
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "platforms": job.get("platforms") or [],
        "collection_mode": job.get("collection_mode") or "search",
        "keywords": job.get("keywords") or [],
        "status": job.get("status") or "unknown",
        "posts": _int(stats.get("posts")),
        "comments": _int(stats.get("comments")),
        "raw_records": _int(stats.get("raw_records")),
        "updated_at": job.get("updated_at"),
    }


def _current_judgment(project: dict[str, Any]) -> str:
    kind = project["sample_status"]["kind"]
    if kind == "collection_issue":
        return "Collection has issues. Review failed jobs before making a business decision."
    if kind == "comment_insufficient":
        return "Post samples are usable, but comments are insufficient for strong topic judgment."
    if kind == "ready_for_insight":
        return "Samples are ready for insight generation."
    if kind == "sample_insufficient":
        return "The project needs more post samples before analysis."
    return "Collection is in progress."


def _recommended_actions(project: dict[str, Any]) -> list[dict[str, str]]:
    primary = project["recommended_action"]
    if primary["kind"] == "backfill_comments":
        return [primary, {"kind": "generate_insight", "label": "Generate preliminary insight"}]
    return [primary]


def _missing_data(project: dict[str, Any]) -> list[str]:
    missing = []
    if project["metrics"]["posts"] < POST_THRESHOLD:
        missing.append("post samples")
    if project["metrics"]["comments"] < COMMENT_THRESHOLD:
        missing.append("comment samples")
    return missing


def _title_from_project_id(project_id: str) -> str:
    return project_id.replace("-", " ").replace("_", " ").title()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", value.strip().lower())
    return slug.strip("_") or "unclassified_collection_records"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
```

- [ ] **Step 4: Run aggregation tests**

Run:

```bash
pytest tests/test_growth_projects.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add research/growth_projects.py tests/test_growth_projects.py
git commit -m "feat: aggregate research jobs into growth projects"
```

---

### Task 2: Expose Growth Project APIs

**Files:**
- Modify: `research/service.py`
- Modify: `research/schemas.py`
- Modify: `api/routers/research.py`
- Test: `tests/test_research_service.py`
- Test: `tests/test_research_api.py`

- [ ] **Step 1: Add failing service tests**

Append to `tests/test_research_service.py`:

```python
@pytest.mark.asyncio
async def test_service_lists_growth_projects_from_existing_jobs():
    class ProjectRepository(FakeResearchRepository):
        async def list_jobs(self):
            return [
                {
                    "id": 1,
                    "name": "Education keyword expansion",
                    "topic": "education_summer_2026",
                    "platforms": ["dy"],
                    "keywords": ["K12 education"],
                    "status": "completed",
                    "collection_mode": "search",
                    "updated_at": "2026-05-20T14:00:00Z",
                }
            ]

        async def get_job_stats(self, job_id):
            return {"posts": 60, "comments": 0, "raw_records": 50, "authors": 5}

    service = ResearchJobService(ProjectRepository())

    projects = await service.list_growth_projects()

    assert projects[0]["id"] == "education_summer_2026"
    assert projects[0]["recommended_action"]["kind"] == "backfill_comments"


@pytest.mark.asyncio
async def test_service_gets_growth_project_detail():
    class ProjectRepository(FakeResearchRepository):
        async def list_jobs(self):
            return [
                {
                    "id": 2,
                    "name": "AI tools keyword expansion",
                    "topic": "ai_tools",
                    "platforms": ["dy"],
                    "keywords": ["AI tools"],
                    "status": "completed",
                    "collection_mode": "search",
                    "updated_at": "2026-05-20T14:00:00Z",
                }
            ]

        async def get_job_stats(self, job_id):
            return {"posts": 80, "comments": 25, "raw_records": 70, "authors": 8}

    service = ResearchJobService(ProjectRepository())

    detail = await service.get_growth_project("ai_tools")

    assert detail is not None
    assert detail["project"]["id"] == "ai_tools"
    assert detail["collection_records"][0]["id"] == 2
```

- [ ] **Step 2: Run service tests to verify they fail**

Run:

```bash
pytest tests/test_research_service.py::test_service_lists_growth_projects_from_existing_jobs tests/test_research_service.py::test_service_gets_growth_project_detail -v
```

Expected: FAIL with `AttributeError: 'ResearchJobService' object has no attribute 'list_growth_projects'`.

- [ ] **Step 3: Extend `research/service.py`**

Add imports near the top:

```python
from research.growth_projects import (
    build_growth_project_detail,
    build_growth_project_summaries,
)
```

Add to `JobRepository`:

```python
    async def get_job_stats(self, job_id: int) -> dict[str, Any]:
        ...
```

Add methods to `ResearchJobService`:

```python
    async def list_growth_projects(self) -> list[dict[str, Any]]:
        jobs = await self.repository.list_jobs()
        stats = await self._stats_by_job_id(jobs)
        return build_growth_project_summaries(jobs, stats)

    async def get_growth_project(self, project_id: str) -> dict[str, Any] | None:
        jobs = await self.repository.list_jobs()
        stats = await self._stats_by_job_id(jobs)
        return build_growth_project_detail(project_id, jobs, stats)

    async def _stats_by_job_id(self, jobs: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        stats: dict[int, dict[str, Any]] = {}
        getter = getattr(self.repository, "get_job_stats", None)
        if getter is None:
            return stats
        for job in jobs:
            job_id = job.get("id")
            if job_id is None:
                continue
            stats[int(job_id)] = await getter(int(job_id))
        return stats
```

- [ ] **Step 4: Run service tests**

Run:

```bash
pytest tests/test_research_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Add create schema**

In `research/schemas.py`, add this model near `ResearchJobCreate`:

```python
class GrowthProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    primary_goal: Literal[
        "topic_discovery",
        "creator_discovery",
        "keyword_expansion",
        "competitor_monitoring",
        "mixed_research",
    ] = "topic_discovery"
    platforms: list[str] = Field(default_factory=list, min_length=1)
    keywords: list[str] = Field(default_factory=list, min_length=1)
    collection_depth: Literal["lightweight", "standard", "deep"] = "standard"
    refresh_cadence: Literal["off", "daily", "three_days", "weekly"] = "off"
    auto_ai_analysis: bool = True
```

- [ ] **Step 6: Add failing API tests**

Append to `tests/test_research_api.py`:

```python
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
                    "sample_status": {"kind": "comment_insufficient", "label": "Posts sufficient, comments insufficient"},
                    "recommended_action": {"kind": "backfill_comments", "label": "Backfill comments"},
                    "opportunity_score": 70,
                    "last_collected_at": "2026-05-20T14:00:00Z",
                    "metrics": {"jobs": 1, "posts": 60, "comments": 0, "raw_records": 50, "creators": 5, "failed_jobs": 0, "running_jobs": 0, "pending_jobs": 0},
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
```

- [ ] **Step 7: Add API routes**

In `api/routers/research.py`, import the schema:

```python
from research.schemas import GrowthProjectCreate
```

If the file already imports many schema names in a parenthesized import, add `GrowthProjectCreate` to that existing import block instead of creating a duplicate import.

Add routes before `@router.get("/jobs/{job_id}")` so `growth-projects` is not captured by the job id route:

```python
@router.get("/growth-projects")
async def list_growth_projects():
    require_research_database()
    service = get_service()
    return {"projects": await service.list_growth_projects()}


@router.get("/growth-projects/{project_id}")
async def get_growth_project(project_id: str):
    require_research_database()
    service = get_service()
    project = await service.get_growth_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Growth project not found")
    return project
```

- [ ] **Step 8: Run API tests**

Run:

```bash
pytest tests/test_research_api.py::test_growth_projects_route_lists_aggregated_projects tests/test_research_api.py::test_growth_project_detail_route_returns_404_for_unknown_project -v
```

Expected: PASS.

- [ ] **Step 9: Add soft create route test**

Append to `tests/test_research_api.py`:

```python
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
```

- [ ] **Step 10: Implement soft create route**

In `api/routers/research.py`, add imports if missing:

```python
from datetime import date
```

Add this helper near the growth project routes:

```python
def _project_slug(value: str) -> str:
    return "_".join(part for part in value.lower().replace("-", " ").split() if part)
```

Add route after `list_growth_projects`:

```python
@router.post("/growth-projects")
async def create_growth_project(request: GrowthProjectCreate):
    require_research_database()
    service = get_service()
    project_id = _project_slug(request.name)
    enable_comments = request.collection_depth in {"standard", "deep"}
    job = await service.create_job(
        ResearchJobCreate(
            name=f"{request.name} initial collection",
            topic=project_id,
            platforms=request.platforms,
            keywords=request.keywords,
            start_date=date.today(),
            end_date=date.today(),
            collection_mode="search",
            comment_policy=CommentPolicy(
                enable_comments=enable_comments,
                comment_limit_per_post=100 if enable_comments else 0,
                enable_sub_comments=request.collection_depth == "deep",
                sub_comment_limit_per_comment=20 if request.collection_depth == "deep" else 0,
                full_comment_crawl=False,
            ),
            schedule_enabled=request.refresh_cadence != "off",
            schedule_interval_minutes={
                "daily": 1440,
                "three_days": 4320,
                "weekly": 10080,
            }.get(request.refresh_cadence),
        )
    )
    return {"project_id": project_id, "job": job}
```

Use the existing `CommentPolicy` and `ResearchJobCreate` imports. If they are not imported in `api/routers/research.py`, add them to the existing schemas import block.

- [ ] **Step 11: Run route tests**

Run:

```bash
pytest tests/test_research_api.py::test_growth_projects_route_lists_aggregated_projects tests/test_research_api.py::test_growth_project_detail_route_returns_404_for_unknown_project tests/test_research_api.py::test_create_growth_project_creates_initial_research_job -v
```

Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add research/service.py research/schemas.py api/routers/research.py tests/test_research_service.py tests/test_research_api.py
git commit -m "feat: expose growth project research APIs"
```

---

### Task 3: Add Frontend Types And Data Loading

**Files:**
- Modify: `api/webui/src/types.ts`
- Modify: `api/webui/src/main.tsx`

- [ ] **Step 1: Add frontend types**

Append to `api/webui/src/types.ts` before `export type ResearchTab`:

```typescript
export type GrowthProjectAction = {
  kind: string;
  label: string;
};

export type GrowthProjectSampleStatus = {
  kind: string;
  label: string;
  project_state?: string;
};

export type GrowthProjectMetrics = {
  jobs: number;
  posts: number;
  comments: number;
  raw_records: number;
  creators: number;
  failed_jobs: number;
  running_jobs: number;
  pending_jobs: number;
};

export type GrowthProjectSummary = {
  id: string;
  name: string;
  primary_goal: "topic_discovery" | "creator_discovery" | "keyword_expansion" | "competitor_monitoring" | "mixed_research";
  platforms: string[];
  status: string;
  sample_status: GrowthProjectSampleStatus;
  recommended_action: GrowthProjectAction;
  opportunity_score: number | null;
  last_collected_at?: string | null;
  metrics: GrowthProjectMetrics;
  job_ids: number[];
};

export type GrowthProjectDetail = {
  project: GrowthProjectSummary;
  status_bar: {
    recommended_action: string;
    sample_status: string;
    opportunity_score: number | null;
  };
  overview: {
    current_judgment: string;
    recommended_actions: GrowthProjectAction[];
    sample_status: GrowthProjectSampleStatus;
    collection_health: GrowthProjectMetrics;
  };
  ai_insights: {
    summary: string;
    missing_data: string[];
  };
  sample_data: {
    posts: number;
    comments: number;
    creators: number;
    raw_records: number;
  };
  keywords: Array<{ keyword: string; type: string; source: string }>;
  collection_records: Array<{
    id: number;
    name: string;
    platforms: string[];
    collection_mode: string;
    keywords: string[];
    status: string;
    posts: number;
    comments: number;
    raw_records: number;
    updated_at?: string | null;
  }>;
  settings: {
    primary_goal: string;
    platforms: string[];
    refresh_cadence: string;
  };
};

export type GrowthProjectCreatePayload = {
  name: string;
  primary_goal: GrowthProjectSummary["primary_goal"];
  platforms: string[];
  keywords: string[];
  collection_depth: "lightweight" | "standard" | "deep";
  refresh_cadence: "off" | "daily" | "three_days" | "weekly";
  auto_ai_analysis: boolean;
};
```

- [ ] **Step 2: Wire `main.tsx` state and loader**

In `api/webui/src/main.tsx`, add imports:

```typescript
  GrowthProjectCreatePayload,
  GrowthProjectDetail,
  GrowthProjectSummary,
```

Add state inside `App()`:

```typescript
  const [growthProjects, setGrowthProjects] = React.useState<GrowthProjectSummary[]>([]);
  const [selectedProjectId, setSelectedProjectId] = React.useState<string | null>(null);
  const [selectedProjectDetail, setSelectedProjectDetail] = React.useState<GrowthProjectDetail | null>(null);
```

Add loaders:

```typescript
  const loadGrowthProjects = React.useCallback(async () => {
    const data = await api<{ projects: GrowthProjectSummary[] }>("/api/research/growth-projects");
    const projects = data.projects || [];
    setGrowthProjects(projects);
    setSelectedProjectId((current) => current ?? projects[0]?.id ?? null);
  }, []);

  const loadSelectedProject = React.useCallback(async (projectId: string | null) => {
    if (!projectId) {
      setSelectedProjectDetail(null);
      return;
    }
    const detail = await api<GrowthProjectDetail>(`/api/research/growth-projects/${projectId}`);
    setSelectedProjectDetail(detail);
  }, []);

  async function createGrowthProject(payload: GrowthProjectCreatePayload) {
    const result = await api<{ project_id: string; job: ResearchJob }>("/api/research/growth-projects", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await Promise.allSettled([loadJobs(), loadGrowthProjects()]);
    setSelectedProjectId(result.project_id);
  }
```

Update `refreshAll` to include `loadGrowthProjects()`:

```typescript
      await Promise.allSettled([loadDashboardSummary(), loadJobs(), loadGrowthProjects(), loadDatabaseStats(), loadAiOverview()]);
```

Add `loadGrowthProjects` to the `refreshAll` dependency array.

Add effect:

```typescript
  React.useEffect(() => { void loadSelectedProject(selectedProjectId); }, [loadSelectedProject, selectedProjectId]);
```

- [ ] **Step 3: Run TypeScript to catch missing imports**

Run:

```bash
npm.cmd run build
```

Expected: FAIL because `createGrowthProject`, `growthProjects`, and project detail state are not passed into a page yet or because `GrowthProjectWorkbenchPage` does not exist.

- [ ] **Step 4: Leave the failing build for Task 4**

Do not commit after this task if the build fails due to the missing page. Commit after Task 4 when the frontend compiles.

---

### Task 4: Build Growth Project Workbench Page

**Files:**
- Create: `api/webui/src/pages/GrowthProjectWorkbenchPage.tsx`
- Modify: `api/webui/src/main.tsx`
- Modify: `api/webui/src/pages/ResearchModulePages.tsx`

- [ ] **Step 1: Create the page component**

Create `api/webui/src/pages/GrowthProjectWorkbenchPage.tsx`:

```typescript
import React from "react";
import { Activity, Bot, Database, FileJson, Plus, RefreshCw, Search, Settings } from "lucide-react";
import { Badge, Button, Card, CardDescription, CardHeader, CardTitle, Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui";
import { formatDateTime, formatNumber, labelPlatform } from "../utils/format";
import type { GrowthProjectCreatePayload, GrowthProjectDetail, GrowthProjectSummary } from "../types";

const GOAL_LABELS: Record<GrowthProjectSummary["primary_goal"], string> = {
  topic_discovery: "找选题",
  creator_discovery: "找达人",
  keyword_expansion: "扩关键词",
  competitor_monitoring: "盯竞品",
  mixed_research: "综合研究",
};

const ACTION_LABELS: Record<string, string> = {
  view_failed_jobs: "查看失败任务",
  wait_for_collection: "等待采集完成",
  backfill_posts: "补抓帖子",
  backfill_comments: "补抓评论",
  generate_insight: "生成洞察",
};

export function GrowthProjectWorkbenchPage({
  projects,
  selectedProjectId,
  selectedProjectDetail,
  onSelectProject,
  onCreateProject,
  onOpenData,
  onOpenAi,
}: {
  projects: GrowthProjectSummary[];
  selectedProjectId: string | null;
  selectedProjectDetail: GrowthProjectDetail | null;
  onSelectProject: (id: string) => void;
  onCreateProject: (payload: GrowthProjectCreatePayload) => Promise<void>;
  onOpenData: () => void;
  onOpenAi: () => void;
}) {
  const [showCreate, setShowCreate] = React.useState(false);
  const selected = projects.find((project) => project.id === selectedProjectId) || projects[0] || null;

  return (
    <section className="module-page growth-workbench">
      <div className="module-hero">
        <div className="module-hero-icon"><Activity size={30} /></div>
        <div>
          <span>Growth Projects</span>
          <h1>增长项目</h1>
          <p>按业务项目聚合关键词、样本、洞察和采集记录；先看下一步动作，再下钻任务细节。</p>
        </div>
        <Button variant="primary" onClick={() => setShowCreate((value) => !value)}><Plus size={16} />新建增长项目</Button>
      </div>

      {showCreate && <GrowthProjectCreateForm onCreate={onCreateProject} onClose={() => setShowCreate(false)} />}

      <div className="growth-project-layout">
        <div className="growth-project-list">
          {projects.length ? (
            projects.map((project) => (
              <GrowthProjectCard
                key={project.id}
                project={project}
                active={project.id === selected?.id}
                onClick={() => onSelectProject(project.id)}
              />
            ))
          ) : (
            <Card className="empty-state">
              <CardTitle>暂无增长项目</CardTitle>
              <CardDescription>创建项目后，系统会把采集任务、样本和洞察聚合到这里。</CardDescription>
            </Card>
          )}
        </div>

        <ProjectDetailPanel detail={selectedProjectDetail} selected={selected} onOpenData={onOpenData} onOpenAi={onOpenAi} />
      </div>
    </section>
  );
}

function GrowthProjectCard({ project, active, onClick }: { project: GrowthProjectSummary; active: boolean; onClick: () => void }) {
  const actionLabel = ACTION_LABELS[project.recommended_action.kind] || project.recommended_action.label;
  return (
    <Card className={`growth-project-card ${active ? "active" : ""}`} onClick={onClick}>
      <div className="growth-project-card-head">
        <div>
          <h2>{project.name}</h2>
          <p>{GOAL_LABELS[project.primary_goal]} · {project.platforms.map(labelPlatform).join(" / ") || "未设置平台"} · {project.last_collected_at ? formatDateTime(project.last_collected_at) : "未采集"}</p>
        </div>
        <Badge tone={project.metrics.failed_jobs ? "danger" : project.opportunity_score ? "success" : "warning"}>
          {project.opportunity_score === null ? "待判断" : `${project.opportunity_score} 分`}
        </Badge>
      </div>
      <div className="growth-project-action">
        <span>建议动作</span>
        <strong>{actionLabel}</strong>
      </div>
      <p className="growth-project-sample">{project.sample_status.label}</p>
      <div className="growth-project-metrics">
        <span>{formatNumber(project.metrics.posts)} 帖子</span>
        <span>{formatNumber(project.metrics.comments)} 评论</span>
        <span>{formatNumber(project.metrics.creators)} 达人</span>
        <span>{formatNumber(project.metrics.raw_records)} Raw</span>
        {project.metrics.failed_jobs > 0 && <span className="danger">{project.metrics.failed_jobs} 失败</span>}
      </div>
    </Card>
  );
}

function ProjectDetailPanel({
  detail,
  selected,
  onOpenData,
  onOpenAi,
}: {
  detail: GrowthProjectDetail | null;
  selected: GrowthProjectSummary | null;
  onOpenData: () => void;
  onOpenAi: () => void;
}) {
  if (!selected) {
    return (
      <Card className="growth-project-detail">
        <CardTitle>选择一个增长项目</CardTitle>
        <CardDescription>项目详情会展示概览、AI 洞察、样本、关键词和采集记录。</CardDescription>
      </Card>
    );
  }

  const project = detail?.project || selected;
  return (
    <Card className="growth-project-detail">
      <div className="project-status-bar">
        <div><span>建议动作</span><strong>{ACTION_LABELS[project.recommended_action.kind] || project.recommended_action.label}</strong></div>
        <div><span>样本状态</span><strong>{project.sample_status.label}</strong></div>
        <div><span>机会评分</span><strong>{project.opportunity_score ?? "待分析"}</strong></div>
      </div>

      <Tabs defaultValue="overview" className="project-tabs">
        <TabsList className="project-tab-list">
          <TabsTrigger value="overview">概览</TabsTrigger>
          <TabsTrigger value="ai">AI洞察</TabsTrigger>
          <TabsTrigger value="samples">样本数据</TabsTrigger>
          <TabsTrigger value="keywords">关键词团</TabsTrigger>
          <TabsTrigger value="records">采集记录</TabsTrigger>
          <TabsTrigger value="settings">设置</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="project-tab-content">
          <CardHeader>
            <div>
              <CardTitle>{project.name}</CardTitle>
              <CardDescription>{detail?.overview.current_judgment || "正在加载项目判断。"}</CardDescription>
            </div>
          </CardHeader>
          <div className="project-overview-grid">
            <Metric label="帖子" value={project.metrics.posts} icon={<FileJson size={16} />} />
            <Metric label="评论" value={project.metrics.comments} icon={<FileJson size={16} />} />
            <Metric label="达人" value={project.metrics.creators} icon={<Search size={16} />} />
            <Metric label="失败任务" value={project.metrics.failed_jobs} icon={<Activity size={16} />} />
          </div>
          <div className="result-actions">
            <Button variant="primary" onClick={onOpenAi}><Bot size={16} />生成洞察</Button>
            <Button variant="ghost" onClick={onOpenData}><Database size={16} />查看样本</Button>
          </div>
        </TabsContent>

        <TabsContent value="ai" className="project-tab-content">
          <CardTitle>AI 洞察</CardTitle>
          <p>{detail?.ai_insights.summary || "还没有聚合洞察。"}</p>
          {!!detail?.ai_insights.missing_data.length && <p>缺少数据：{detail.ai_insights.missing_data.join("、")}</p>}
        </TabsContent>

        <TabsContent value="samples" className="project-tab-content">
          <div className="project-overview-grid">
            <Metric label="帖子" value={detail?.sample_data.posts ?? project.metrics.posts} icon={<FileJson size={16} />} />
            <Metric label="评论" value={detail?.sample_data.comments ?? project.metrics.comments} icon={<FileJson size={16} />} />
            <Metric label="达人" value={detail?.sample_data.creators ?? project.metrics.creators} icon={<Search size={16} />} />
            <Metric label="Raw" value={detail?.sample_data.raw_records ?? project.metrics.raw_records} icon={<Database size={16} />} />
          </div>
        </TabsContent>

        <TabsContent value="keywords" className="project-tab-content">
          <div className="keyword-chip-list">
            {(detail?.keywords || []).map((item) => <Badge key={item.keyword} tone="muted">{item.keyword}</Badge>)}
            {!detail?.keywords.length && <CardDescription>暂无关键词资产。</CardDescription>}
          </div>
        </TabsContent>

        <TabsContent value="records" className="project-tab-content">
          <div className="collection-record-list">
            {(detail?.collection_records || []).map((record) => (
              <div className="collection-record-row" key={record.id}>
                <div>
                  <strong>{record.name}</strong>
                  <span>{record.platforms.map(labelPlatform).join(" / ")} · {record.collection_mode}</span>
                </div>
                <span>{record.status}</span>
                <span>{record.posts} 帖子</span>
                <span>{record.comments} 评论</span>
                <span>{record.raw_records} Raw</span>
              </div>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="settings" className="project-tab-content">
          <p><Settings size={16} /> 主目标：{GOAL_LABELS[project.primary_goal]}</p>
          <p>平台：{project.platforms.map(labelPlatform).join(" / ") || "未设置"}</p>
        </TabsContent>
      </Tabs>
    </Card>
  );
}

function Metric({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  return (
    <div className="project-mini-metric">
      {icon}
      <span>{label}</span>
      <strong>{formatNumber(value)}</strong>
    </div>
  );
}

function GrowthProjectCreateForm({
  onCreate,
  onClose,
}: {
  onCreate: (payload: GrowthProjectCreatePayload) => Promise<void>;
  onClose: () => void;
}) {
  const [name, setName] = React.useState("");
  const [primaryGoal, setPrimaryGoal] = React.useState<GrowthProjectCreatePayload["primary_goal"]>("topic_discovery");
  const [platforms, setPlatforms] = React.useState("dy,xhs");
  const [keywords, setKeywords] = React.useState("");
  const [collectionDepth, setCollectionDepth] = React.useState<GrowthProjectCreatePayload["collection_depth"]>("standard");
  const [refreshCadence, setRefreshCadence] = React.useState<GrowthProjectCreatePayload["refresh_cadence"]>("off");
  const [submitting, setSubmitting] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await onCreate({
        name,
        primary_goal: primaryGoal,
        platforms: splitValues(platforms),
        keywords: splitValues(keywords),
        collection_depth: collectionDepth,
        refresh_cadence: refreshCadence,
        auto_ai_analysis: true,
      });
      onClose();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="growth-project-create">
      <form onSubmit={submit}>
        <CardHeader>
          <div>
            <CardTitle>新建增长项目</CardTitle>
            <CardDescription>填写业务目标，系统会生成第一批采集任务。</CardDescription>
          </div>
        </CardHeader>
        <div className="form-grid">
          <label>项目名<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
          <label>主目标<select value={primaryGoal} onChange={(event) => setPrimaryGoal(event.target.value as GrowthProjectCreatePayload["primary_goal"])}>
            <option value="topic_discovery">找选题</option>
            <option value="creator_discovery">找达人</option>
            <option value="keyword_expansion">扩关键词</option>
            <option value="competitor_monitoring">盯竞品</option>
            <option value="mixed_research">综合研究</option>
          </select></label>
          <label>平台<input value={platforms} onChange={(event) => setPlatforms(event.target.value)} /></label>
          <label>采集深度<select value={collectionDepth} onChange={(event) => setCollectionDepth(event.target.value as GrowthProjectCreatePayload["collection_depth"])}>
            <option value="lightweight">轻量：只抓帖子</option>
            <option value="standard">标准：帖子 + 基础评论</option>
            <option value="deep">深度：帖子 + 评论 + 达人主页</option>
          </select></label>
          <label>刷新周期<select value={refreshCadence} onChange={(event) => setRefreshCadence(event.target.value as GrowthProjectCreatePayload["refresh_cadence"])}>
            <option value="off">不开启</option>
            <option value="daily">每天</option>
            <option value="three_days">每 3 天</option>
            <option value="weekly">每周</option>
          </select></label>
          <label className="full">初始关键词<textarea value={keywords} onChange={(event) => setKeywords(event.target.value)} rows={4} required /></label>
        </div>
        <div className="collection-plan-preview">
          <strong>将创建</strong>
          <span>{splitValues(platforms).map(labelPlatform).join(" / ") || "所选平台"} 关键词搜索任务</span>
          <span>{collectionDepth !== "lightweight" ? "评论补抓任务" : "仅采集帖子"}</span>
          <span>项目概览和后续 AI 洞察入口</span>
        </div>
        <div className="result-actions">
          <Button type="button" variant="ghost" onClick={onClose}>取消</Button>
          <Button type="submit" variant="primary" disabled={submitting}><RefreshCw size={16} />创建项目</Button>
        </div>
      </form>
    </Card>
  );
}

function splitValues(value: string) {
  return value.split(/[\n,，/]+/).map((item) => item.trim()).filter(Boolean);
}
```

- [ ] **Step 2: Use the new page in `main.tsx`**

Replace the `TaskWorkbenchPage` import with:

```typescript
import { GrowthProjectWorkbenchPage } from "./pages/GrowthProjectWorkbenchPage";
```

Remove `TaskWorkbenchPage` from the destructured import from `ResearchModulePages`.

Replace the `tab === "tasks"` block with:

```tsx
        {tab === "tasks" && (
          <GrowthProjectWorkbenchPage
            projects={growthProjects}
            selectedProjectId={selectedProjectId}
            selectedProjectDetail={selectedProjectDetail}
            onSelectProject={setSelectedProjectId}
            onCreateProject={createGrowthProject}
            onOpenData={() => setTab("data")}
            onOpenAi={() => setTab("ai")}
          />
        )}
```

- [ ] **Step 3: Stop exporting old active workbench**

In `api/webui/src/pages/ResearchModulePages.tsx`, leave `TaskWorkbenchPage` in place if other code still imports it during the transition. If TypeScript reports an unused export is acceptable, do not delete it. If lint rules require cleanup during this implementation, remove the old component in a separate commit after the new page ships.

- [ ] **Step 4: Run frontend build**

Run:

```bash
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/webui/src/types.ts api/webui/src/main.tsx api/webui/src/pages/GrowthProjectWorkbenchPage.tsx
git commit -m "feat: add growth project workbench UI"
```

---

### Task 5: Add Workbench Styling And Responsive Polish

**Files:**
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Add styles**

Append to `api/webui/src/styles.css`:

```css
.growth-workbench .module-hero {
  align-items: center;
}

.growth-workbench .module-hero > button {
  margin-left: auto;
}

.growth-project-layout {
  display: grid;
  grid-template-columns: minmax(320px, 0.95fr) minmax(0, 1.55fr);
  gap: 16px;
  align-items: start;
}

.growth-project-list {
  display: grid;
  gap: 12px;
}

.growth-project-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  cursor: pointer;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.growth-project-card:hover,
.growth-project-card.active {
  border-color: var(--accent);
  box-shadow: 0 12px 30px rgba(18, 28, 25, 0.08);
}

.growth-project-card.active {
  background: #f1fbf8;
}

.growth-project-card-head {
  display: flex;
  gap: 12px;
  align-items: start;
  justify-content: space-between;
}

.growth-project-card h2 {
  margin: 0 0 4px;
  font-size: 17px;
  line-height: 1.35;
}

.growth-project-card p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.45;
}

.growth-project-action {
  display: grid;
  gap: 3px;
  padding: 10px 12px;
  border: 1px solid var(--line-soft);
  border-radius: 7px;
  background: var(--panel-soft);
}

.growth-project-action span,
.project-status-bar span {
  color: var(--muted);
  font-size: 12px;
}

.growth-project-action strong,
.project-status-bar strong {
  font-size: 15px;
}

.growth-project-sample {
  color: var(--text);
}

.growth-project-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  color: var(--muted);
  font-size: 12px;
}

.growth-project-metrics span {
  padding: 4px 7px;
  border-radius: 999px;
  background: var(--panel-soft);
}

.growth-project-metrics .danger {
  color: var(--danger);
  background: var(--danger-soft);
}

.growth-project-detail {
  display: grid;
  gap: 14px;
  padding: 14px;
}

.project-status-bar {
  display: grid;
  grid-template-columns: 1.4fr 1.4fr 0.7fr;
  gap: 10px;
}

.project-status-bar > div {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--line-soft);
  border-radius: 7px;
  background: var(--panel-soft);
}

.project-tabs {
  display: grid;
  gap: 14px;
}

.project-tab-list {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.project-tab-list button {
  min-height: 32px;
}

.project-tab-content {
  display: grid;
  gap: 14px;
}

.project-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.project-mini-metric {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--line-soft);
  border-radius: 7px;
  background: var(--panel-soft);
}

.project-mini-metric span {
  color: var(--muted);
  font-size: 12px;
}

.project-mini-metric strong {
  font-size: 20px;
}

.keyword-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.collection-record-list {
  display: grid;
  gap: 8px;
}

.collection-record-row {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) 90px 90px 90px 90px;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid var(--line-soft);
  border-radius: 7px;
  background: var(--panel-soft);
  font-size: 13px;
}

.collection-record-row div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.collection-record-row strong,
.collection-record-row span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.collection-record-row div span {
  color: var(--muted);
}

.growth-project-create {
  padding: 14px;
}

.growth-project-create form {
  display: grid;
  gap: 14px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.form-grid label {
  display: grid;
  gap: 6px;
  color: var(--muted);
  font-size: 13px;
}

.form-grid .full {
  grid-column: 1 / -1;
}

.collection-plan-preview {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid var(--line-soft);
  border-radius: 7px;
  background: var(--panel-soft);
  color: var(--muted);
  font-size: 13px;
}

.collection-plan-preview strong {
  color: var(--text);
}

@media (max-width: 1100px) {
  .growth-project-layout {
    grid-template-columns: 1fr;
  }

  .project-status-bar,
  .project-overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 680px) {
  .growth-workbench .module-hero {
    align-items: stretch;
  }

  .growth-workbench .module-hero > button {
    margin-left: 0;
  }

  .project-status-bar,
  .project-overview-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }

  .collection-record-row {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 2: Build frontend**

Run:

```bash
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 3: Start dev server**

Run:

```bash
npm.cmd run dev
```

Expected: Vite prints a local URL, usually `http://127.0.0.1:5173/`.

- [ ] **Step 4: Verify with browser**

Open the dev server URL and navigate to the task workbench. Verify:

- The page title is `增长项目`.
- Project cards render in the left column when `/api/research/growth-projects` returns data.
- Empty state renders when no projects are returned.
- Detail tabs do not overlap at desktop width.
- At mobile width around 390px, cards and detail stack vertically.

- [ ] **Step 5: Commit**

```bash
git add api/webui/src/styles.css
git commit -m "style: polish growth project workbench"
```

---

### Task 6: Full Regression And Cleanup

**Files:**
- Modify only files needed to fix issues found by tests.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
pytest tests/test_growth_projects.py tests/test_research_service.py tests/test_research_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 3: Inspect changed files**

Run:

```bash
git status --short
```

Expected: only files from this plan are modified, plus unrelated pre-existing user changes if they were already present before implementation.

- [ ] **Step 4: Review staged diff before final commit**

Run:

```bash
git diff -- research/growth_projects.py research/service.py research/schemas.py api/routers/research.py api/webui/src/types.ts api/webui/src/main.tsx api/webui/src/pages/GrowthProjectWorkbenchPage.tsx api/webui/src/styles.css tests/test_growth_projects.py tests/test_research_service.py tests/test_research_api.py
```

Expected: diff contains only growth project aggregation, API, UI, styles, and tests.

- [ ] **Step 5: Commit final fixes if any**

If Step 1 or Step 2 required fixes, commit them:

```bash
git add research/growth_projects.py research/service.py research/schemas.py api/routers/research.py api/webui/src/types.ts api/webui/src/main.tsx api/webui/src/pages/GrowthProjectWorkbenchPage.tsx api/webui/src/styles.css tests/test_growth_projects.py tests/test_research_service.py tests/test_research_api.py
git commit -m "test: verify growth project workbench"
```

If there were no fixes after Task 5, skip this commit.

---

## Self-Review

Spec coverage:

- Growth project as the top-level object: Task 1 and Task 4.
- Project cards with recommended action, sample status, metrics, platform, and opportunity score: Task 1 and Task 4.
- Collection records nested under detail: Task 1 and Task 4.
- Soft aggregation over existing `research_jobs`: Task 1 and Task 2.
- Rule-first recommendations: Task 1.
- Create growth project flow: Task 2 and Task 4.
- MVP avoids crawler and worker rewrites: all tasks leave crawler execution unchanged.

Type consistency:

- Backend response fields match `GrowthProjectSummary` and `GrowthProjectDetail`.
- `GrowthProjectCreatePayload` matches `GrowthProjectCreate`.
- Route paths are `/api/research/growth-projects` and `/api/research/growth-projects/{project_id}` throughout.

Implementation order:

- Backend pure logic first.
- API second.
- Frontend types and loading third.
- UI fourth.
- Styling and verification last.
