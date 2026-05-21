# Content Tracking Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-database content tracking workbench with keyword extraction, similar-content search, tracker creation, and AI analysis through the env-configured OpenAI-compatible gateway.

**Architecture:** Keep retrieval deterministic in `research.content_tracking` and expose one new `/api/content-tracking/ai-analysis` route that sends only local evidence to the gateway. Replace the existing placeholder React page with a dense three-column workbench that calls existing local APIs plus the new AI route.

**Tech Stack:** FastAPI, Pydantic, existing `ResearchRepository`, OpenAI-compatible `research.ai_provider`, React, TypeScript, existing UI primitives, CSS modules in `styles.css`.

---

### Task 1: Backend AI Analysis

**Files:**
- Modify: `research/schemas.py`
- Modify: `research/content_tracking.py`
- Modify: `api/routers/content_tracking.py`
- Test: `tests/test_content_tracking_api.py`

- [ ] Add a `ContentTrackingAIAnalysisRequest` schema with source text, selected keywords, candidates, comments, and optional provider id.
- [ ] Add prompt building and output normalization helpers in `research.content_tracking`.
- [ ] Add `/api/content-tracking/ai-analysis` using the enabled AI provider from the local repository or the provided provider id.
- [ ] Test success with a fake provider and test missing provider returns a clear HTTP error.

### Task 2: Frontend Workbench

**Files:**
- Modify: `api/webui/src/pages/ResearchModulePages.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] Replace `ContentTrackingPage` placeholder with local state for input, selected platforms, keywords, candidates, trackers, tracker analysis, and AI report.
- [ ] Wire buttons to `/extract-keywords`, `/search-similar`, `/trackers`, `/trackers/{id}/analysis`, and `/ai-analysis`.
- [ ] Render keyword chips with include toggles, local content cards, tracker controls, and AI report sections.
- [ ] Add responsive CSS for a dense research-console layout.

### Task 3: Verification

**Files:**
- Use existing test and build commands.

- [ ] Run focused backend tests: `pytest tests/test_content_tracking_api.py -q`.
- [ ] Run frontend build: `npm.cmd run build`.
- [ ] Fix any type, lint, or behavior failures without changing unrelated files.
