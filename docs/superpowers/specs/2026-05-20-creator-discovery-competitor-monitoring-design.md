# Creator Discovery and Competitor Monitoring Design

Date: 2026-05-20

## Goal

Build a full-platform workflow for two connected product needs:

1. Find creators for promotion and cooperation by keyword, vertical, and tag match.
2. Monitor competitor accounts and discover content opportunities from traffic, keywords, and tag trends.

The first version should support all existing project platforms at the architecture level, while administrators control which platforms and capabilities are enabled. Normal users only see enabled platforms and usable analysis results.

## Product Scope

The product has three normal-user entry points:

- Creator discovery: users select a vertical or use a smart search box, then get creator recommendations ranked by keyword and tag match.
- Competitor monitoring: users add competitor accounts, then review daily traffic composition, new content, hot posts, and tag distribution.
- Keyword opportunities: users review heat, growth, competition strength, and content supply gaps within a selected vertical.

The administrator domain has two configuration areas:

- Platform capabilities: whether a platform can crawl, analyze, monitor, and calculate keyword heat.
- Multi-vertical tag library: verticals, tag groups, tag definitions, keywords, synonyms, negative keywords, weights, and AI prompt hints.

Normal users cannot maintain platform capabilities or tag rules.

## Non-Goals

- Do not hard-code the system for the education vertical.
- Do not expose platform and tag configuration to normal users in the first version.
- Do not let AI create free-form production tags outside the configured tag library.
- Do not make push or restriction judgments as absolute truths. The first version outputs explainable signals such as suspected boost, normal fluctuation, or suspected cooling.
- Do not replace the existing research job, post, comment, and AI analysis foundation.

## Platform Capability Model

All platform-dependent behavior must check administrator configuration.

```text
platform_capabilities
- platform
- enabled
- crawl_search_enabled
- crawl_creator_enabled
- crawl_detail_enabled
- comments_enabled
- analysis_enabled
- daily_monitor_enabled
- keyword_heat_enabled
- rate_limit_per_minute
- max_daily_jobs
- notes
- updated_at
```

Rules:

- If `enabled` is false, normal users cannot create new tasks for that platform.
- If a specific capability is disabled, workflows requiring that capability skip or reject the platform with a clear reason.
- Schedulers and analysis queues re-check platform capability before execution.
- Existing data remains queryable after a platform is disabled.
- Pending scheduled work for a disabled platform should move to `paused_by_platform_config` or an equivalent paused state.

## Vertical and Tag Model

Tags are configured by administrators and grouped by vertical. Education, technology, beauty, health, finance, and future domains use the same model.

```text
verticals
- id
- code
- name
- enabled
- created_at
- updated_at

tag_groups
- id
- vertical_id
- name
- description
- sort_order
- enabled

tag_definitions
- id
- vertical_id
- group_id
- tag_name
- keywords
- synonyms
- negative_keywords
- ai_prompt_hint
- weight
- enabled
- created_at
- updated_at
```

Example tag groups:

- Industry
- Audience
- Identity
- Scenario
- Pain point
- Product
- Commercial intent
- Content format

Examples:

- Education: K12 education, single mother, homework tutoring, school admission anxiety, parent-child companionship.
- Technology: AI tools, office automation, developers, workflow productivity, SaaS trial intent.
- Beauty: sensitive skin, anti-aging, essence, ingredient-focused users, repair, product review.

The same raw keyword can map differently across verticals. For example, "model" can mean AI model in technology and product model or face model in beauty, so tag matching must include vertical context.

## Entity Tags

Posts, comments, and creators receive structured tags.

```text
entity_tags
- entity_type: post | comment | creator
- entity_id
- platform
- vertical_id
- tag_id
- confidence
- source: rule | ai | manual
- evidence_json
- analysis_version
- created_at
```

Evidence is required for useful creator discovery. It should include the matched field, matched text, source post or comment ID, and short context. This keeps recommendations explainable.

## Creator Profile Model

Creator discovery uses a dedicated profile layer built from creator crawls, post history, engagement metrics, and aggregated tags.

```text
creator_profiles
- platform
- creator_id
- display_name
- profile_url
- bio
- follower_count
- following_count
- post_count
- avg_engagement_rate
- hot_post_rate
- recent_post_count_30d
- latest_snapshot_at
- tag_summary_json
- updated_at
```

Daily monitoring stores historical movement.

```text
creator_daily_snapshots
- platform
- creator_id
- snapshot_date
- follower_count
- total_like_count
- total_comment_count
- total_share_count
- new_post_count
- hot_post_count
- tag_distribution_json
- top_posts_json
- created_at
```

Creator tags should not depend only on profile text. They should aggregate recent content, high-engagement posts, comments when available, and AI supplemental analysis.

## Search Intent Model

Creator search supports two user paths:

- Manual vertical selection.
- Smart search box that detects vertical and tags.

```text
search_intents
- raw_query
- detected_verticals
- selected_vertical_id
- required_tags
- optional_tags
- negative_tags
- confidence
- parser_source: rule | ai | hybrid
- created_at
```

If the smart search detects multiple verticals, the system asks the user to select one before searching. For example, "AI education tool" can match education and technology; the search should not mix both by default.

AI may help parse the search intent, but it must choose from enabled verticals and enabled tags. It cannot invent tags for production search.

## Tagging Flow

```text
Collected post/comment/creator
-> Normalize into research data model
-> Rule tagger applies configured keywords, synonyms, negative keywords, and weights
-> AI tagger supplements configured tags where allowed
-> entity_tags stores tag, confidence, source, and evidence
-> creator_profiles aggregates recent post tags and engagement context
-> creator_daily_snapshots records daily movement for monitored creators
```

Rule tagging is the first layer because it is deterministic, cheap, and administrator-controlled. AI tagging supplements semantic cases such as content style, commercial intent, audience identity, and implicit scenario.

AI output rules:

- AI receives only enabled tags for the selected vertical.
- AI must return tag IDs or exact configured tag names.
- AI must return evidence and confidence.
- Low-confidence AI tags are stored but should have less ranking weight.
- AI tags do not override higher-confidence rule tags automatically.

## Creator Discovery Flow

```text
User selects vertical or enters smart query
-> parse search_intent
-> if multiple verticals are detected, user selects one
-> required and optional tags are resolved
-> query creator_profiles, entity_tags, and recent posts
-> calculate creator_match_score
-> return ranked creators with match evidence and sample content
```

Default ranking prioritizes keyword and tag match.

```text
creator_match_score =
  required_tags_coverage * 40%
+ recent_30d_tag_frequency * 25%
+ high_engagement_tag_posts * 15%
+ creator_profile_tag_match * 10%
+ confidence_quality * 10%
```

Follower count, engagement rate, and hot post rate are filters and secondary signals. They should not dominate the default ranking.

Creator result fields:

- Platform.
- Creator display name and profile URL.
- Follower count.
- Recent 30-day post count.
- Match score.
- Matched tags.
- Evidence snippets.
- Representative posts.
- Average engagement rate.
- Hot post rate.

## Competitor Monitoring Flow

```text
User adds competitor account
-> platform capability is checked
-> daily scheduler runs creator crawl
-> new posts and updated creator metrics are stored
-> posts and creator profile are tagged
-> creator_daily_snapshots captures daily movement
-> dashboard shows traffic composition and content patterns
```

Competitor monitoring should show:

- New content count.
- Engagement deltas.
- Hot posts.
- Tag distribution.
- Posting time distribution.
- Content format distribution where available.
- Keyword and tag contribution to traffic.
- Representative posts and evidence.

## Keyword Opportunity Flow

Keyword opportunities are calculated from creator discovery data and competitor monitoring snapshots.

First-version signals:

- Heat: recent content volume and engagement around a tag or keyword.
- Growth: recent increase against historical baseline.
- Competition strength: number and strength of creators or competitors producing similar content.
- Supply gap: high engagement with relatively low creator/content supply.
- Platform signal: suspected boost, normal fluctuation, or suspected cooling based on explainable deltas.

The output should include formula components and evidence instead of only a black-box score.

## API Boundaries

Administrator APIs:

```text
GET /api/admin/platform-capabilities
PUT /api/admin/platform-capabilities/{platform}

GET /api/admin/verticals
POST /api/admin/verticals
PATCH /api/admin/verticals/{id}

GET /api/admin/tag-definitions
POST /api/admin/tag-definitions
PATCH /api/admin/tag-definitions/{id}
```

Creator discovery APIs:

```text
POST /api/creator-search/parse-intent
POST /api/creator-search/search
GET /api/creator-search/{creator_id}/evidence
```

Competitor and opportunity APIs:

```text
POST /api/competitors
GET /api/competitors
GET /api/competitors/{id}/daily-snapshots
GET /api/keyword-opportunities
```

Existing research APIs should continue to own research jobs, collection execution, AI provider configuration, and exports.

## MVP Phases

### Phase 1: Administrator Configuration

Acceptance criteria:

- Administrators can configure platform capabilities.
- Normal user platform options only include enabled capabilities.
- Task creation rejects disabled platform or capability combinations.
- Schedulers check capability settings before running.
- Administrators can configure verticals, tag groups, tag definitions, keywords, synonyms, negative keywords, weights, and AI hints.

### Phase 2: Automatic Tagging

Acceptance criteria:

- Posts, comments, and creators can receive rule-based tags.
- AI supplemental tagging can run against enabled configured tags.
- Each tag result includes confidence and evidence.
- Creator tags aggregate recent content rather than only profile text.
- Tagging can be re-run with a version marker.

### Phase 3: Creator Discovery

Acceptance criteria:

- Users can search by manual vertical plus keywords.
- Users can search through the smart search box.
- Multi-vertical smart search asks the user to choose one vertical before result retrieval.
- Results are ranked by creator match score.
- Each result explains why the creator matched.
- Filters include platform, follower range, recent activity, and engagement rate.

### Phase 4: Competitor Monitoring and Keyword Opportunities

Acceptance criteria:

- Users can add competitor accounts on enabled platforms.
- Daily snapshots are saved.
- Dashboard data includes new content, engagement deltas, hot posts, and tag distribution.
- Keyword opportunities expose heat, growth, competition strength, supply gap, and platform signal with evidence.

## Recommended Implementation Order

1. Platform capability table and repository methods.
2. Vertical and tag definition tables.
3. Admin APIs for platform and tag configuration.
4. Rule tagger.
5. AI supplemental tagger.
6. Entity tag storage and creator profile aggregation.
7. Search intent parser.
8. Creator discovery search API.
9. Competitor account pool and daily snapshots.
10. Keyword opportunity scoring.

## Testing

Unit tests:

- Platform capability validation.
- Disabled platform rejection.
- Vertical and tag definition validation.
- Rule tag matching with keywords, synonyms, negative keywords, and weights.
- Search intent parsing for one vertical and multiple verticals.
- Creator match score calculation.

Integration-style tests:

- A collected post gets tags and evidence.
- A creator profile aggregates tags from recent posts.
- Creator search returns ranked results with evidence.
- Competitor daily snapshot updates traffic and tag distribution.
- Scheduler skips disabled platform capabilities.

No live platform crawling is required for automated tests. Use existing normalized data fixtures and mocked AI provider responses.

## Open Decisions Resolved

- First version supports all platforms at the architecture level.
- Administrators control platform capabilities and tag libraries.
- Normal users cannot edit platform or tag configuration.
- Creator discovery ranking prioritizes keyword and tag match.
- Search can start from manual vertical selection or a smart search box.
- Multi-vertical smart search requires the user to choose one vertical before searching.
- AI tagging is allowed but constrained to configured enabled tags.
