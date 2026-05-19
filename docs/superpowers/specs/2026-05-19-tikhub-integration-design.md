# TikHub Integration Design

Date: 2026-05-19

## Goal

Add TikHub as an optional third-party API data source for all platforms already supported by this project: Xiaohongshu, Douyin, Kuaishou, Bilibili, Weibo, Baidu Tieba, and Zhihu.

When enabled, TikHub should replace the current Playwright/CDP login crawler path for these platforms while preserving the existing command line shape, Web API request shape, crawler types, storage options, and downstream analysis/export behavior as much as possible.

## Non-Goals

- Do not add new non-project platforms such as TikTok, Instagram, YouTube, or Twitter/X in this phase.
- Do not rewrite the existing browser-based crawlers.
- Do not download media binaries through TikHub in the first version. Store media URLs only.
- Do not require users to pass account cookies for TikHub mode unless a specific TikHub endpoint requires them later.

## Configuration

Add these settings to `config/base_config.py`:

- `ENABLE_TIKHUB = False`
- `TIKHUB_API_KEY = ""`
- `TIKHUB_BASE_URL = "https://api.tikhub.io"`
- `TIKHUB_TIMEOUT_SECONDS = 30`
- `TIKHUB_MAX_RETRIES = 3`
- `TIKHUB_RETRY_BACKOFF_SECONDS = 2`

The effective API key is resolved in this order:

1. Environment variable `TIKHUB_API_KEY`
2. `config.TIKHUB_API_KEY`

If `ENABLE_TIKHUB=True` and no API key is available, the crawler fails during startup with a clear configuration error.

## Activation Model

The user selected a global replacement switch:

- Existing platform values remain unchanged: `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba`, `zhihu`.
- Existing crawler types remain unchanged: `search`, `detail`, `creator`.
- When `config.ENABLE_TIKHUB` is false, `CrawlerFactory` keeps returning the existing platform crawler.
- When `config.ENABLE_TIKHUB` is true, `CrawlerFactory` returns one shared `TikHubCrawler(platform=config.PLATFORM)`.

This avoids expanding platform names such as `xhs_tikhub` and keeps the Web UI mostly stable.

## Architecture

Create a new package:

```text
media_platform/tikhub/
  __init__.py
  client.py
  core.py
  endpoints.py
  errors.py
  mappers/
    __init__.py
    base.py
    xhs.py
    douyin.py
    kuaishou.py
    bilibili.py
    weibo.py
    tieba.py
    zhihu.py
```

`client.py` owns HTTP concerns:

- Builds `Authorization: Bearer <token>` headers.
- Uses the configured base URL.
- Applies timeout, retry, and backoff.
- Normalizes TikHub response envelopes.
- Raises typed errors for missing API key, authentication failure, rate limiting, unsupported endpoints, validation errors, and upstream failures.

`endpoints.py` owns endpoint registry data:

- Platform.
- Crawler capability: search, detail, creator, comments, sub-comments.
- HTTP method and path.
- Parameter names.
- Pagination strategy.
- Sort mapping where supported.

`core.py` owns crawler flow:

- Dispatches by `config.CRAWLER_TYPE`.
- Enforces `START_PAGE`, `CRAWLER_MAX_NOTES_COUNT`, `CRAWLER_MAX_SLEEP_SEC`, `ENABLE_GET_COMMENTS`, `ENABLE_GET_SUB_COMMENTS`, and `CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES`.
- Calls platform mapper functions.
- Calls existing store modules.
- Writes raw fallback records when existing stores cannot safely accept a response shape.

`mappers/` owns platform-specific data conversion:

- Convert TikHub item/detail/comment/user payloads into the closest existing model/store dictionaries.
- Preserve raw TikHub payloads in an `extra` or `raw_data` field where supported.
- Return a raw fallback record if a required existing-store field cannot be derived.

## Data Flow

Search mode:

1. Split `config.KEYWORDS` by comma.
2. For each keyword, call the platform search endpoint page by page.
3. Map each returned content item to the existing platform store format.
4. Save content items through existing store functions.
5. If comments are enabled, fetch comments for saved item IDs.
6. Respect configured sleep interval between API pages.

Detail mode:

1. Use existing `specified_id` parsing from `cmd_arg`.
2. For each ID or URL, call the platform detail endpoint.
3. Map and save the content item.
4. Fetch comments if enabled.

Creator mode:

1. Use existing `creator_id` parsing from `cmd_arg`.
2. Fetch creator profile where TikHub provides an endpoint.
3. Save creator data through existing store functions when mapping is available.
4. Fetch creator content list.
5. Map and save content items.
6. Fetch comments for content items if enabled.

Comments:

1. Fetch first-level comments up to `CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES`.
2. If `ENABLE_GET_SUB_COMMENTS=True`, fetch sub-comments only where the endpoint registry marks support.
3. If sub-comments are not supported for a platform, log a warning and continue.

## Platform Coverage

The first implementation covers all existing platforms, but capabilities are endpoint-dependent:

- Xiaohongshu: search, detail, creator, comments, sub-comments where available.
- Douyin: search, detail, creator, comments, sub-comments where available.
- Kuaishou: search, detail, creator, comments, sub-comments where available.
- Bilibili: search, detail, creator, comments, sub-comments where available.
- Weibo: search, detail, creator, comments, sub-comments where available.
- Baidu Tieba: search, detail, creator, comments where available.
- Zhihu: search, detail, creator, comments where available.

If TikHub does not expose a stable endpoint for one capability on a platform, the registry marks that capability unsupported. The crawler logs a warning and skips that capability instead of failing the whole run.

## Storage Strategy

Reuse existing platform stores by default:

- `store/xhs`
- `store/douyin`
- `store/kuaishou`
- `store/bilibili`
- `store/weibo`
- `store/tieba`
- `store/zhihu`

If a TikHub response cannot be mapped into the existing store contract without losing important data or causing type errors, write a raw JSONL fallback record through a small TikHub raw writer. Raw fallback records include:

- platform
- crawler_type
- source_keyword where relevant
- entity_type: content, comment, creator, or raw_response
- entity_id if available
- fetched_at
- raw payload

This keeps the run useful even when a platform mapper is incomplete.

## Error Handling

Startup errors:

- Missing API key: fail fast with setup instructions.
- Invalid platform in TikHub mode: fail fast with supported project platforms.

HTTP errors:

- 401 or 403: fail the run with a message about token validity, permissions, or account balance.
- 429: retry using configured backoff, then fail if retries are exhausted.
- 422: fail the current item/page with a validation error and continue where safe.
- 5xx or network errors: retry, then fail the current operation with context.

Capability errors:

- Unsupported search/detail/creator/comment capability: warning and skip the capability.
- Unsupported sub-comments: warning and continue with first-level comments.

Mapping errors:

- Required field missing: write raw fallback and log warning.
- Unexpected payload shape: write raw fallback and log warning.

## CLI and Web API Impact

No new CLI flag is required for first version because activation is config-driven.

The Web API request model can remain unchanged initially. If later needed, the API can expose `enable_tikhub` and `tikhub_api_key` fields, but this design avoids sending API keys through the Web UI by default.

The process manager does not need structural changes. It will continue to run:

```text
uv run python main.py --platform <platform> --type <crawler_type> ...
```

The crawler selected by `main.py` changes based on `config.ENABLE_TIKHUB`.

## Testing

Unit tests:

- API key resolution: environment wins over config.
- TikHub client builds correct Authorization header.
- TikHub client handles 401, 403, 429, 422, and 5xx envelopes.
- Endpoint registry rejects unsupported capability lookups clearly.
- Each platform mapper handles representative minimal payloads.
- Raw fallback writer handles unknown payloads.

Integration-style tests with mocked HTTP:

- Search flow saves mapped content and fetches comments when enabled.
- Detail flow accepts configured IDs and writes raw fallback on mapping failure.
- Creator flow saves creator profile and creator content where endpoints are available.
- Unsupported sub-comment endpoints log warning and do not fail the run.

No live TikHub API calls are required in automated tests. A manual smoke test can be run with a real `TIKHUB_API_KEY` after implementation.

## Rollout

1. Add configuration and API key resolver.
2. Add TikHub client and typed errors.
3. Add endpoint registry.
4. Add raw fallback writer.
5. Add platform mappers.
6. Add `TikHubCrawler`.
7. Wire `CrawlerFactory` to use TikHub when enabled.
8. Add tests with mocked TikHub responses.
9. Run formatting and test suite.

## Open Decisions Resolved

- Scope: existing all seven project platforms.
- API key configuration: environment variable first, config fallback.
- Activation: global `ENABLE_TIKHUB=True` replaces current crawler selection.
- Media binaries: not downloaded in first version.
- Unsupported endpoints: warning and skip, not whole-run failure.
