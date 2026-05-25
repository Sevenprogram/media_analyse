# Tab Lazy Fetch And Viewport Chart Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delay non-active tab data requests and load competitor-monitor charts only after they enter the viewport.

**Architecture:** Move the root app from eager global prefetching to tab-scoped refresh paths, then add a tiny viewport observer hook and an opt-in `enabled` flag for endpoint fetching. Competitor chart blocks will mount and fetch only after they are visible, while preserving the existing page layout and data contracts.

**Tech Stack:** React, TypeScript, Vite

---

### Task 1: Tab-Scoped Root Fetching

**Files:**
- Modify: `D:\program\media_analyse_api_only\api\webui\src\main.tsx`

- [ ] Replace eager app-wide bootstrap fetching with tab-aware refresh callbacks.
- [ ] Guard selected job loading so `/jobs/:id/*` requests only run for the keyword-heat tab.
- [ ] Guard project detail/progress loading so project polling only runs for tabs that render those datasets.
- [ ] Keep the header refresh button behavior, but make it refresh only the currently active tab's data.

### Task 2: Reusable Lazy Endpoint Controls

**Files:**
- Modify: `D:\program\media_analyse_api_only\api\webui\src\lib\useEndpoint.ts`
- Create: `D:\program\media_analyse_api_only\api\webui\src\lib\useInView.ts`

- [ ] Extend `useEndpoint` with an optional `enabled` flag that skips initial network work when false.
- [ ] Add a small `useInView` hook backed by `IntersectionObserver` with one-shot behavior for lazy mounting.

### Task 3: Competitor Chart Viewport Loading

**Files:**
- Modify: `D:\program\media_analyse_api_only\api\webui\src\competitor_monitor\InsightSidebar.tsx`

- [ ] Use `useInView` to gate the composition chart block and publish heatmap block independently.
- [ ] Trigger the shared composition endpoint only when either chart block becomes visible.
- [ ] Render lightweight placeholders before visibility so layout stays stable.

### Task 4: Verification

**Files:**
- Modify: `D:\program\media_analyse_api_only\api\webui\src\main.tsx`
- Modify: `D:\program\media_analyse_api_only\api\webui\src\lib\useEndpoint.ts`
- Modify: `D:\program\media_analyse_api_only\api\webui\src\competitor_monitor\InsightSidebar.tsx`
- Create: `D:\program\media_analyse_api_only\api\webui\src\lib\useInView.ts`

- [ ] Run `npm.cmd run build`
- [ ] Confirm the build still succeeds after the lazy loading changes.
