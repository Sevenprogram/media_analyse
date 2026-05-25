# Creator Search Session Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist creator discovery searches and restore the latest session after refresh.

**Architecture:** Add tenant-scoped session/session-result tables in the research domain, expose persistence and restore endpoints from the creator-search router, and hydrate the creator discovery page from the saved session snapshot before falling back to the candidate pool.

**Tech Stack:** FastAPI, SQLAlchemy, React, TypeScript, existing research repository.

---

### Task 1: Backend persistence model

**Files:**
- Modify: `D:\program\media_analyse_api_only\research\models.py`
- Modify: `D:\program\media_analyse_api_only\research\repository.py`

- [ ] Add search session and session result models.
- [ ] Add repository methods for create session, get latest session, get one session, and mark session saved.

### Task 2: Backend API

**Files:**
- Modify: `D:\program\media_analyse_api_only\api\routers\creator_search.py`

- [ ] Add create session endpoint.
- [ ] Add latest session restore endpoint.
- [ ] Add save current session endpoint.

### Task 3: Frontend restore and save wiring

**Files:**
- Modify: `D:\program\media_analyse_api_only\api\webui\src\pages\creator-discovery\index.tsx`

- [ ] Restore the latest session on page load.
- [ ] Persist session snapshots after each search.
- [ ] Turn the save button into a real action.
- [ ] Preserve current fallback candidate-pool bootstrap when no session exists.

### Task 4: Verification

**Files:**
- Create: `D:\program\media_analyse_api_only\tests\test_creator_search_session_api.py`

- [ ] Add API tests for persist, restore, and save.
- [ ] Run targeted pytest.
- [ ] Run frontend build.
