# Creator Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add partner creator monitoring to the existing competitor monitor workbench.

**Architecture:** Reuse the existing account-monitoring pipeline and add a `monitor_type` discriminator to account records. Frontend switches the current list between competitors and partner creators, and creator discovery can create partner creator monitor records directly.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite schema migration helper, React, TypeScript, Vite.

---

### Task 1: Backend Monitor Type

**Files:**
- Modify: `research/models.py`
- Modify: `research/schemas.py`
- Modify: `research/repository.py`
- Modify: `research/schema_migration.py`
- Modify: `api/routers/competitors.py`
- Test: `tests/test_competitor_monitor_ranking.py`

- [ ] Add `monitor_type` to `ResearchCompetitorAccount`, defaulting to `competitor`.
- [ ] Add Pydantic validation for `competitor` and `partner_creator`.
- [ ] Let repository create, update, return, and filter by `monitor_type`.
- [ ] Extend schema migration so existing DBs receive `monitor_type`.
- [ ] Extend create/list/from-url/from-candidate APIs.
- [ ] Add tests proving default competitor listings exclude partner creators and filtered listings return them.

### Task 2: Workbench Type Switch

**Files:**
- Modify: `api/webui/src/competitor_monitor/types.ts`
- Modify: `api/webui/src/competitor_monitor/AccountSidebar.tsx`
- Modify: `api/webui/src/competitor_monitor/AddCompetitorDrawer.tsx`
- Modify: `api/webui/src/competitor_monitor/CompetitorMonitorWorkbench.tsx`
- Modify: `api/webui/src/competitor_monitor/mock.ts`
- Modify: `api/webui/src/competitor_monitor/styles.css`

- [ ] Add `MonitorType` to frontend account types.
- [ ] Add segmented switch to the account sidebar.
- [ ] Request `/api/competitors?enabled_only=true&monitor_type=<type>`.
- [ ] Pass the active type to the add drawer and submit it.
- [ ] Update labels for partner creator mode.

### Task 3: Creator Discovery Add Monitor

**Files:**
- Modify: `api/webui/src/pages/creator-discovery/index.tsx`
- Modify: `api/webui/src/pages/creator-discovery/styles.css`

- [ ] Track monitor-add state by creator row.
- [ ] Add “添加监控” action in the result operation column.
- [ ] Submit to `/api/competitors/from-candidate` with `monitor_type=partner_creator`.
- [ ] Mark successful rows as “已监控” and keep row selection behavior intact.

### Task 4: Verification

**Commands:**
- `uv run python -m pytest tests/test_competitor_monitor_ranking.py -q`
- `npm.cmd run build`

- [ ] Run focused backend tests.
- [ ] Run frontend typecheck/build.
- [ ] Fix regressions found by verification.
