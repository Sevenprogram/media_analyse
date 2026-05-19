# Research Crawler Design

Date: 2026-05-19

## Background

This project extends MediaCrawler for a non-commercial political communication research workflow. The goal is not to build an unlimited crawler. The goal is to make platform data collection reproducible, auditable, ethically safer, and usable for downstream analysis.

The first phase keeps the existing MediaCrawler platform crawlers and adds a research task layer above them. We will reuse the existing Weibo and Zhihu keyword collection capabilities, then standardize data, record checkpoints, preserve minimal raw evidence, anonymize users, run configurable AI analysis, and export data plus charts for research reports.

## First Phase Scope

- Platforms: Weibo and Zhihu.
- Collection mode: topic or keyword groups with a declared time window.
- Time filtering: use platform filters when available, but treat normalized `publish_time` filtering as the authoritative rule.
- Comments: enabled by default with limited depth and count.
- Full comment collection: available as an explicit protected option.
- Storage: PostgreSQL as primary storage, SQLite as local fallback, JSONL as raw backup/export format.
- Raw records: saved by default in `minimal` mode, with optional `full` mode.
- Anonymization: enabled by default for author and user identifiers.
- AI analysis: OpenAI-compatible provider configuration through the backend.
- WebUI: research task console, AI configuration, charts, export, and task diagnostics.
- Exports: CSV, JSONL, Excel, `job_report.md`, and chart images.

## Non-Goals

- No commercial use.
- No large-scale crawling that disrupts platform operations.
- No automatic account registration, aggressive anti-detection, or private Pro implementation cloning.
- No Bilibili, Xiaohongshu, Douyin, Kuaishou, or cross-platform network graph in phase one.
- No Cloudflare Workers execution for crawler jobs. Crawlers run locally or on a server.

## Architecture

The design keeps MediaCrawler's current platform modules and adds a new research layer.

```text
Existing MediaCrawler
  media_platform/weibo
  media_platform/zhihu
  store/*
  proxy/*
  api/*

New research layer
  research/
    jobs
    checkpoints
    normalizer
    anonymizer
    raw_records
    export
    ai
    charts
```

The research layer owns task state, standardized schemas, anonymization, AI analysis, report generation, and chart exports. Platform crawlers remain responsible for fetching platform-specific data.

## Data Flow

```text
WebUI creates research_job
-> ResearchJobRunner expands platform + keyword crawl units
-> Existing Weibo/Zhihu crawler collects data
-> raw_records stores minimal source evidence
-> normalizer converts records to unified posts/comments/authors
-> anonymizer hashes user identifiers
-> checkpoint records progress
-> AI jobs analyze selected data
-> charts and job_report.md are generated
-> exports are written to exports/research_job_<id>/
```

## Database Model

The first phase adds research tables rather than replacing existing platform tables.

### research_jobs

Stores the reproducible research task definition.

- `id`
- `name`
- `topic`
- `platforms`
- `keywords`
- `start_date`
- `end_date`
- `status`
- `comment_policy`
- `raw_record_mode`
- `anonymize_authors`
- `created_at`
- `updated_at`

### crawl_checkpoints

Stores resumable progress by job, platform, keyword, and cursor.

- `id`
- `job_id`
- `platform`
- `keyword`
- `cursor_type`
- `cursor_value`
- `last_publish_time`
- `status`
- `updated_at`

### crawl_events

Stores task logs and diagnostic events.

- `id`
- `job_id`
- `platform`
- `event_type`
- `message`
- `stats_json`
- `created_at`

### raw_records

Stores source traceability.

- `id`
- `job_id`
- `platform`
- `source_type`
- `source_id`
- `source_url`
- `payload_hash`
- `payload_json`
- `fetched_at`
- `parser_version`

Default mode is `minimal`, with only necessary source fields and metadata. `full` mode is available for debugging or method review.

### research_authors

Stores anonymized author metadata.

- `id`
- `job_id`
- `platform`
- `author_hash`
- `raw_author_id_encrypted`
- `display_name_hash`
- `profile_url_hash`
- `metrics_json`
- `created_at`

Raw author mapping is disabled by default and should stay local when enabled.

### research_posts

Stores normalized posts, answers, questions, notes, or videos.

- `id`
- `job_id`
- `platform`
- `platform_post_id`
- `author_hash`
- `title`
- `content`
- `url`
- `publish_time`
- `engagement_json`
- `raw_record_id`
- `created_at`

### research_comments

Stores normalized comments and replies.

- `id`
- `job_id`
- `platform`
- `platform_comment_id`
- `platform_post_id`
- `parent_comment_id`
- `author_hash`
- `content`
- `publish_time`
- `like_count`
- `raw_record_id`
- `created_at`

### AI Tables

`ai_provider_configs`

- `id`
- `name`
- `base_url`
- `api_key_encrypted`
- `model`
- `timeout`
- `max_concurrency`
- `default_params_json`
- `enabled`

`ai_prompt_templates`

- `id`
- `name`
- `task_type`
- `platform`
- `prompt_text`
- `output_schema_json`
- `version`
- `enabled`

`ai_analysis_jobs`

- `id`
- `research_job_id`
- `task_type`
- `scope`
- `status`
- `provider_config_id`
- `prompt_template_id`
- `created_at`

`ai_analysis_results`

- `id`
- `analysis_job_id`
- `target_type`
- `target_id`
- `result_json`
- `model`
- `prompt_version`
- `created_at`

AI results are stored separately from source data so analysis can be rerun with different prompts or models.

## Task Execution

The first phase adds a `ResearchJobRunner` that wraps existing crawler behavior.

```text
1. Load research_job.
2. Split into crawl units by platform and keyword.
3. Load checkpoint for each unit.
4. Call existing platform crawler/client.
5. Persist raw_records.
6. Normalize records into research_posts/comments/authors.
7. Apply authoritative publish_time filtering.
8. Update checkpoint and crawl_events.
9. Generate charts and job_report.md after completion.
```

Execution should be sequential in phase one. This improves reproducibility and reduces platform risk. Concurrency can be added later after task state, rate limits, and recovery behavior are stable.

## Job States

- `pending`
- `running`
- `paused`
- `failed`
- `completed`
- `cancelled`

## Failure Handling

- Single record parse failure: write `crawl_events`, skip record, continue.
- Page request failure: retry with bounded attempts, then mark the crawl unit checkpoint as failed.
- Login expiration: pause the job and require manual re-login.
- AI provider failure: fail only the AI job, not the data collection job.
- Export failure: keep collected data and record the export error.

## Comment Collection Policy

Default policy:

```text
enable_comments: true
comment_limit_per_post: 100
enable_sub_comments: false
sub_comment_limit_per_comment: 0
```

Full comment policy:

```text
full_comment_crawl: true
comment_limit_per_post: null
enable_sub_comments: true
sub_comment_limit_per_comment: null
```

Full comment collection requires:

- Checkpointing enabled.
- Explicit rate limit.
- `max_posts_per_job` or `stop_after_hours`.
- A research note explaining why full collection is needed.

## Raw Records

Raw record settings:

```text
save_raw_records: true
raw_record_mode: minimal | full
```

`minimal` mode is the default. It stores the source ID, URL, fetch time, payload hash, parser version, and necessary raw fields. `full` mode stores fuller payloads for debugging and review, but should be used sparingly.

## Anonymization

Default settings:

```text
anonymize_authors: true
author_hash_salt: .env value
save_author_raw_mapping: false
```

Author hashes should use HMAC over platform-specific identifiers. Exports should include `author_hash`, not raw platform identifiers. If raw mappings are enabled, they should remain local and should not be included in default exports.

## AI Analysis

The AI layer uses an OpenAI-compatible `/v1/chat/completions` API.

Provider configuration:

- Provider name.
- Base URL.
- API key.
- Model.
- Timeout.
- Max concurrency.
- Max tokens.
- Temperature.
- Enabled tasks.

First phase task types:

- `sentiment`
- `stance`
- `topic_tags`
- `summary`
- `controversy_points`
- `argument_structure`
- `comment_digest`

AI flow:

```text
research_posts/comments
-> filter by job, platform, keyword, and time window
-> anonymize
-> batch
-> apply prompt template
-> call provider
-> validate JSON response
-> write ai_analysis_results
```

AI should process anonymized data only. Results must record model, prompt version, and creation time.

## WebUI

The WebUI remains a research console, not a marketing dashboard.

Pages:

- Research job list.
- Create/edit research job.
- Job detail with status, checkpoints, events, counts, and errors.
- AI provider configuration.
- Prompt template configuration.
- AI analysis job runner.
- Chart dashboard.
- Export page.

## Charts

Interactive charts should use ECharts in the WebUI. Report exports should include static PNG by default and optional SVG.

First phase charts:

- Platform post/comment counts.
- Daily or hourly post trend.
- Daily or hourly comment trend.
- Keyword hit ranking.
- Time-window inside/outside ratio.
- Engagement metric distributions.
- Top posts or answers.
- High-engagement timeline.
- Sentiment distribution.
- Stance distribution.
- Topic tag ranking.
- Controversy point statistics.
- Weibo vs Zhihu comparison.
- Crawl success/failure counts.
- Missing field ratios.
- Parse failure reason ranking.

Not included in phase one:

- Account relationship network graph.
- Propagation path graph.
- Geographic map.
- Real-time big-screen display.

## Export

Exports should be written under:

```text
exports/
  research_job_<id>/
    posts.csv
    comments.csv
    authors.csv
    ai_results.jsonl
    raw_records.jsonl
    job_report.md
    charts/
      platform_counts.png
      post_trend.png
      comment_trend.png
      sentiment_distribution.png
      stance_distribution.png
```

`job_report.md` should include:

- Research job configuration.
- Platforms and keywords.
- Time-window strategy.
- Comment policy.
- Raw record mode.
- Anonymization policy.
- Data volume statistics.
- Collection error summary.
- AI provider, model, and prompt versions.
- Chart image references.
- Export timestamp.

## Deployment

Crawler execution should run locally or on a server.

Recommended phase one setup:

```text
Development:
  Windows machine
  PostgreSQL cloud database
  SQLite fallback
  local exports folder

Research collection:
  Linux VPS or lab server
  PostgreSQL
  persistent exports volume
```

Cloudflare can be used for domain, access control, or Hyperdrive if connecting to an external PostgreSQL-compatible database. Cloudflare D1 should not be treated as PostgreSQL.

## Compliance and Research Boundaries

- Respect platform terms and robots rules where applicable.
- Keep collection rates conservative.
- Avoid unnecessary personal data storage.
- Enable anonymization by default.
- Record the research purpose and collection configuration.
- Avoid large-scale collection that disrupts platform operations.
- Do not implement account registration automation or aggressive restriction bypassing.

## Acceptance Criteria

Phase one is complete when:

- A research job can be created for Weibo and Zhihu with keyword groups and a time window.
- The job records checkpoints and can resume after interruption.
- Posts, comments, authors, raw records, and crawl events are persisted.
- `publish_time` filtering is applied consistently after normalization.
- Default comment limits work, and full comment mode requires guardrails.
- Author identifiers are anonymized by default.
- PostgreSQL works as primary storage and SQLite works as fallback.
- An OpenAI-compatible AI provider can be configured and tested.
- AI analysis jobs can run against anonymized data and save results.
- The WebUI shows task status, logs, statistics, and charts.
- CSV, JSONL, Excel, `job_report.md`, PNG charts, and optional SVG charts can be exported.
