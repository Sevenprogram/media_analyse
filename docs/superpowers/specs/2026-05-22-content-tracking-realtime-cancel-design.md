# Content Tracking Realtime Cancel Design

## Scope

Content tracking realtime search needs a visible running strip and a cancel action for the realtime job started by the current content tracking page. Creator discovery and other research workflows are out of scope.

## Behavior

- When content tracking starts realtime search, the UI stores the created `content_realtime_discovery` job id and shows a compact running strip with stage, progress, job id, and a cancel button.
- If another research execution is already running, the UI shows a compact busy strip saying a different task is running. It does not show a cancel button because the task was not started by content tracking.
- Cancel is allowed only for the current content tracking realtime job. The backend verifies the target job exists and has `topic == "content_realtime_discovery"` before attempting to stop it.
- If the target job is the active research execution, the backend stops the crawler and cancels the active execution task. If it is only pending or queued, the backend marks it cancelled.

## Data Flow

1. `POST /api/content-tracking/search-similar` creates the realtime job and returns realtime metadata as soon as the job is accepted.
2. The frontend stores `job_id` in the content tracking page state.
3. `POST /api/content-tracking/realtime-jobs/{job_id}/cancel` cancels only content tracking realtime jobs.
4. After cancellation, the frontend clears the local realtime task state and displays a cancellation message.

## Error Handling

- Busy without a content tracking job id: show "当前已有任务运行中，请稍后再试".
- Cancel wrong topic: return `400`.
- Cancel missing job: return `404`.
- Cancel current job: return `stopping`.
- Cancel inactive content tracking job: return `cancelled`.

## Tests

- Backend tests cover cancelling an active content tracking realtime job, rejecting a wrong-topic job, and returning busy metadata from realtime search.
- Frontend build verifies TypeScript and UI wiring.
