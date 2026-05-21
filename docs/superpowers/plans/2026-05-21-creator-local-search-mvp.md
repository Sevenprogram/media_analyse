# Creator Local Search MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the audience creator filter return useful local candidates from existing crawled research posts, even when profile rebuilds or tag matches have not been prepared manually.

**Architecture:** Keep the feature inside the existing creator search service and Web UI. The backend search endpoint will auto-rebuild missing creator profiles from posts, use tag scoring when tags exist, and fall back to local query-term matching over creator posts when tags are absent or inconclusive. The frontend will display backend diagnostics so an empty result explains the missing prerequisite instead of silently failing.

**Tech Stack:** FastAPI, Pydantic, async repository service layer, React/TypeScript Vite Web UI, pytest.

---

### Task 1: Backend Local Fallback Search

**Files:**
- Modify: `MediaCrawler/research/creator_search.py`
- Test: `MediaCrawler/tests/test_creator_discovery_scoring.py`

- [ ] **Step 1: Add a failing async test for auto-rebuild and text fallback**

Add a test that calls `search_creators()` with no existing profiles, a repository that has two posts by one creator, and no tag definitions. It should assert that the service rebuilds one profile and returns that creator by matching `K12` and `single mom` against recent post text.

- [ ] **Step 2: Implement profile auto-rebuild**

Inside `search_creators()`, after the first `list_creator_profiles()` call returns empty, call `rebuild_creator_profiles()` with the selected platform when there is exactly one platform filter. Use the returned `profiles` for the same search request and expose `diagnostics["auto_rebuilt_profiles"]`.

- [ ] **Step 3: Implement query-term fallback**

Add helpers that split `raw_query` by whitespace and common Chinese separators, preserve short ASCII terms such as `K12`, score creator profile text plus recent posts, and return representative matching posts as evidence. Use this fallback when no required or optional tag ids were inferred, or when tag scoring for a profile has no entity tags.

- [ ] **Step 4: Return diagnostics**

Return `diagnostics` with `profile_count`, `tag_definition_count`, `matched_tag_count`, `fallback_used`, `auto_rebuilt_profiles`, and `guidance`. Keep the existing `results` and `intent` response shape intact for compatibility.

- [ ] **Step 5: Run backend tests**

Run: `python -m pytest tests/test_creator_discovery_scoring.py tests/test_creator_discovery_postprocess.py tests/test_creator_discovery_workflow_api.py -q`

Expected: all selected tests pass.

### Task 2: Frontend Diagnostics

**Files:**
- Modify: `MediaCrawler/api/webui/src/main.tsx`

- [ ] **Step 1: Extend response typing**

Add a `CreatorSearchDiagnostics` type and store the last diagnostics in `AudiencePage`.

- [ ] **Step 2: Show actionable status**

After `筛选达人`, render the diagnostics in the status panel: profile count, tag count, whether fallback was used, whether profiles were auto-rebuilt, and guidance text.

- [ ] **Step 3: Improve empty state**

When no results are returned, show backend guidance instead of a generic empty message.

- [ ] **Step 4: Build UI**

Run: `npm.cmd run build`

Expected: TypeScript and Vite build pass.
