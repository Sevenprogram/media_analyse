# Content Tracking P0 Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the P0 backend analysis pipeline for content tracking, including analysis persistence, candidate samples, decision metrics, and read/run APIs.

**Architecture:** Extend the existing `research_content_trackers` workflow instead of replacing it. Persist one normalized analysis run, one rich analysis snapshot, and optional candidate samples per run; compute P0 metrics in a deterministic Python service and expose them through tracker-scoped endpoints while preserving the legacy lightweight snapshot for compatibility.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy ORM, existing research repository/service pattern, SQLite/PostgreSQL-compatible JSON columns.

---

### Task 1: Add persistence models for tracker analysis

**Files:**
- Modify: `D:\program\media_analyse_api_only\research\models.py`

- [ ] Add ORM models for `research_content_tracker_analysis_runs`, `research_content_tracker_analysis_snapshots`, and `research_content_tracker_candidate_samples`.
- [ ] Keep fields focused on P0: tracker/run ids, status, window metadata, summary scores, snapshot JSON blocks, candidate evidence, and timestamps.
- [ ] Preserve the existing `research_content_tracking_snapshots` table for backward compatibility.

### Task 2: Add schema bootstrap and upgrade coverage

**Files:**
- Modify: `D:\program\media_analyse_api_only\research\schema_migration.py`

- [ ] Add `_ensure_table(...)` calls for the three new analysis tables.
- [ ] Provide SQLite/PostgreSQL/MySQL/MariaDB create statements.
- [ ] Ensure the new tables can be bootstrapped on older databases without breaking existing installs.

### Task 3: Extend repository methods for analysis storage and retrieval

**Files:**
- Modify: `D:\program\media_analyse_api_only\research\repository.py`

- [ ] Import the new ORM models.
- [ ] Add repository methods to create/update analysis runs.
- [ ] Add repository methods to replace candidate samples for a run.
- [ ] Add repository methods to create and fetch rich analysis snapshots.
- [ ] Add dict serializers for the new models.

### Task 4: Implement P0 analysis computation service

**Files:**
- Modify: `D:\program\media_analyse_api_only\research\content_tracking.py`

- [ ] Add deterministic helpers for candidate classification, quality metrics, trend metrics, keyword metrics, creator metrics, risk metrics, and decision metrics.
- [ ] Reuse existing post search/fingerprint helpers where possible.
- [ ] Add one orchestration function that returns a complete P0 analysis payload plus persistence payloads.

### Task 5: Wire FastAPI endpoints to the new analysis flow

**Files:**
- Modify: `D:\program\media_analyse_api_only\api\routers\content_tracking.py`

- [ ] Upgrade `POST /content-tracking/trackers/{tracker_id}/analysis` to run the rich P0 analysis and persist new records.
- [ ] Add `GET /content-tracking/trackers/{tracker_id}/analysis` for the latest snapshot.
- [ ] Add `GET /content-tracking/trackers/{tracker_id}/analysis/history` and `GET /content-tracking/analysis-runs/{run_id}` if the repository surface is ready.
- [ ] Preserve enough of the legacy response shape to avoid obvious breakage.

### Task 6: Validate with focused checks

**Files:**
- Optional Modify: `D:\program\media_analyse_api_only\tests\...` if a small regression test is practical

- [ ] Run at least syntax/compile validation for edited Python modules.
- [ ] If lightweight tests are feasible, add one focused repository/service or API smoke test.
- [ ] Record any intentional P1/P2 omissions in the final handoff.
