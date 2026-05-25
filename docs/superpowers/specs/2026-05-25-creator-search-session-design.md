# Creator Search Session Design

## Goal

Persist creator discovery search sessions so the page can restore the latest search after a refresh without forcing the user to rerun the query.

## Scope

- Persist one search session record per executed creator discovery search.
- Persist the result snapshot for that session so restored results are stable even if creator profiles later change.
- Restore the latest session automatically when the creator discovery page loads.
- Turn the existing "保存搜索" button into a real save action for the current session.

## Design

### Data model

- `research_creator_search_sessions`
  - stores query, selected vertical, backend search payload, frontend view state, diagnostics, realtime metadata, progress, current status, saved flag, and result counts.
- `research_creator_search_session_results`
  - stores ordered result snapshots for a session, keyed by session id and rank.

### Backend flow

1. Frontend runs `/api/creator-search/search` as it does today.
2. Frontend immediately posts the executed request, current view state, and returned results to a new persistence endpoint.
3. Backend writes the session row and ordered result snapshots.
4. Frontend stores the returned session id in memory.
5. On page load, frontend requests the latest session and restores filters, controls, diagnostics, and results from the saved snapshot.

### Save semantics

- Every executed search becomes the latest restorable session.
- Clicking `保存搜索` marks the current session as saved; this keeps the button meaningful without forcing a separate manual persistence path.

### Fallback

- If no saved session exists, the page falls back to the current candidate-pool bootstrap behavior.

## Testing

- Repository/API tests for create latest session, load latest session, and save current session.
- Frontend build smoke test.
