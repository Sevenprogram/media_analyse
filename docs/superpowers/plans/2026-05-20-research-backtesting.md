# Research Backtesting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a historical backtesting workflow for validating research scoring against past data.

**Architecture:** Add a focused backtesting service that reads normalized research posts, replays keyword heat by day, stores a JSON report, and exposes it through a small FastAPI router. The React console gets one new page that can create, run, and inspect backtests.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, Vite React TypeScript.

---

### Task 1: Backend Model And Repository

**Files:**
- Modify: `research/models.py`
- Modify: `research/repository.py`

- [ ] Add `ResearchBacktest` with JSON columns for keywords, platforms, and report.
- [ ] Import the model in `ResearchRepository`.
- [ ] Add create, get, list, update, and serializer methods.

### Task 2: Backtesting Service

**Files:**
- Create: `research/backtesting.py`

- [ ] Define request-independent helpers for date windows and post filtering.
- [ ] Build `run_backtest(repository, backtest)` that loads posts and produces report JSON.
- [ ] Use `aggregate_keyword_heat_from_posts(..., now=...)` for daily replay.
- [ ] Return calibration notes when sample size is low, signal is volatile, or labels conflict across platforms.

### Task 3: API Router

**Files:**
- Create: `api/routers/backtests.py`
- Modify: `api/main.py`

- [ ] Add Pydantic models for create/run payloads.
- [ ] Implement create/list/get/run/report endpoints.
- [ ] Register the router under `/api`.

### Task 4: Frontend Page

**Files:**
- Modify: `api/webui/src/main.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] Add `backtests` tab and sidebar entry.
- [ ] Add create/run form with default `K12教育 + 单亲妈妈`.
- [ ] Render recent backtests and selected report.
- [ ] Add compact daily replay table and calibration notes.

### Task 5: Verification

**Files:**
- Create: `tests/test_backtests_api.py`
- Create: `tests/test_backtesting.py`

- [ ] Seed historical posts.
- [ ] Verify create/run/report APIs.
- [ ] Verify service replay output.
- [ ] Run focused pytest and `npm.cmd run build`.
