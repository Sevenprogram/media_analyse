# Growth Project Edit Collection Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand growth project editing to cover platform checkbox selection, scene pack switching with keyword handling mode, comment collection toggle, crawl frequency, and immediate crawl behavior.

**Architecture:** Store project-level collection preferences on `ResearchGrowthProject`, keep per-platform schedule in `ResearchGrowthProjectCollectionPlan`, and keep keyword snapshots in `ResearchGrowthProjectKeyword`. Editing a scene pack applies one of three keyword modes: replace, append, or link-only.

**Tech Stack:** FastAPI, SQLAlchemy models/repository, Pydantic schemas, React/Vite.

---

### Task 1: Backend Model and Schema

**Files:**
- Modify: `research/models.py`
- Modify: `research/schema_migration.py`
- Modify: `research/schemas.py`

- [ ] Add growth project columns for comment collection, refresh cadence, and custom interval.
- [ ] Add schema migration for existing databases.
- [ ] Extend `GrowthProjectUpdate` with scene pack, keyword handling mode, comments, refresh fields.

### Task 2: Backend Update Semantics

**Files:**
- Modify: `research/repository.py`
- Modify: `research/service.py`
- Modify: `api/routers/research.py`
- Test: `tests/test_research_api.py`

- [ ] Return new settings in project detail.
- [ ] Apply scene pack keyword modes on edit.
- [ ] Update collection plans from selected platforms/frequency.
- [ ] Make run-now use the project comment toggle.

### Task 3: Frontend Edit UI

**Files:**
- Modify: `api/webui/src/types.ts`
- Modify: `api/webui/src/pages/GrowthProjectWorkbenchPage.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] Replace platform text input with checkboxes.
- [ ] Add scene pack selector and keyword handling mode selector.
- [ ] Add comment collection toggle.
- [ ] Add fixed/custom frequency controls.

### Task 4: Verification

**Files:**
- Test: `tests/test_research_api.py`

- [ ] Run backend focused tests.
- [ ] Run `npm.cmd run build`.

