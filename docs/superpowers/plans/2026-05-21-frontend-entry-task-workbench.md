# Frontend Entry Task Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the research console the clear primary frontend and add a task-centered workbench for common research operations.

**Architecture:** Keep the existing React local-state app and backend API contracts. Change only the Vite entry/static HTML path, grouped sidebar rendering, top-level notices, and the task page composition.

**Tech Stack:** React 19, TypeScript, Vite, lucide-react, existing FastAPI proxy endpoints.

---

### Task 1: Unified Dev Entry

**Files:**
- Modify: `D:/program/media_analyse/MediaCrawler/vite.config.ts`
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/index.html`

- [ ] **Step 1: Make Vite build and dev use the same React entry**

Change the Vite rollup input from `api/webui/research.html` to `api/webui/index.html`, and make `index.html` load `./src/main.tsx` during development.

- [ ] **Step 2: Preserve legacy crawler access**

Do not delete `api/webui/research.js` or the legacy command center assets. The legacy page remains reachable from FastAPI `/crawler`.

- [ ] **Step 3: Verify dev entry**

Run: `npm.cmd run dev -- --host 0.0.0.0 --port 5175`

Expected: opening `/static/dist/` or `/static/dist/index.html` shows the React research console, not the legacy command center.

### Task 2: Grouped Navigation

**Files:**
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/src/main.tsx`
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/src/styles.css`

- [ ] **Step 1: Replace flat sidebar item rendering**

Render groups named Overview, Workbench, Growth Tools, and Setup. Keep the same `Tab` union and `setTab` state.

- [ ] **Step 2: Make the workbench tab primary**

Rename the current task entry from "采集任务" to "任务工作台" and keep its `Tab` id as `tasks` to avoid data-flow changes.

- [ ] **Step 3: Add responsive styles**

Add `.nav-group` and `.nav-group-label` styles, and keep mobile nav usable with the existing CSS breakpoints.

### Task 3: Service Notice

**Files:**
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/src/main.tsx`
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/src/styles.css`

- [ ] **Step 1: Add `ServiceNotice`**

Create a component that shows one actionable notice for backend unavailable, database not ready, or module warning.

- [ ] **Step 2: Replace scattered notice rendering**

Render `ServiceNotice` below the topbar. Keep the existing dismiss behavior for module warnings.

- [ ] **Step 3: Disable unsafe task actions**

Pass `serviceAvailable` and `databaseReady` into the task workbench so run/export actions are disabled when state is not usable.

### Task 4: Task Workbench

**Files:**
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/src/main.tsx`
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/src/styles.css`

- [ ] **Step 1: Replace `TasksPage` layout**

Keep `TaskTable`, `UnitList`, and `EventFeed`, but add task summary, next-step guidance, action bar, and data preview sections.

- [ ] **Step 2: Add task summary helpers**

Show selected task platform, mode, input terms, date window, schedule status, anonymization status, and stats.

- [ ] **Step 3: Add task data preview**

Show tabs for posts, comments, raw records, and AI results using existing loaded arrays. Limit previews to a small number of rows and add buttons to switch to full Data, AI, or Export tabs.

- [ ] **Step 4: Keep advanced screens**

Do not remove the Data Browser, AI Analysis, or Export Center pages.

### Task 5: Verification

**Files:**
- Modify only files touched above.

- [ ] **Step 1: Build**

Run: `npm.cmd run build`

Expected: TypeScript and Vite build finish successfully.

- [ ] **Step 2: Browser smoke test**

Run the dev server and inspect the research console with Playwright. Confirm grouped sidebar, service notice, task workbench, and legacy `/crawler` link still exist.

- [ ] **Step 3: Review diff**

Run: `git diff -- api/webui/src/main.tsx api/webui/src/styles.css api/webui/index.html vite.config.ts`

Expected: changes are scoped to entry, navigation, notices, and task workbench.
