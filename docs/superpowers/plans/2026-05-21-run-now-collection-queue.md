# Run Now Collection Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add queued "立即采集" for growth projects with realtime progress polling.

**Architecture:** Reuse the existing single research execution runner and wrap it with a lightweight in-process FIFO queue. Growth project run-now creates a `ResearchJob`, enqueues it, starts the queue worker if idle, and exposes queue/progress snapshots through REST endpoints.

**Tech Stack:** FastAPI, asyncio, existing `ResearchRepository`, React/Vite, polling-based progress UI.

---

### Task 1: Backend Queue Manager

**Files:**
- Modify: `api/routers/research.py`
- Test: `tests/test_research_api.py`

- [ ] Add queue state near `_research_execution_task`: `_research_execution_queue`, `_research_queue_worker_task`, and helpers `_enqueue_research_job`, `_run_research_execution_queue`, `_collection_queue_snapshot`, `_job_progress_snapshot`.
- [ ] Change `schedule_and_execute_research_job` so direct background execution remains available, while run-now can enqueue without returning busy.
- [ ] Add `GET /api/research/collection-queue`.

### Task 2: Growth Project Run Now

**Files:**
- Modify: `api/routers/research.py`
- Test: `tests/test_research_api.py`

- [ ] Add `POST /api/research/growth-projects/{project_id}/collection/run-now`.
- [ ] Reuse project keywords/platforms from growth project detail.
- [ ] Return `{status: "queued", job, queue_position}` and update project collection status.

### Task 3: Progress Endpoint

**Files:**
- Modify: `api/routers/research.py`
- Test: `tests/test_research_api.py`

- [ ] Add `GET /api/research/growth-projects/{project_id}/collection/progress`.
- [ ] Compute progress from `ResearchCrawlUnit` statuses when available; fall back to job status and job stats.
- [ ] Include current job, queued jobs, percent, posts/comments/raw counts, and latest event.

### Task 4: Frontend Controls

**Files:**
- Modify: `api/webui/src/pages/GrowthProjectWorkbenchPage.tsx`
- Modify: `api/webui/src/main.tsx`
- Modify: `api/webui/src/types.ts`
- Modify: `api/webui/src/styles.css`

- [ ] Rename main action to "立即采集".
- [ ] Poll progress every 2 seconds for selected project.
- [ ] Show progress bar, queued jobs, current job, sample counters, and latest event.
- [ ] Keep pause/stop/archive controls.

### Task 5: Verification

**Files:**
- Test: `tests/test_research_api.py`

- [ ] Run focused backend tests.
- [ ] Run `npm.cmd run build`.
- [ ] Verify the workbench in browser at `http://127.0.0.1:5174/static/dist/research`.

