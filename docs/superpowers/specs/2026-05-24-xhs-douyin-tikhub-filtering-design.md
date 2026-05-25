# XHS + Douyin TikHub Filtering Design

Date: 2026-05-24

## Goal

Add search-time filtering controls for TikHub-backed crawling on Xiaohongshu (`xhs`) and Douyin (`dy`) with these requirements:

- Support time-ordered retrieval.
- Support per-keyword-per-platform result caps.
- Support both preset time windows and exact start/end ranges.
- Prefer filling the requested count even when exact time-range matching is insufficient.
- Keep the implementation explicitly limited to Xiaohongshu and Douyin.

This design covers backend request models, TikHub parameter mapping, crawler behavior, response metadata, frontend controls, and tests.

## Scope

In scope:

- TikHub search crawling for `xhs` and `dy`
- Search-mode crawling only
- API-triggered runs
- Filter controls in the current crawler/research UI entry points that already trigger crawling
- Result metadata that marks items outside the requested exact time range when backfilled

Out of scope:

- Kuaishou, Bilibili, Weibo, Zhihu, Tieba
- Creator-mode and detail-mode filtering changes
- Reworking the entire crawler scheduling system
- Hard guarantee of exact-range-only completeness

## User Requirements

The confirmed requirements are:

- Platforms: Xiaohongshu and Douyin only
- Time range input: both preset options and exact start/end time
- Count semantics: each keyword x each platform has its own max result count
- Fill behavior: prefer filling the target count, even if a minority of returned items fall outside the requested exact time range

Example:

- Keyword A on Xiaohongshu: max 200
- Keyword A on Douyin: max 200
- Keyword B on Xiaohongshu: max 200
- Keyword B on Douyin: max 200

## Capability Summary

TikHub supports native filtering for the target platforms, but not with identical semantics:

- Xiaohongshu search supports:
  - sort order
  - note type
  - published-time preset filter
- Douyin general search supports:
  - sort order
  - published-time preset filter
  - duration filter
  - content type filter

Exact start/end ranges are not exposed as first-class arbitrary range parameters in the target search endpoints. Exact ranges therefore require local filtering after native coarse filtering and pagination.

## Recommended Approach

Use a hybrid model:

- Prefer native TikHub filters whenever the platform supports them.
- Apply local post-filtering for exact start/end ranges.
- Continue pagination beyond the exact-match set when needed to fill the requested count.
- Mark out-of-range items used for fill as fallback results.

This is preferred over a fully local filtering model because it:

- reduces request volume
- uses TikHub-native ranking and windowing where available
- fits the current code structure with moderate changes

## Search Control Model

Introduce a normalized search-control payload for API-triggered crawls:

- `sort_mode`
  - `relevance`
  - `latest`
  - `most_liked`
  - `most_commented`
  - `most_collected`
- `time_preset`
  - `all`
  - `1d`
  - `7d`
  - `30d`
  - `180d`
- `time_start`
  - ISO datetime, optional
- `time_end`
  - ISO datetime, optional
- `max_results_per_keyword_per_platform`
  - positive integer
- `fill_strategy`
  - fixed initially to `prefer_fill`
- `max_extra_pages`
  - positive integer safety guard for deep pagination

Validation rules:

- `time_start` and `time_end` must either both be provided or both omitted.
- `time_start <= time_end`.
- If exact range is provided, `time_preset` remains optional and acts as coarse-filter hint.
- `max_results_per_keyword_per_platform >= 1`.

## Platform Mapping

### Xiaohongshu

TikHub endpoint:

- `/api/v1/xiaohongshu/app/search_notes`

Mapping:

- `sort_mode=relevance` -> `sort_type=general`
- `sort_mode=latest` -> `sort_type=time_descending`
- `sort_mode=most_liked` -> `sort_type=popularity_descending`
- `sort_mode=most_commented` -> `sort_type=comment_descending`
- `sort_mode=most_collected` -> `sort_type=collect_descending`

Preset time mapping:

- `all` -> `filter_note_time=不限`
- `1d` -> `filter_note_time=一天内`
- `7d` -> `filter_note_time=一周内`
- `30d` -> no exact native equivalent, keep `filter_note_time=不限` and rely on local filtering
- `180d` -> `filter_note_time=半年内`

Rule:

- If exact range is present, force `sort_type=time_descending`.
- Use the smallest native preset that is guaranteed not to exclude too much desired data only when it helps reduce over-fetch.
- If there is no safe preset match, keep `filter_note_time=不限`.

### Douyin

TikHub endpoint:

- `/api/v1/douyin/search/fetch_general_search_v1`

Mapping:

- `sort_mode=relevance` -> `sort_type=0`
- `sort_mode=most_liked` -> `sort_type=1`
- `sort_mode=latest` -> `sort_type=2`

Preset time mapping:

- `all` -> `publish_time=0`
- `1d` -> `publish_time=1`
- `7d` -> `publish_time=7`
- `30d` -> no exact native equivalent, use `0` and rely on local filtering
- `180d` -> `publish_time=180`

Rule:

- If exact range is present, force `sort_type=2`.
- For exact ranges without a matching native preset, keep `publish_time=0` and rely on local filtering.

### Unsupported Sort Combinations

Not every sort mode is supported equally across both platforms.

Behavior:

- If the selected platform does not support the requested sort mode, downgrade to the nearest valid mode.
- The API response and UI should surface the effective mode used.

Initial downgrade table:

- Douyin `most_commented` -> `relevance`
- Douyin `most_collected` -> `relevance`

## Retrieval Algorithm

For each keyword and platform pair:

1. Build native TikHub request params from the normalized control model.
2. Fetch pages in order.
3. Map each item to normalized local content.
4. Classify each item:
   - exact-range match
   - outside exact range but otherwise valid candidate
5. Accumulate exact-range matches first.
6. Continue pagination until one of these happens:
   - target count reached
   - no more pages
   - `max_extra_pages` reached
7. If exact-range matches are below target:
   - append outside-range candidates in retrieval order until the target count is met or candidates are exhausted
8. Persist metadata indicating whether each saved item is:
   - `within_requested_time_range=true`
   - `outside_requested_time_range=true`

Ordering rule:

- Preserve retrieval order after native sort is applied by TikHub.
- Do not re-sort locally after filling; use exact matches first, then fallback fill items.

## Count Semantics

The result cap is applied independently for every keyword and platform pair.

Internal counters should be scoped as:

- `counter[(keyword, platform)]`

Do not share caps across:

- different keywords on the same platform
- the same keyword across different platforms

## Data Model Changes

Add optional crawl metadata to normalized content payloads or stored post metadata:

- `requested_sort_mode`
- `effective_sort_mode`
- `requested_time_preset`
- `requested_time_start`
- `requested_time_end`
- `within_requested_time_range`
- `outside_requested_time_range`
- `fill_reason`
  - `exact_match`
  - `fill_to_target`

If schema changes are expensive, these fields can initially live under existing JSON metadata fields rather than top-level columns.

## API Changes

Extend the crawler start request model and any growth-project collection request models that create TikHub-backed search runs.

New request fields:

- `sort_mode`
- `time_preset`
- `time_start`
- `time_end`
- `max_results_per_keyword_per_platform`
- `max_extra_pages`

Compatibility:

- Existing callers remain valid.
- Defaults preserve current behavior:
  - `sort_mode=relevance`
  - `time_preset=all`
  - exact range omitted
  - `max_results_per_keyword_per_platform` falls back to current count field

The API response should echo the effective controls used after platform normalization.

## Frontend Changes

Expose one unified filter panel for Xiaohongshu and Douyin search runs.

Controls:

- sort mode
- preset time range
- optional exact start/end datetime
- per-keyword-per-platform max count

UI behavior:

- Show which filters are supported natively for the selected platform.
- If an exact range is chosen, display a note:
  - exact time range uses local filtering after platform search
- If fallback fill happens, show:
  - number of items outside requested time range
  - that they were added to fill the target count

Do not split the UI into separate XHS and Douyin forms. Use a common model and platform-specific helper text.

## Failure and Safety Rules

Guardrails:

- Cap `max_extra_pages` to prevent runaway pagination and cost blowups.
- Stop early on repeated TikHub validation or rate-limit failures.
- If a platform-normalized request becomes too broad, return a warning in the task log and response metadata.

If exact range is impossible to satisfy:

- return partial exact matches
- then fallback-filled items
- include explicit counts for both groups

## Logging

Add structured logs for:

- requested vs effective search controls
- per-page fetched item counts
- exact-match counts
- fallback-fill counts
- final count per `(keyword, platform)`

This is important because the behavior is intentionally approximate under `prefer_fill`.

## Testing

Minimum automated coverage:

- Xiaohongshu preset latest + 7d mapping
- Douyin preset latest + 7d mapping
- Xiaohongshu exact range with enough exact matches
- Xiaohongshu exact range with fallback fill
- Douyin exact range with fallback fill
- independent caps for multiple keywords and both platforms
- unsupported sort downgrade behavior
- metadata flags on fallback-filled items

Minimum manual verification:

- UI control state and request payloads
- task logs showing effective platform filters
- result list correctly indicating fallback items

## Implementation Notes

Primary files expected to change:

- `media_platform/tikhub/endpoints.py`
- `media_platform/tikhub/core.py`
- `config/base_config.py`
- crawler request schemas and router handlers
- relevant frontend pages/forms that trigger crawling

Implementation should keep the platform-specific mapping logic isolated, rather than scattering `if platform == ...` branches across the UI and router layers.

## Open Decisions Resolved

The following were resolved during design:

- Platforms are limited to Xiaohongshu and Douyin.
- Both preset and exact time range inputs are required.
- Max count applies per keyword x per platform.
- Fill policy is `prefer_fill`, not strict-only.

## Recommendation

Implement this as a focused XHS + Douyin search-control enhancement, not as a generic all-platform filtering framework. The internal model can be extensible, but the rollout should stay narrow until real usage validates the approximation and cost profile.
