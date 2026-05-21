# Background Task Center Design

## Goal

Add a left-sidebar page for managing background work that is running inside the current Web backend process.

The page should answer three operator questions:

1. What is running now?
2. What is queued next?
3. Which running or queued tasks can I cancel safely?

This feature does not manage independently launched `research.worker` or scheduler processes. It may show persisted research jobs that were created by this Web backend, but cancellation only applies to tasks that still have an in-process handle.

## Scope

In scope:

- Add a new sidebar entry: `后台任务`.
- Add a new frontend page that polls current process task state.
- Add a unified backend task-center API.
- Show and cancel these current-process tasks:
  - standalone crawler process managed by `crawler_manager`;
  - active research execution task;
  - in-memory research execution queue;
  - growth project collection runs that use the same research execution queue;
  - creator search tasks stored in `CREATOR_SEARCH_TASKS`;
  - content realtime discovery jobs that use research execution;
  - AI analysis tasks started from the Web backend after adding an in-memory task registry.

Out of scope:

- Killing external worker or scheduler OS processes.
- Persisting a durable background task table.
- Recovering in-memory task progress after backend restart.
- Bulk cancel all tasks.
- Editing task parameters from the task center.

## User Experience

The page appears in the left sidebar near existing operational pages, after `任务工作台` and before `增长机会决策`.

The page has:

- Summary metrics: running, queued, cancellable, recent failures.
- Type filters: all, crawler, collection, creator search, content search, AI analysis.
- A task list with title, type, status, progress, source, related job id, timestamps, and latest message.
- A cancel button only when the backend reports `cancellable: true`.
- A details area or expandable row for task metadata and recent messages.

The page polls every 2 seconds while open. A manual refresh button remains available. Cancel actions show a confirmation dialog before sending the request.

## Unified Task Model

The backend returns tasks in a normalized shape:

```json
{
  "id": "research-execution:128",
  "type": "research_execution",
  "title": "Research execution #128",
  "status": "running",
  "progress": {
    "percent": 42,
    "stage": "crawler",
    "label": "Crawler running"
  },
  "source": "growth_project",
  "started_at": "2026-05-22T10:00:00Z",
  "updated_at": "2026-05-22T10:03:00Z",
  "cancellable": true,
  "cancel_reason": null,
  "related_job_id": 128,
  "detail": {
    "platform": "xhs",
    "project_id": "example-project"
  }
}
```

Task ids are stable within the current backend process and use a typed prefix:

- `crawler:current`
- `research-execution:{job_id}`
- `research-queue:{job_id}`
- `creator-search:{task_id}`
- `ai-analysis:{analysis_job_id}`

Content realtime discovery and growth project collection reuse `research-execution:*` or `research-queue:*` ids, with `source` and `detail` distinguishing where the task came from.

## Backend API

Add a new router, mounted under `/api/background-tasks`.

Endpoints:

- `GET /api/background-tasks`
  - Returns `{ "tasks": TaskCenterItem[], "summary": TaskCenterSummary }`.
  - Aggregates from process memory and existing manager state.

- `POST /api/background-tasks/{task_id}/cancel`
  - Cancels a cancellable task.
  - Returns `{ "status": "cancelled" | "stopping" | "not_cancellable", "task": TaskCenterItem | null }`.
  - Uses task id prefix to route the cancellation.

The router should not expose secrets, cookies, prompt contents, or raw request payloads. `detail` should contain only operational metadata useful for identifying the task.

## Backend Aggregation Sources

### Crawler

Use `crawler_manager.get_status()` and `crawler_manager.logs`.

Cancellation:

- Call `crawler_manager.stop()`.
- Return `stopping` if a process existed.

### Research Execution

Use the module-level state in `api.routers.research`:

- `_research_execution_task`
- `_research_execution_job_id`
- `_research_execution_queue`

The task center should reuse helper functions from the research router or move the state helpers into a small service module if direct imports would create awkward coupling.

Cancellation:

- For `research-execution:{job_id}`:
  - call `crawler_manager.stop()`;
  - cancel `_research_execution_task`;
  - update the research job status to `cancelled`;
  - create a crawl event describing cancellation.
- For `research-queue:{job_id}`:
  - remove the queued item from `_research_execution_queue`;
  - update the research job status to `cancelled`;
  - create a crawl event describing queue cancellation.

### Growth Project Collection

Growth project collection does not need a separate execution engine. It is shown as research execution or queue items whose queue metadata includes `project_id`, or whose job topic maps to a growth project id.

Cancellation is the same as research execution. If the task maps to a growth project, update the growth project collection status to `stopped` and recommended action to `start_collection`.

### Creator Search

Use `CREATOR_SEARCH_TASKS`.

Cancellation:

- For running or pending tasks, set status to `cancelled`.
- Update progress to a cancelled stage.
- This follows the existing creator-search cancel endpoint semantics.

Limitation:

- If a realtime platform request is already inside a lower-level call, cancellation is cooperative and takes effect at the next status check.

### Content Realtime Discovery

Content realtime discovery creates research jobs and starts research execution, so it is represented by the research execution or queue entries. `source` should be `content_search` when the job topic is `content_realtime_discovery`.

Cancellation is the same as research execution.

### AI Analysis

Current AI analysis starts an `asyncio.create_task(runner.run(...))` without storing the task handle. Add a small in-memory registry in the research router or a new service:

- keyed by `analysis_job_id`;
- stores the asyncio task, created time, updated time, and latest known status;
- removes or marks terminal tasks after completion.

Cancellation:

- Cancel the registered asyncio task.
- Set `ai_analysis_jobs.status` to `cancelled`.
- Create a research event on the related research job.

The AI runner should handle `asyncio.CancelledError` by updating status to `cancelled` before re-raising or returning.

## Status Semantics

Use these normalized statuses:

- `queued`
- `running`
- `stopping`
- `completed`
- `failed`
- `cancelled`
- `unknown`

Only `queued` and `running` tasks are cancellable by default. A task may still set `cancellable: false` if the backend lacks a live handle.

## Error Handling

If cancellation races with natural completion:

- Return the latest known task state.
- Do not treat "already completed" as a server error.

If a task id is unknown:

- Return `404`.

If a task exists but is not cancellable:

- Return `409` with a clear reason.

If stopping the crawler fails:

- Return `502` or `500` and include a concise operational error.
- Keep the task visible until the next poll resolves the state.

## Testing

Backend tests:

- Aggregates crawler status into a normalized item.
- Aggregates research queue entries.
- Cancels a queued research job and updates status to `cancelled`.
- Cancels a running research execution by calling the crawler manager and cancelling the task.
- Aggregates creator search tasks and delegates cancellation.
- Registers and cancels AI analysis tasks.
- Does not mark unknown or completed tasks as cancellable.

Frontend tests or focused smoke checks:

- Sidebar contains `后台任务`.
- Page renders summary metrics and task rows from mocked API data.
- Cancel button is hidden or disabled when `cancellable` is false.
- Cancel confirmation calls the unified cancel endpoint and refreshes the list.

Manual verification:

- Start the dev server.
- Open `/research`.
- Start a creator search task and confirm it appears.
- Start or enqueue a growth project collection and confirm running/queued state appears.
- Cancel a queued collection and confirm the job changes to `cancelled`.
- Run build after implementation.

## Risks

- Process-local task state is intentionally volatile. The UI must state that it only manages current Web backend tasks.
- Research execution state currently lives as module-level variables. The implementation should keep changes small but may need helper functions to avoid fragile cross-router imports.
- AI cancellation is cooperative. In-flight provider requests may not stop instantly, but the registry should mark the task cancelled and prevent further processing.
- Existing frontend text encoding appears inconsistent in some files. New UI text should be written as normal UTF-8 Chinese and verified in the browser.

## Acceptance Criteria

- A new `后台任务` item appears in the left sidebar.
- The new page lists current-process background tasks through one unified API.
- The page distinguishes running, queued, completed, failed, and cancelled states.
- The page exposes cancel actions only for tasks the backend can cancel.
- Cancelling a running crawler-backed task stops the crawler process and marks the related job cancelled where applicable.
- Cancelling a queued collection removes it from the queue and marks the job cancelled.
- Cancelling a creator search task updates its status to cancelled.
- Cancelling an AI analysis task updates the analysis job status to cancelled.
- External workers and schedulers are not killed or presented as cancellable.
