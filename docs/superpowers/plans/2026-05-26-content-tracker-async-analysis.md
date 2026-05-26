# Content Tracker Async Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tracker creation return immediately while the first analysis runs in the background, and surface stage-based progress in the content tracking page.

**Architecture:** Reuse the existing in-process async task style already used by content collection. Create an analysis run up front, store tracker-level latest run linkage immediately, update run status/progress through summary metadata, and let the frontend poll that run while preserving the last completed snapshot.

**Tech Stack:** FastAPI, asyncio, SQLAlchemy repository layer, React, TypeScript, existing `api()` helper and page-local polling.

---

### Task 1: Backend async analysis orchestration

**Files:**
- Modify: `D:/program/media_analyse_api_only/api/routers/content_tracking.py`
- Modify: `D:/program/media_analyse_api_only/research/repository.py`

- [ ] Create an analysis run before heavy work starts and mark it `queued`.
- [ ] Add a tracker repository helper that updates `latest_analysis_run_id` without requiring a snapshot.
- [ ] Move heavy analysis execution into a background coroutine launched with `asyncio.create_task(...)`.
- [ ] Update run status and stage progress at each milestone: queued, loading_posts, scoring_candidates, refining_samples, saving_results, completed, failed.
- [ ] Keep snapshot persistence and scoring logic unchanged.

### Task 2: Frontend progress state and polling

**Files:**
- Modify: `D:/program/media_analyse_api_only/api/webui/src/pages/ContentTrackingPageRedesign.tsx`

- [ ] Add local state for the active analysis run and polling guards.
- [ ] Change tracker creation to await only tracker creation plus queued analysis creation.
- [ ] Rework rerun analysis to use the same queued flow.
- [ ] Restore active analysis run from `latest_analysis_run_id` when switching trackers or reloading the page.
- [ ] Poll `/api/content-tracking/analysis-runs/{run_id}` until the run reaches `completed` or `failed`.
- [ ] Refresh the latest snapshot automatically after completion.

### Task 3: Progress banner and visual states

**Files:**
- Modify: `D:/program/media_analyse_api_only/api/webui/src/pages/ContentTrackingPageRedesign.tsx`
- Modify: `D:/program/media_analyse_api_only/api/webui/src/styles.css`

- [ ] Add a top progress banner below the content tracking subtabs.
- [ ] Render stage label, detail message, and a stage-based progress bar.
- [ ] Reflect active analysis in the selected tracker action area so rerun controls disable correctly during polling.
- [ ] Keep the page readable when there is no prior snapshot by showing “analysis in progress” instead of an error.

### Task 4: Verification

**Files:**
- Verify: `D:/program/media_analyse_api_only/api/routers/content_tracking.py`
- Verify: `D:/program/media_analyse_api_only/research/repository.py`
- Verify: `D:/program/media_analyse_api_only/api/webui/src/pages/ContentTrackingPageRedesign.tsx`
- Verify: `D:/program/media_analyse_api_only/api/webui/src/styles.css`

- [ ] Run Python compile checks for touched backend files.
- [ ] Run the frontend build.
- [ ] Smoke-test tracker creation, progress polling, completion refresh, and failed-run messaging.
