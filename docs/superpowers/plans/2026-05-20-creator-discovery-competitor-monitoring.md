# Creator Discovery and Competitor Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-vertical, full-platform creator discovery and competitor monitoring layer where admins control platform capabilities and tag libraries, while normal users search creators and monitor competitors through enabled capabilities.

**Architecture:** Extend the existing `research/` package instead of creating a parallel product stack. Add admin configuration tables, deterministic and AI-assisted tagging services, creator profile aggregation, creator search APIs, competitor snapshots, and keyword opportunity scoring. Keep existing MediaCrawler platform collectors and research job execution as the data ingestion foundation.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy async ORM, PostgreSQL/SQLite-compatible JSON columns, pytest, existing OpenAI-compatible AI provider abstraction, existing WebUI/API patterns.

---

## File Structure

- Modify `research/models.py`: add platform capability, vertical, tag group, tag definition, entity tag, creator profile, creator daily snapshot, search intent, competitor account, and keyword opportunity snapshot ORM models.
- Modify `research/schema_migration.py`: add compatibility column/table checks for the new research tables where existing deployed databases may already exist.
- Modify `research/schemas.py`: add admin config schemas, tagging schemas, creator search schemas, competitor schemas, and keyword opportunity response schemas.
- Modify `research/repository.py`: add persistence methods for platform capabilities, vertical/tag CRUD, entity tags, creator profiles, snapshots, search intents, competitors, and opportunity data.
- Create `research/tagging.py`: rule tagger, AI tagger wrapper, and tag orchestration.
- Create `research/creator_search.py`: search-intent parsing, multi-vertical detection, match scoring, evidence formatting, and creator result assembly.
- Create `research/competitors.py`: competitor account validation, daily snapshot aggregation, and keyword opportunity scoring.
- Create `api/routers/admin.py`: protected admin-ish API surface for platform capabilities and tag library maintenance. First version follows existing local API style and does not add authentication.
- Create `api/routers/creator_search.py`: normal-user creator discovery endpoints.
- Create `api/routers/competitors.py`: competitor account, snapshot, and keyword opportunity endpoints.
- Modify `api/main.py`: register the new routers.
- Modify `api/routers/research.py`: filter normal user platform options by platform capability where database configuration is available.
- Add tests under `tests/`: model registration, schema validation, rule tagging, search scoring, admin API, creator search API, competitor snapshots, and scheduler capability checks.

## Task 1: Data Model and Schema Migration

**Files:**
- Modify: `research/models.py`
- Modify: `research/schema_migration.py`
- Test: `tests/test_creator_discovery_models.py`
- Test: `tests/test_creator_discovery_schema_migration.py`

- [ ] Add failing model-registration tests asserting these tables are in `Base.metadata.tables`: `research_platform_capabilities`, `research_verticals`, `research_tag_groups`, `research_tag_definitions`, `research_entity_tags`, `research_creator_profiles`, `research_creator_daily_snapshots`, `research_search_intents`, `research_competitor_accounts`, `research_keyword_opportunity_snapshots`.
- [ ] Add failing column tests for required uniqueness and lookup columns: platform capability unique `platform`, vertical unique `code`, tag definition `vertical_id/group_id/tag_name`, entity tag `entity_type/entity_id/tag_id`, creator profile unique `platform/creator_id`, daily snapshot unique `platform/creator_id/snapshot_date`.
- [ ] Implement ORM models using the existing `json_column()` helper and SQLAlchemy style in `research/models.py`.
- [ ] Add migration helper constants and table/column checks in `research/schema_migration.py`; keep it additive and safe for SQLite, PostgreSQL, MySQL, and MariaDB.
- [ ] Run `pytest tests/test_creator_discovery_models.py tests/test_creator_discovery_schema_migration.py -v`.
- [ ] Commit: `feat: add creator discovery data models`.

## Task 2: Pydantic Schemas and Constants

**Files:**
- Modify: `research/enums.py`
- Modify: `research/schemas.py`
- Test: `tests/test_creator_discovery_schemas.py`

- [ ] Add constants for entity types (`post`, `comment`, `creator`), tag sources (`rule`, `ai`, `manual`), parser sources (`rule`, `ai`, `hybrid`), and disabled-job status `paused_by_platform_config`.
- [ ] Add schema tests for platform capability validation, vertical/tag validation, tag source validation, creator search request validation, and competitor account validation.
- [ ] Implement schemas: `PlatformCapabilityUpsert`, `VerticalCreate/Update/Read`, `TagGroupCreate/Update/Read`, `TagDefinitionCreate/Update/Read`, `EntityTagRead`, `CreatorSearchIntentRequest`, `CreatorSearchRequest`, `CreatorSearchResult`, `CompetitorAccountCreate/Read`, `KeywordOpportunityRead`.
- [ ] Validation defaults: enabled booleans default to true for new admin records; platform values must be in `SUPPORTED_RESEARCH_PLATFORMS`; weights are positive integers; confidence is `0.0 <= confidence <= 1.0`.
- [ ] Run `pytest tests/test_creator_discovery_schemas.py -v`.
- [ ] Commit: `feat: add creator discovery schemas`.

## Task 3: Repository Methods

**Files:**
- Modify: `research/repository.py`
- Test: `tests/test_creator_discovery_repository.py`

- [ ] Add repository tests using the existing database test setup for CRUD on platform capabilities, verticals, tag groups, tag definitions, entity tags, creator profiles, competitor accounts, and daily snapshots.
- [ ] Implement list/upsert/get methods for platform capabilities.
- [ ] Implement create/list/update methods for verticals, tag groups, and tag definitions; list methods must support `enabled_only`.
- [ ] Implement bulk upsert for entity tags keyed by entity type, entity id, platform, vertical, tag, source, and analysis version.
- [ ] Implement upsert/get/list for creator profiles and daily snapshots.
- [ ] Implement create/list/update for competitor accounts and list snapshots by competitor.
- [ ] Run `pytest tests/test_creator_discovery_repository.py -v`.
- [ ] Commit: `feat: add creator discovery repositories`.

## Task 4: Admin API for Platform and Tag Configuration

**Files:**
- Create: `api/routers/admin.py`
- Modify: `api/main.py`
- Test: `tests/test_creator_discovery_admin_api.py`

- [ ] Add route tests for `GET/PUT /api/admin/platform-capabilities`, `GET/POST/PATCH /api/admin/verticals`, `GET/POST/PATCH /api/admin/tag-groups`, and `GET/POST/PATCH /api/admin/tag-definitions`.
- [ ] Implement router functions using `require_research_database()` behavior consistent with `api/routers/research.py`.
- [ ] Register router under `/api/admin`.
- [ ] Keep first version local-admin only: no new auth implementation, but isolate under `admin` namespace for future protection.
- [ ] Ensure normal config route `/api/research/config/options` only exposes enabled platforms when SQL research storage is configured and platform capability rows exist; fallback to existing options when no capability rows exist.
- [ ] Run `pytest tests/test_creator_discovery_admin_api.py tests/test_research_api.py::test_research_config_options_include_keyword_platforms -v`.
- [ ] Commit: `feat: add admin platform and tag APIs`.

## Task 5: Rule-Based Tagging

**Files:**
- Create: `research/tagging.py`
- Test: `tests/test_creator_discovery_tagging.py`

- [ ] Add tests for keyword match, synonym match, negative keyword suppression, vertical-specific matching, weighted confidence, evidence JSON shape, and duplicate tag consolidation.
- [ ] Implement `RuleTagger.match_text(entity, vertical, tag_definitions)` that checks title/content/bio/comment text fields and returns tag candidates with `source="rule"`.
- [ ] Evidence JSON must include `field`, `matched_term`, `matched_text`, and `context`.
- [ ] Confidence rule: base `0.6`, add `0.2` for synonym/keyword frequency above one, add up to `0.2` from tag weight normalization, cap at `1.0`; negative keyword match returns no tag.
- [ ] Implement `TaggingService.tag_posts_and_creators(job_id, vertical_id, analysis_version="v1")` using repository methods and existing normalized posts/authors.
- [ ] Run `pytest tests/test_creator_discovery_tagging.py -v`.
- [ ] Commit: `feat: add rule based tagging`.

## Task 6: AI Supplemental Tagging

**Files:**
- Modify: `research/tagging.py`
- Test: `tests/test_creator_discovery_ai_tagging.py`

- [ ] Add mocked-provider tests proving AI receives only enabled tag names/IDs, stores only configured tags, rejects invented tags, preserves confidence/evidence, and does not override stronger rule tags.
- [ ] Implement `AITaggingService` using the existing `OpenAICompatibleProvider` pattern from `research/ai_analysis.py`.
- [ ] Prompt contract: model must return JSON array items with `tag_id`, `confidence`, and `evidence`; service discards unknown tags and malformed entries.
- [ ] Add orchestration method that runs rule tagging first, then AI tagging only when platform capability `analysis_enabled` is true.
- [ ] Run `pytest tests/test_creator_discovery_ai_tagging.py -v`.
- [ ] Commit: `feat: add ai supplemental tagging`.

## Task 7: Creator Profile Aggregation and Match Scoring

**Files:**
- Create: `research/creator_search.py`
- Test: `tests/test_creator_discovery_scoring.py`

- [ ] Add tests for creator aggregation from recent posts, high-engagement tagged posts, profile tag matches, confidence quality, and default match score formula.
- [ ] Implement `aggregate_creator_profile(platform, creator_id, posts, entity_tags)` producing `tag_summary_json`, recent 30-day count, average engagement rate, and hot post rate.
- [ ] Implement `calculate_creator_match_score(required_tags, optional_tags, creator_profile, entity_tags, recent_posts)` with the confirmed weights: required coverage 40%, recent frequency 25%, high-engagement tagged posts 15%, profile tag match 10%, confidence quality 10%.
- [ ] Treat follower count and engagement rate as filters/secondary display fields, not primary ranking inputs.
- [ ] Run `pytest tests/test_creator_discovery_scoring.py -v`.
- [ ] Commit: `feat: add creator aggregation and scoring`.

## Task 8: Search Intent Parsing and Creator Search API

**Files:**
- Modify: `research/creator_search.py`
- Create: `api/routers/creator_search.py`
- Modify: `api/main.py`
- Test: `tests/test_creator_discovery_search_api.py`

- [ ] Add tests for manual vertical search, smart search with one vertical, smart search with multiple verticals requiring user selection, tag resolution from configured keyword/synonym rules, and result evidence.
- [ ] Implement `parse_search_intent(raw_query, selected_vertical_id=None)` as hybrid-ready: rule parser first, AI fallback only when needed and configured.
- [ ] Multi-vertical result returns `needs_vertical_selection=True` with candidate verticals; no search results are returned until `selected_vertical_id` is supplied.
- [ ] Implement `POST /api/creator-search/parse-intent`, `POST /api/creator-search/search`, and `GET /api/creator-search/{creator_id}/evidence`.
- [ ] Search filters: platform, follower min/max, recent activity min, engagement rate min.
- [ ] Run `pytest tests/test_creator_discovery_search_api.py -v`.
- [ ] Commit: `feat: add creator search api`.

## Task 9: Competitor Accounts and Daily Snapshots

**Files:**
- Create: `research/competitors.py`
- Create: `api/routers/competitors.py`
- Modify: `api/main.py`
- Test: `tests/test_competitor_monitoring.py`

- [ ] Add tests for adding a competitor only when platform `enabled` and `daily_monitor_enabled` are true.
- [ ] Add tests for daily snapshot aggregation: new post count, engagement deltas, hot post count, top posts JSON, and tag distribution JSON.
- [ ] Implement competitor account service and endpoints: `POST /api/competitors`, `GET /api/competitors`, `GET /api/competitors/{id}/daily-snapshots`.
- [ ] Implement snapshot builder from existing creator profile, posts, and entity tags. Do not run live crawler inside the endpoint.
- [ ] Run `pytest tests/test_competitor_monitoring.py -v`.
- [ ] Commit: `feat: add competitor monitoring snapshots`.

## Task 10: Keyword Opportunity Scoring

**Files:**
- Modify: `research/competitors.py`
- Test: `tests/test_keyword_opportunities.py`

- [ ] Add tests for heat, growth, competition strength, supply gap, and platform signal classification.
- [ ] Implement scoring from creator profiles, entity tags, and daily snapshots.
- [ ] Platform signal defaults: `suspected_boost` when recent heat and growth both exceed baseline by configured threshold; `suspected_cooling` when both fall below threshold; otherwise `normal_fluctuation`.
- [ ] Response includes score components and evidence post/creator references; do not output an unexplained single score.
- [ ] Add `GET /api/keyword-opportunities` with filters for vertical, platform, date window, and tag IDs.
- [ ] Run `pytest tests/test_keyword_opportunities.py -v`.
- [ ] Commit: `feat: add keyword opportunity scoring`.

## Task 11: Scheduler and Execution Capability Checks

**Files:**
- Modify: `research/scheduler.py`
- Modify: `research/execution.py`
- Test: `tests/test_creator_discovery_capability_checks.py`

- [ ] Add tests that disabled platform capabilities prevent new schedule units, skip existing pending units, and mark skipped work with `paused_by_platform_config`.
- [ ] Add checks before scheduling search/detail/creator crawl units.
- [ ] Add checks before execution claims or starts a unit; use platform capability and required collection mode capability.
- [ ] Keep historical data queryable; do not delete jobs, posts, tags, profiles, or snapshots when a platform is disabled.
- [ ] Run `pytest tests/test_creator_discovery_capability_checks.py -v`.
- [ ] Commit: `feat: enforce platform capabilities`.

## Task 12: WebUI Wiring for First Usable Workflow

**Files:**
- Modify: `api/webui/research.html`
- Modify: `api/webui/research.js`
- Modify: `api/webui/research.css`
- Test: `tests/test_creator_discovery_webui.py`

- [ ] Add lightweight WebUI tests or response smoke tests that confirm creator search and competitor sections are served.
- [ ] Add admin-only sections in the existing research console for platform capabilities and tag definitions; label them as administrator configuration.
- [ ] Add normal-user sections for creator search and competitor list using the new APIs.
- [ ] Keep UI minimal: forms, tables, match evidence, and snapshot summaries. Avoid adding charts until API data is stable.
- [ ] Run `pytest tests/test_creator_discovery_webui.py tests/test_research_api.py -v`.
- [ ] Commit: `feat: wire creator discovery webui`.

## Task 13: Full Verification

**Files:**
- No new files expected.

- [ ] Run focused suite:

```bash
pytest tests/test_creator_discovery_*.py tests/test_competitor_monitoring.py tests/test_keyword_opportunities.py -v
```

- [ ] Run regression suite for existing research APIs and models:

```bash
pytest tests/test_research_api.py tests/test_research_models.py tests/test_research_schema_migration.py tests/test_research_schemas.py -v
```

- [ ] Run build if frontend assets were changed:

```bash
npm.cmd run build
```

- [ ] Manually smoke test API routes with `TestClient` or local server: admin config, parse intent, creator search, competitor creation, snapshots, keyword opportunities.
- [ ] Commit final fixes with a focused message such as `fix: stabilize creator discovery workflow`.

## Acceptance Checklist

- [ ] Admins can enable/disable platform capabilities and configure multi-vertical tag libraries.
- [ ] Normal user platform options respect enabled capabilities.
- [ ] Posts, comments, and creators receive rule-based tags with evidence.
- [ ] AI supplemental tags are constrained to configured enabled tags.
- [ ] Creator profiles aggregate recent content tags and engagement context.
- [ ] Creator search supports manual vertical and smart query entry.
- [ ] Multi-vertical smart search forces vertical selection before returning results.
- [ ] Creator results are ranked by tag/keyword match and explain why each creator matched.
- [ ] Competitor accounts can be monitored through daily snapshots.
- [ ] Keyword opportunities expose heat, growth, competition strength, supply gap, and platform signal with evidence.
- [ ] Existing research collection, AI analysis, and export APIs continue to pass regression tests.
