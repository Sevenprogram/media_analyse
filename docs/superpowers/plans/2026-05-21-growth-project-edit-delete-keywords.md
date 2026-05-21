# Growth Project Edit Delete Keywords Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add project edit/delete controls and make each project's crawl keywords explicit.

**Architecture:** Keep project deletion as a soft archive so collected samples remain available. Growth project detail should prefer the formal project keyword snapshot over inferred job keywords, so the UI can show exactly which core and expanded keywords participate in crawling.

**Tech Stack:** FastAPI, Pydantic schemas, existing repository/service layer, React/Vite.

---

### Task 1: Backend Project Update and Delete

**Files:**
- Modify: `research/schemas.py`
- Modify: `api/routers/research.py`
- Test: `tests/test_research_api.py`

- [ ] Add `GrowthProjectUpdate`.
- [ ] Add `PATCH /api/research/growth-projects/{project_id}`.
- [ ] Add `DELETE /api/research/growth-projects/{project_id}` as soft archive.

### Task 2: Formal Keyword Snapshot in Detail

**Files:**
- Modify: `research/service.py`
- Test: `tests/test_research_service.py`

- [ ] Merge formal growth project keywords into detail when a project record exists.
- [ ] Keep legacy job keyword inference as fallback.

### Task 3: Frontend Edit/Delete and Keyword Visibility

**Files:**
- Modify: `api/webui/src/types.ts`
- Modify: `api/webui/src/main.tsx`
- Modify: `api/webui/src/pages/GrowthProjectWorkbenchPage.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] Add edit/delete buttons in project detail.
- [ ] Add settings edit form.
- [ ] Add "参与采集关键词" summary and copy button in keywords tab.

### Task 4: Verification

**Files:**
- Test: `tests/test_research_api.py`
- Test: `tests/test_research_service.py`

- [ ] Run focused backend tests.
- [ ] Run frontend build.

