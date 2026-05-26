# Project-Scoped Today Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Today Intelligence generate, save, and restore separate AI analysis per growth project.

**Architecture:** Add project scope to the Today Intelligence service and API, store results under project-specific `research_global_settings` keys, and have the React app pass the selected project id on load/regenerate. Reuse existing project resolution, project job matching, and job stats instead of introducing a new table.

**Tech Stack:** FastAPI, SQLAlchemy repository helpers, React/TypeScript, existing `OpenAICompatibleProvider`, pytest, Vite.

---

### Task 1: Backend Scope and Cache

**Files:**
- Modify: `research/today_intelligence.py`
- Modify: `api/routers/reports.py`

- [ ] Add `project_id` and `project_record` parameters to Today Intelligence service functions.
- [ ] Add project-specific setting keys with `reports:today-intelligence:project:{resolved_id}`.
- [ ] Resolve `project_id` in the API before calling the service.
- [ ] Return stale saved project results instead of auto-regenerating when stale history exists.

### Task 2: Project-Filtered Input

**Files:**
- Modify: `research/today_intelligence.py`

- [ ] Use project jobs from `list_jobs_for_project` plus semantic fallback matching.
- [ ] Use `get_job_stats_many` to build project database stats.
- [ ] Filter heat snapshots by project keywords and project platforms.
- [ ] Include `project` metadata in `input_summary` and result payload.

### Task 3: Tests

**Files:**
- Modify: `tests/test_today_intelligence_ai.py`

- [ ] Assert project runs persist under a project-specific key.
- [ ] Assert global runs still use the global key.
- [ ] Assert GET with `project_id` returns a project payload.
- [ ] Assert POST regenerate with `project_id` returns the same project scope.

### Task 4: Frontend Wiring

**Files:**
- Modify: `api/webui/src/main.tsx`
- Modify: `api/webui/src/types.ts`

- [ ] Add `project_id` and project metadata to `TodayIntelligenceSummary`.
- [ ] Pass selected project id in GET and regenerate requests.
- [ ] Reload Today Intelligence when selected project changes on the today tab.
- [ ] Keep current dashboard/database fallback behavior for no project.

### Task 5: Verification

**Commands:**
- `uv run pytest tests/test_today_intelligence_ai.py -q`
- `npm.cmd run build`

- [ ] Run backend tests.
- [ ] Run frontend build.
- [ ] Restart the local API so `8080` loads the new route behavior.
- [ ] Verify an authenticated `GET /api/reports/today-intelligence?project_id=...` returns project-scoped AI data.
