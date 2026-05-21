# Frontend Entry And Task Workbench Design

Date: 2026-05-21

## Goal

Improve the current frontend from a feature-list console into a clearer product workflow. This design combines:

- Approach A: unify the frontend entry, navigation, empty states, and backend-unavailable messaging.
- Approach B: make the research task the primary workbench, so users can create, run, monitor, inspect, analyze, and export from one task context.

The change should improve first-use clarity without changing crawler, research, AI, or export backend behavior.

## Current Problems

The app currently exposes both a legacy crawler console and a newer research console. Vite development can land on the legacy page, while FastAPI redirects `/` to `/research`, and the built research page lives under `/static/dist/research.html`. This creates an unclear starting point.

The research console sidebar has many first-level destinations. These entries map to capabilities, but not to the user's natural workflow. Users must infer how configuration, task creation, execution, data browsing, AI analysis, and export connect.

When the backend is unavailable, the page shows low-context HTTP errors and repeats failed API calls. The interface should explain what is unavailable and what the user can do next.

Most frontend behavior is concentrated in one large `main.tsx`, which makes even small experience changes harder to reason about. This design keeps refactoring limited to the touched workflow and avoids a full frontend rewrite.

## Users And Main Workflow

Primary user: a local operator using MediaCrawler to collect platform data, inspect results, run analysis, and export evidence.

Main workflow:

1. Open the web UI.
2. Confirm service and storage readiness.
3. Create or select a research task.
4. Run or schedule the task.
5. Watch progress, units, and logs.
6. Browse collected posts, comments, raw records, and AI results.
7. Run AI analysis or export files from the same task context.

## Design Approach

### A. Unified Entry And Navigation

The research console becomes the primary frontend surface.

Development and production should both make the intended entry obvious:

- `/` in FastAPI continues to route to the research console.
- Vite development should expose the research console without forcing users through the legacy command center.
- The legacy crawler console remains available as an explicit secondary link, for compatibility and direct crawler validation.

The sidebar should become grouped around user intent instead of a flat list. Proposed groups:

- Overview: Growth Overview.
- Workbench: Task Workbench, Data Browser, AI Analysis, Export Center.
- Growth Tools: Audience Filter, Content Tracking, Competitors, Keyword Heat, Backtests, Reports.
- Setup: Keyword Library, Monitor Pools, Config Center, Direct Crawler.

For the first implementation, grouping can be visual rather than a full router rewrite. The active tab model can remain local state.

### B. Task Workbench

Create a task-centered page that replaces the current fragmented "采集任务" experience as the main operational surface.

The workbench should include:

- Task selector and status filter.
- Current task summary: platform, mode, keywords or IDs, date window, schedule status, anonymization status.
- Primary actions: create task, edit task, run task, stop execution, preview plan, schedule, export.
- Execution status: progress, active units, failed units, recent logs.
- Data preview tabs: posts, comments, raw records, AI results.
- Next-step panel: prompts such as "configure storage", "create task", "run task", "view data", "run AI analysis", or "export".

The workbench should not duplicate every advanced data/AI/export screen. It should show previews and deep-link or switch tabs to the full screens when needed.

## Empty And Error States

Backend unavailable:

- Show a single high-level notice near the top: "后端服务不可用".
- Include likely local action: start FastAPI with `uvicorn api.main:app --port 8080 --reload` or the project's documented start command.
- Keep the shell visible, but disable run/export actions that require backend state.

Database not ready:

- Tell the user to open Config Center.
- Keep task creation disabled or explain that task data will not persist until storage is ready.

No task:

- Show a clear primary action: create research task.
- Explain the minimum required fields: topic, platform, collection mode, and keywords/IDs.

Selected task has no data:

- Offer "run task" and "preview plan" first.
- Keep data tabs visible, but display empty states with the correct next action.

## Component Boundaries

Keep the first refactor targeted:

- `api/webui/src/main.tsx` can still host the app shell initially, but new workbench-related UI should be split into smaller components in the same file or a small adjacent module if practical.
- Extract reusable helpers only when they remove duplication in the touched workflow.
- Do not introduce a global state library or routing library in this iteration.
- Do not redesign charts, AI provider configuration, or growth scoring internals in this iteration.

Recommended component units:

- `Sidebar` with grouped navigation.
- `ServiceNotice` for backend/database/module warnings.
- `TaskWorkbenchPage`.
- `TaskSummaryPanel`.
- `TaskActionBar`.
- `TaskDataPreview`.
- `NextStepPanel`.

## Data Flow

Use the existing API client and state loading functions.

The workbench consumes existing state already loaded by `App`:

- `jobs`, `selectedJob`, `selectedJobId`, `stats`, `units`, `events`.
- `posts`, `comments`, `rawRecords`, `aiResults`.
- `databaseReady`, `serviceStatus`, `moduleWarning`, `activityOutput`.
- Existing action handlers for edit, execute, stop, preview, schedule, export.

The implementation should avoid adding new backend endpoints.

## Interaction Rules

Disable destructive or unavailable actions when no task is selected.

Primary action order:

1. If backend unavailable: show service recovery.
2. If database not ready: show setup.
3. If no task: create task.
4. If task has no execution output: preview or run.
5. If task has data: inspect, analyze, export.

The UI should not show raw JSON as the main success feedback when a friendlier summary is possible. It can keep JSON in a collapsible or console-style secondary area for debugging.

## Visual Direction

Keep the existing restrained B2B dashboard style: white panels, muted green accent, compact controls, dense but readable tables.

Adjust hierarchy:

- Workbench top area should read as operational status, not marketing.
- Tables should remain scrollable.
- Cards should not nest inside cards.
- Buttons should use existing lucide icons.
- Mobile should keep grouped sidebar entries usable without horizontal overflow.

## Testing And Verification

Manual checks:

- Vite dev entry opens the research console or clearly points to it.
- FastAPI `/` still reaches the research console.
- `/crawler` still opens the legacy crawler console.
- Backend unavailable state shows one useful notice and does not flood the page with repeated raw errors.
- No-task, no-database, no-data, selected-task, and task-with-data states render coherently.
- Sidebar grouping works on desktop and mobile widths.

Automated checks:

- Run `npm.cmd run build`.
- If practical, add focused unit-level checks only if a test setup already exists for frontend. Do not create a test framework solely for this UI pass.

## Out Of Scope

- Full frontend file/module rewrite.
- New routing library.
- New design system.
- Backend endpoint changes.
- Redesign of AI prompt workflows, charts, or report generation.
- Removal of the legacy crawler console.

## Acceptance Criteria

- Users land on the intended research experience from the normal entry path.
- Legacy crawler console remains reachable but is no longer the accidental first page.
- Sidebar is grouped by workflow and easier to scan.
- A task-centered workbench lets users operate on one selected task without bouncing between pages for common actions.
- Empty and error states tell users the next action.
- Existing core operations still call the same backend handlers.
- The frontend builds successfully.
