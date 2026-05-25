# Collection And Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add manual collection runs for content tracking and competitor monitoring, with optional follow-up analysis and frontend status polling.

**Architecture:** Introduce a shared `collection_runs` persistence layer and run-status APIs first, then wire tracker collection and competitor collection services to existing database and analysis paths. Frontend buttons poll run status and refresh only the relevant modules after completion.

**Tech Stack:** FastAPI, SQLAlchemy, React, TypeScript, Vite

---

### Task 1: Add Collection Run Persistence

**Files:**
- Modify: `D:\program\media_analyse_api_only\research\models.py`
- Modify: `D:\program\media_analyse_api_only\research\schema_migration.py`
- Modify: `D:\program\media_analyse_api_only\research\repository.py`
- Modify: `D:\program\media_analyse_api_only\research\schemas.py`

- [ ] Add a `collection_runs` model with status, phase, payload, summary, and error fields.
- [ ] Add schema migration support for the new table.
- [ ] Add repository methods:
  - `create_collection_run`
  - `update_collection_run_status`
  - `update_collection_run_summary`
  - `get_collection_run`
  - `list_collection_runs_for_target`
- [ ] Add Pydantic response schemas for collection run payloads.

### Task 2: Add Content Tracker Collection Service

**Files:**
- Create: `D:\program\media_analyse_api_only\research\content_tracking_collection.py`
- Modify: `D:\program\media_analyse_api_only\research\content_tracking.py`
- Modify: `D:\program\media_analyse_api_only\api\routers\content_tracking.py`

- [ ] Create a tracker collection entrypoint that reads tracker config and creates a collection run.
- [ ] Implement `collect_only` and `collect_and_analyze` modes.
- [ ] Reuse existing tracker analysis snapshot generation after successful collection.
- [ ] Add endpoints:
  - `POST /api/content-tracking/trackers/{tracker_id}/collect`
  - `POST /api/content-tracking/trackers/{tracker_id}/collect-and-analyze`
  - `GET /api/content-tracking/collection-runs/{run_id}`

### Task 3: Add Competitor Collection Service

**Files:**
- Create: `D:\program\media_analyse_api_only\research\competitor_collection.py`
- Modify: `D:\program\media_analyse_api_only\api\routers\competitors.py`
- Modify: `D:\program\media_analyse_api_only\research\repository.py`

- [ ] Create a competitor collection entrypoint that reads competitor config and creates a collection run.
- [ ] Implement `collect_only` and `collect_and_refresh` modes.
- [ ] Refresh competitor-facing summary/ranking/composition/anomaly data after successful collection.
- [ ] Add endpoints:
  - `POST /api/competitors/{competitor_id}/collect`
  - `POST /api/competitors/{competitor_id}/collect-and-refresh`
  - `GET /api/competitors/collection-runs/{run_id}`

### Task 4: Add Frontend Run Triggers And Polling

**Files:**
- Modify: `D:\program\media_analyse_api_only\api\webui\src\pages\ContentTrackingPageRedesign.tsx`
- Modify: `D:\program\media_analyse_api_only\api\webui\src\competitor_monitor\CompetitorMonitorWorkbench.tsx`
- Modify: `D:\program\media_analyse_api_only\api\webui\src\utils\api.ts`

- [ ] Add content-tracking buttons for:
  - collect only
  - collect and analyze
  - re-analyze only
- [ ] Add competitor buttons for:
  - collect only
  - collect and refresh
- [ ] Add polling state for collection runs.
- [ ] Refresh only relevant modules after success.

### Task 5: Add Tests

**Files:**
- Create: `D:\program\media_analyse_api_only\tests\test_collection_runs_api.py`
- Modify: `D:\program\media_analyse_api_only\tests\test_content_tracking_api.py`
- Modify: `D:\program\media_analyse_api_only\tests\test_lead_attribution_api.py`

- [ ] Add API tests for content tracking collection run lifecycle.
- [ ] Add API tests for competitor collection run lifecycle.
- [ ] Add assertions for:
  - queued -> running -> succeeded
  - collect-and-analyze triggers analysis
  - partial failure returns structured errors

### Task 6: Verification

**Files:**
- Modify: `D:\program\media_analyse_api_only\research\models.py`
- Modify: `D:\program\media_analyse_api_only\research\schema_migration.py`
- Modify: `D:\program\media_analyse_api_only\research\repository.py`
- Modify: `D:\program\media_analyse_api_only\api\routers\content_tracking.py`
- Modify: `D:\program\media_analyse_api_only\api\routers\competitors.py`
- Modify: `D:\program\media_analyse_api_only\api\webui\src\pages\ContentTrackingPageRedesign.tsx`
- Modify: `D:\program\media_analyse_api_only\api\webui\src\competitor_monitor\CompetitorMonitorWorkbench.tsx`

- [ ] Run `pytest tests/test_content_tracking_api.py -q`
- [ ] Run `pytest tests/test_collection_runs_api.py -q`
- [ ] Run `npm.cmd run build`
- [ ] Verify manual collection and polling behavior in browser.

