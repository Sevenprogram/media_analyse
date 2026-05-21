# Background Task Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a left-sidebar background task center that lists and cancels current Web backend process tasks through one unified API.

**Architecture:** Add a focused backend service/router for task aggregation and cancellation, keeping process-local state ownership in the existing routers. Add a small AI analysis task registry so AI jobs have cancellable asyncio handles. Add a React page that polls the unified API and uses a confirmation dialog before cancellation.

**Tech Stack:** FastAPI, asyncio, SQLAlchemy-backed repository helpers, React/Vite/TypeScript, lucide-react, pytest.

---

### Task 1: Backend Task Center API

**Files:**
- Create: `api/services/background_task_center.py`
- Create: `api/routers/background_tasks.py`
- Modify: `api/main.py`
- Test: `tests/test_background_tasks_api.py`

- [ ] **Step 1: Add service tests for aggregation and queue cancellation**

Create `tests/test_background_tasks_api.py` with tests that patch current in-memory state and verify `/api/background-tasks` plus queue cancellation.

- [ ] **Step 2: Implement `background_task_center.py`**

Create a service with:

```python
RUNNING_STATUSES = {"running", "stopping"}
QUEUED_STATUSES = {"queued", "pending"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
```

It should produce normalized items with `id`, `type`, `title`, `status`, `progress`, `source`, `started_at`, `updated_at`, `cancellable`, `cancel_reason`, `related_job_id`, and `detail`.

- [ ] **Step 3: Implement `background_tasks.py` router**

Expose:

```python
@router.get("")
async def list_background_tasks()

@router.post("/{task_id:path}/cancel")
async def cancel_background_task(task_id: str)
```

Use `:path` so ids such as `research-execution:123` pass through unchanged.

- [ ] **Step 4: Mount router**

Import and include the router in `api/main.py` under `/api`.

- [ ] **Step 5: Run backend API tests**

Run: `uv run python -m pytest tests/test_background_tasks_api.py -q`

Expected: all tests pass.

### Task 2: AI Analysis Registry

**Files:**
- Modify: `api/routers/research.py`
- Modify: `research/ai_analysis.py`
- Test: `tests/test_background_tasks_api.py`

- [ ] **Step 1: Add in-memory AI task registry**

In `api/routers/research.py`, add a process-local `AI_ANALYSIS_TASKS` mapping keyed by `analysis_job_id`.

- [ ] **Step 2: Register AI tasks when running**

Change `run_ai_analysis_job` so it stores the created asyncio task and minimal metadata, then removes or marks terminal state in a done callback.

- [ ] **Step 3: Handle AI cancellation**

In `AIAnalysisRunner.run`, catch `asyncio.CancelledError`, update the AI job status to `cancelled`, create a cancellation event, then re-raise.

- [ ] **Step 4: Cover AI registry in task center tests**

Patch `AI_ANALYSIS_TASKS` with a fake pending task and verify it appears as `ai-analysis:{id}` and can be cancelled.

### Task 3: Frontend Task Center Page

**Files:**
- Modify: `api/webui/src/types.ts`
- Modify: `api/webui/src/components/sidebar.tsx`
- Modify: `api/webui/src/main.tsx`
- Create: `api/webui/src/pages/BackgroundTasksPage.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Add TypeScript types**

Add `BackgroundTaskItem`, `BackgroundTaskSummary`, and include `"background_tasks"` in `ResearchTab`.

- [ ] **Step 2: Add sidebar item**

Add `后台任务` after `任务工作台` with an appropriate lucide icon.

- [ ] **Step 3: Add page component**

Create a page that fetches `/api/background-tasks`, polls every 2 seconds, filters by type, shows summary cards and task rows, and calls `POST /api/background-tasks/{task.id}/cancel` after confirmation.

- [ ] **Step 4: Wire page into `main.tsx`**

Render the page when `tab === "background_tasks"`.

- [ ] **Step 5: Add scoped CSS**

Add styles for `.background-task-page`, summary cards, filter chips, task rows, status badges, progress bars, and detail blocks.

### Task 4: Verification

**Files:**
- No new production files.

- [ ] **Step 1: Run focused backend tests**

Run: `uv run python -m pytest tests/test_background_tasks_api.py tests/test_research_api.py -q`

- [ ] **Step 2: Run frontend build**

Run: `npm.cmd run build`

- [ ] **Step 3: Inspect git diff**

Run: `git diff -- api/services/background_task_center.py api/routers/background_tasks.py api/main.py api/routers/research.py research/ai_analysis.py api/webui/src/types.ts api/webui/src/components/sidebar.tsx api/webui/src/main.tsx api/webui/src/pages/BackgroundTasksPage.tsx api/webui/src/styles.css tests/test_background_tasks_api.py`

Confirm only task-center related changes are present.
