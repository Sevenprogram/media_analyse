# Creator Realtime Unified Search Design

Date: 2026-05-21

## Goal

Upgrade the creator discovery page so one search can combine local database creator discovery with realtime TikHub discovery from Xiaohongshu and Douyin.

The user can opt into realtime search with a checkbox in the keyword filter form. When enabled, the backend searches local creator profiles first, searches TikHub second, merges the results, labels each result source, and automatically persists newly discovered realtime creators into the local creator profile and candidate pool tables.

## Non-Goals

- Do not replace the existing local search behavior.
- Do not make realtime search the default.
- Do not add a separate TikHub API key input to this page.
- Do not require users to manually approve realtime creators before persistence.
- Do not build a general cross-platform realtime creator search beyond the platforms already selected on this page.

## User Experience

The creator discovery form adds one checkbox:

```text
Realtime search Xiaohongshu/Douyin
```

When unchecked, search keeps the current behavior and uses the database only.

When checked, submitting the form runs a unified search:

1. Query local creator profiles and candidate pool evidence.
2. Query TikHub for selected realtime-supported platforms.
3. Merge local and realtime creator results.
4. Persist realtime creators into local storage.
5. Render the combined list.

Each creator row shows a compact source label:

- `Database`
- `Realtime`
- `Database + Realtime`

If TikHub fails, local results still render. The response includes realtime diagnostics so the UI can show a non-blocking warning such as `Realtime search failed; database results are shown`.

When realtime search is enabled, the search interaction should show visible progress rather than a single loading spinner. The form area displays a compact progress bar and current stage label:

- `Searching database`
- `Searching realtime platforms`
- `Saving creator profiles`
- `Merging results`
- `Complete`

The progress indicator is determinate when the backend can report known stages, and stage-based when exact TikHub page counts are unknown. The user should be able to understand that local results are still being protected even while realtime work is slower.

## Request And Response Shape

Extend `CreatorSearchRequest` with:

```json
{
  "include_realtime": true
}
```

Search results add source metadata:

```json
{
  "source_type": "local",
  "source_labels": ["Database"],
  "realtime_unverified": false
}
```

Valid `source_type` values:

- `local`
- `realtime`
- `mixed`

The top-level response adds diagnostics:

```json
{
  "realtime": {
    "enabled": true,
    "status": "ok",
    "platforms": ["xhs", "dy"],
    "created_profiles": 8,
    "created_candidates": 8,
    "error": null
  }
}
```

`status` values:

- `skipped`
- `ok`
- `partial`
- `failed`

For better interaction feedback, the backend should also expose lightweight progress metadata when practical:

```json
{
  "progress": {
    "stage": "merging_results",
    "label": "Merging results",
    "percent": 85
  }
}
```

For the first implementation this can be request-lifecycle progress calculated by the frontend from known phases. A future enhancement can stream progress through polling or WebSocket events if TikHub searches become long-running.

## Backend Architecture

Keep `/api/creator-search/search` as the single endpoint. It remains responsible for local-only and unified searches.

Add a focused service:

```text
research/realtime_creator_discovery.py
```

This service owns:

- Calling TikHub search endpoints for realtime-supported platforms.
- Extracting creator identity from content search results.
- Fetching or deriving profile fields where possible.
- Scoring realtime creators against the request.
- Upserting creator profiles and candidate pool rows.
- Returning normalized realtime creator results and diagnostics.

`research/creator_search.py` continues to own local search, scoring, and final merged response assembly.

## TikHub Flow

Realtime discovery uses content search as the primary primitive:

1. For each selected platform and query keyword, call TikHub search.
2. Extract author fields from returned notes/videos.
3. Deduplicate authors within the realtime batch.
4. Optionally call creator/profile endpoints when a stable creator id is available.
5. Normalize each author into the same creator result shape used by local search.

Supported first version platforms:

- `xhs`
- `dy`

Other selected platforms are ignored for realtime search and reported in diagnostics as unsupported for realtime.

## Persistence

Realtime creators are automatically persisted after normalization.

Write or update `ResearchCreatorProfile` with:

- `platform`
- `creator_id`
- `display_name`
- `profile_url`
- `bio`
- `follower_count`
- `post_count`
- `recent_post_count_30d`
- `latest_snapshot_at`
- `tag_summary_json.profile_metrics`

Write or update `ResearchCreatorCandidate` with:

- `platform`
- `creator_id`
- `pool_name`: `realtime`
- `vertical_id`: selected vertical when available
- `match_score`
- `matched_tags_json`: keyword and source evidence
- `evidence_json`: representative posts and TikHub metadata
- `notes`: realtime discovery source note

Persistence must be idempotent. Re-running the same search should update the same creator profile/candidate rather than creating duplicate rows.

## Merge And Dedupe

Merge local and realtime results using this identity order:

1. `platform + creator_id`
2. `profile_url`
3. `platform + display_name`

When a creator appears in both local and realtime results:

- Return one row.
- Set `source_type` to `mixed`.
- Set `source_labels` to `["Database", "Realtime"]`.
- Preserve local tag evidence and candidate score where available.
- Fill missing profile metrics from realtime data.
- Include representative realtime posts in `representative_posts` when local evidence is sparse.

When a creator appears only from TikHub:

- Set `source_type` to `realtime`.
- Set `source_labels` to `["Realtime"]`.
- Set `realtime_unverified` to `true`.

## Realtime Scoring

Realtime creator score is lightweight and deterministic:

- Keyword match in title/content/author fields.
- Count of representative matched posts.
- Engagement from likes/comments/collects/shares where present.
- Follower filter compatibility.
- Recent activity compatibility.

The score is capped to 100 and should be conservative. Local results with strong tag evidence should not be displaced by weak realtime hits. Sorting remains by `match_score`, with mixed results naturally inheriting local confidence where available.

## Error Handling

Realtime errors are non-fatal for unified search.

- Missing TikHub key: local results returned, realtime status `failed`.
- TikHub 401/403: local results returned, realtime status `failed`.
- TikHub 429: retry according to existing client behavior, then return local results if exhausted.
- One platform failure: return local results plus successful realtime platform results, realtime status `partial`.
- Unexpected TikHub payload: skip malformed items and include counts in diagnostics.

Local search validation remains strict. If the request itself is invalid, the endpoint should still return a request validation error.

## Frontend Changes

Update `ResearchModulePages.tsx` creator discovery form:

- Add a checkbox bound to `includeRealtime`.
- Send `include_realtime` in the search payload.
- Show source badges on each result row.
- Show a progress bar and current stage label that distinguishes database search, realtime platform search, persistence, merge, and completion when realtime is enabled.
- Show a non-blocking warning if realtime diagnostics report `failed` or `partial`.

The checkbox should be off by default to avoid surprise TikHub usage, latency, and quota consumption.

Progress UI behavior:

- Local-only search can keep a simple loading state.
- Realtime search shows the progress bar immediately after submit.
- The submit button remains disabled while the search is running.
- Existing results remain visible but visually marked as stale or updating until the new search finishes.
- On partial realtime failure, progress reaches complete and the warning explains which realtime source failed.

## Testing

Backend tests:

- Local-only search response remains compatible.
- `include_realtime=true` calls realtime service and merges results.
- Realtime-only creators are persisted to profile and candidate storage.
- Duplicate local/realtime creators merge into one mixed result.
- TikHub failure returns local results with realtime failure diagnostics.
- Unsupported realtime platforms are reported without failing the request.

Frontend tests or smoke checks:

- Checkbox defaults off.
- Search payload includes `include_realtime` only when checked.
- Result badges render for database, realtime, and mixed sources.
- Progress bar advances through database, realtime, persistence, merge, and complete stages.
- Warning appears for failed or partial realtime search.

## Rollout

1. Extend request and result schemas.
2. Add realtime creator discovery service with mocked TikHub tests.
3. Wire unified search into `/api/creator-search/search`.
4. Add persistence and merge behavior.
5. Add frontend checkbox and source badges.
6. Run targeted backend tests and a browser smoke test.
