# Content Tracking Realtime Cancel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a content tracking realtime running strip and a safe cancel action for the current content tracking realtime job.

**Architecture:** The content tracking API owns a dedicated cancel endpoint that verifies `topic == "content_realtime_discovery"` before cancelling. The content tracking page keeps current realtime job metadata in its module-level state and renders either a cancellable current-job strip or a non-cancellable global-busy strip.

**Tech Stack:** FastAPI, pytest, React, TypeScript, Vite.

---

### Task 1: Backend Realtime Cancel API

**Files:**
- Modify: `api/routers/research.py`
- Modify: `api/routers/content_tracking.py`
- Test: `tests/test_content_tracking_api.py`

- [ ] **Step 1: Add backend tests**

Add tests that assert content tracking can cancel only its own realtime job and rejects another topic.

- [ ] **Step 2: Add a research helper**

Expose a helper in `api/routers/research.py` that cancels the active research execution only when the active job id matches the requested job id.

- [ ] **Step 3: Add the content tracking cancel endpoint**

Add `POST /api/content-tracking/realtime-jobs/{job_id}/cancel`, load the job, validate topic, cancel active execution when matching, otherwise mark pending/queued/running content tracking job cancelled.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_content_tracking_api.py -q`

### Task 2: Frontend Running Strip And Cancel

**Files:**
- Modify: `api/webui/src/pages/ResearchModulePages.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Extend content tracking state**

Add `realtimeJobId`, `realtimeBusyJobId`, and `realtimeCancelling` to the module-level content tracking state.

- [ ] **Step 2: Capture realtime metadata**

When realtime search starts and the backend returns job metadata, store the content tracking job id. If the backend returns a busy error, show a global-busy strip without a cancel button.

- [ ] **Step 2a: Add total post limit**

Add a realtime-only numeric input that sends the combined post limit to the backend. The backend stores the combined limit and splits it across selected platforms.

- [ ] **Step 3: Add cancel action**

Wire the cancel button to `POST /api/content-tracking/realtime-jobs/{job_id}/cancel`, clear local realtime state on success, and display a Chinese status message.

- [ ] **Step 4: Style the strip**

Add compact styles for the running strip, busy strip, progress label, and cancel button without changing other pages.

- [ ] **Step 5: Run frontend build**

Run: `npm.cmd run build` in `api/webui`.
