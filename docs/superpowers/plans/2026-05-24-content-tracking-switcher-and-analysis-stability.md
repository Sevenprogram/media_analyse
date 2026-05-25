# Content Tracking Switcher And Analysis Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the content tracking overview switch between trackers reliably and ensure tracker analysis snapshots are persisted even when collected posts contain duplicate records.

**Architecture:** Keep the existing React page and FastAPI router structure. Add a local tracker switcher state in `ContentTrackingPageRedesign.tsx`, separate "view analysis" from "edit tracker", and deduplicate backend candidate samples before writing tables that have unique constraints.

**Tech Stack:** React, TypeScript, FastAPI, SQLAlchemy async repository, pytest/httpx integration tests.

---

### Task 1: Backend Analysis Persistence

**Files:**
- Modify: `research/content_tracking.py`
- Modify: `research/repository.py`
- Test: `tests/test_content_tracking_api.py`

- [ ] **Step 1: Add regression coverage for duplicate post candidates**

Add an integration test that seeds two `ResearchPost` rows with the same `platform` and `platform_post_id`, runs tracker analysis, and asserts a snapshot is created with only one saved candidate sample for that duplicate key.

- [ ] **Step 2: Deduplicate candidate rows**

In `build_tracker_analysis_snapshot`, deduplicate `candidate_rows` and `candidate_rows_all` by `(platform, platform_post_id)` after sorting candidates by similarity, engagement, and publish time, preserving the strongest row for each content item.

- [ ] **Step 3: Mark failed runs when persistence fails**

Wrap `_persist_tracker_analysis_snapshot` persistence after run creation in a `try/except`. On exception, update the run status to `failed` with `error_message`, then re-raise so API callers and collection runs still see a failure.

- [ ] **Step 4: Verify backend tests**

Run `pytest tests/test_content_tracking_api.py -q`.

### Task 2: Frontend Tracker Switching

**Files:**
- Modify: `api/webui/src/pages/ContentTrackingPageRedesign.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Add switcher UI state**

Add `trackerMenuOpen` state, a derived `activeTrackerCandidates` list, and close the menu after selecting a tracker.

- [ ] **Step 2: Wire topbar selector**

Turn the static `ct-select-pill` button into a menu trigger. Render a dropdown containing filtered tracker rows with name, status, platforms, and included keywords. Selecting a row sets `selectedTrackerId` and returns to `analysis overview`.

- [ ] **Step 3: Split list actions**

In the tracker list card actions, add `查看分析` that sets `selectedTrackerId` and switches to `analysis overview`. Keep `编辑` for editing without conflating it with analysis viewing.

- [ ] **Step 4: Improve empty-state copy**

When a selected tracker has no snapshot, keep the existing "run analysis" prompt visible and make sure actions remain enabled.

- [ ] **Step 5: Verify frontend build**

Run `npm.cmd run build`.

### Task 3: Final Validation

**Files:**
- Review changed files only.

- [ ] **Step 1: Run focused backend test**

Run `pytest tests/test_content_tracking_api.py -q` after all changes.

- [ ] **Step 2: Run frontend build**

Run `npm.cmd run build`.

- [ ] **Step 3: Inspect diff**

Run `git diff -- api/webui/src/pages/ContentTrackingPageRedesign.tsx api/webui/src/styles.css api/routers/content_tracking.py research/content_tracking.py research/repository.py tests/test_content_tracking_api.py docs/superpowers/plans/2026-05-24-content-tracking-switcher-and-analysis-stability.md`.

