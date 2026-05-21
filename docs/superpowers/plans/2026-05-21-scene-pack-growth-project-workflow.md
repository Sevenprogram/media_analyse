# Scene Pack Growth Project Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect keyword-library scene packs to growth projects so users can create projects from reusable scene packs, manage project keyword snapshots, and control project-level collection.

**Architecture:** Reuse the existing `research_scene_packs` and `research_scene_pack_keywords` capability. Add formal growth project tables for project state, keyword snapshots, and collection plans, while keeping existing `research_jobs` as collection records. Frontend changes extend the current keyword library and growth project workbench instead of replacing them.

**Tech Stack:** FastAPI, SQLAlchemy ORM, async repository methods, Pydantic schemas, pytest, React/TypeScript/Vite.

---

## Existing Capabilities To Reuse

- `research_scene_packs`
- `research_scene_pack_keywords`
- `/api/keyword-library/scene-packs`
- `/api/keyword-library/keywords`
- keyword library scene pack UI
- `research.tracking_packs.create_daily_sampling_jobs`
- growth project soft aggregation endpoint added in the previous step

## Task Order

### Task 1: Scene Pack Semantics

- [ ] Extend scene pack schemas with `primary_goal`, `default_collection_depth`, `default_ai_template`, `source`, and `archived`.
- [ ] Normalize keyword types to the product vocabulary:
  - `primary` -> core
  - `secondary` -> expanded
  - `ai_suggested` -> pending
  - `negative` -> excluded
- [ ] Keep backward compatibility with existing stored keyword types.
- [ ] Add tests for scene pack create/update payloads and keyword type mapping.

### Task 2: Growth Project Tables And Repository

- [ ] Add ORM models:
  - `ResearchGrowthProject`
  - `ResearchGrowthProjectKeyword`
  - `ResearchGrowthProjectCollectionPlan`
- [ ] Add repository methods to create/list/get/archive projects.
- [ ] Add repository methods to create/list/update project keyword snapshots.
- [ ] Add repository methods to create/list/update collection plans.
- [ ] Add tests for repository-independent pure project creation helpers where practical, plus API tests using fake repositories.

### Task 3: Create Growth Project From Scene Pack

- [ ] Extend `GrowthProjectCreate` with `scene_pack_id` and optional `start_immediately`.
- [ ] When `scene_pack_id` is present:
  - load scene pack
  - load enabled scene pack keywords
  - copy core/expanded/pending/excluded keywords into project keyword snapshot
  - use core + expanded keywords for initial collection job
  - create collection plans per selected platform
- [ ] Return project id, created job ids, keyword snapshot counts, and collection plans.
- [ ] Add API tests for scene-pack-driven project creation.

### Task 4: Project Collection Control

- [ ] Add endpoints:
  - `POST /api/research/growth-projects/{id}/collection/start`
  - `POST /api/research/growth-projects/{id}/collection/pause`
  - `POST /api/research/growth-projects/{id}/collection/stop-current-run`
  - `POST /api/research/growth-projects/{id}/archive`
- [ ] First version semantics:
  - start creates/schedules a new search job from active project keywords
  - pause disables future collection plans
  - stop-current-run cancels queued/pending plans and marks project collection state as stopped; it does not kill already-running external processes
  - archive hides the project from the default list
- [ ] Add tests for each endpoint.

### Task 5: Frontend Integration

- [ ] Keyword library:
  - expose scene pack fields in the form
  - show core/expanded/pending/excluded keyword counts
  - add “用此创建增长项目”
- [ ] Growth project workbench:
  - scene pack selector in create form
  - auto-fill platforms and keyword preview from selected scene pack
  - show `关键词&场景` tab
  - show `采集计划` tab
  - add buttons: start collection, pause, stop current run, archive
- [ ] Run `npm.cmd run build`.

### Task 6: Verification

- [ ] Run backend tests:
  - `pytest tests/test_keyword_library_api.py tests/test_research_api.py tests/test_research_service.py tests/test_growth_projects.py -v`
- [ ] Run frontend build:
  - `npm.cmd run build`
- [ ] Browser-check keyword library scene pack tab and growth project workbench.

## MVP Boundary

This implementation will not add AI-generated scene packs, scene pack versioning, hard deletion of samples, or full worker process termination. The first version uses archive/soft control semantics to avoid data loss and process-risk surprises.
