# Growth Intelligence Phase One Design

Date: 2026-05-20

## Summary

This design defines the first deliverable phase for the research console as a growth intelligence system. The phase prioritizes four business goals:

1. Discover creators from configured keyword groups, such as `K12教育 + 单亲妈妈`, and move selected creators into monitor pools.
2. Locate keywords from text, video metadata, post links, or content samples, then search similar content and track it over time.
3. Monitor selected competitor accounts daily and split their traffic composition by keyword, tag, content type, posting time, and hit rate.
4. Calculate keyword heat and platform push/cooldown signals with scores and evidence.

The system must stay configurable. Keywords, verticals, scene packs, AI provider settings, crawler platform choices, monitor cadence, and automation rules must be managed in the UI rather than hard-coded.

## 已确认的中文业务设计

### 核心流程

关键词发现达人形成一个闭环：

1. 输入关键词和筛选条件。
2. 先查本地达人画像和历史采集数据。
3. 如果开启“实时发现”，再触发平台关键词搜索爬虫。
4. 从搜索结果和已采集内容里抽取达人信息。
5. 计算达人匹配分，补充地区、简介、认证、最近发布时间、联系方式线索等指标。
6. 生成候选达人列表。
7. 手动勾选、加入 Top N，或使用自动化规则。
8. 加入到某个监控池。
9. 系统按监控池创建或更新达人主页采集任务。
10. 可选择“加入并立即爬取”，立即执行同一个长期监控任务一次。

### 监控池任务策略

长期监控采用“按监控池分组任务”：

- 一个监控池代表一个主题或业务目标，例如 `K12教育达人池`。
- 池内可以包含多个平台、多个达人。
- 系统为监控池创建或更新 `collection_mode="creator"` 的研究任务。
- 任务的 `creator_ids` 来自池内达人。
- 默认频率：每 12 小时一次，也就是每天 2 次。
- 可自定义频率。
- 评论策略创建时可选：不采集 / 一级评论 / 一级评论 + 子评论。
- “立即爬取”直接执行这个监控任务，不额外创建一次性任务。

### 实时发现

实时发现默认关闭，必须显式开启：

- 平台范围：表单选择的平台优先；未选择则使用全局默认平台。
- 默认异步执行，页面显示发现任务状态。
- 提供“等待完成并刷新”按钮。
- 实时发现完成后刷新候选达人列表。

### 自动化选项

高级自动化可开启，默认关闭：

- 模式：待确认队列 / 直接加入监控，可切换。
- 默认：待确认队列。
- Top N 默认 10。
- 最低匹配分默认 80。
- 近 30 天最低发帖数默认 3。
- 粉丝数范围可选。
- 默认排除已监控达人。
- 自动加入时也使用监控池分组任务。
- 可选择是否“加入并立即爬取”。

### 赛道词库与 AI 关键词扩展

- 词库采用“赛道 + 人群/场景包”两层结构。
- 默认单选场景包，但允许多选。
- 主关键词必须命中，辅助关键词加分。
- 词库支持前端手动维护，也支持 CSV/Excel 导入导出。
- 前端新增 AI 关键词扩展功能：输入一个赛道关键词，AI 给出同类需要监控的关键词。
- AI 输出包含关键词、监控理由、平台适配建议。
- AI 生成结果必须人工确认后才能写入正式词库。
- 4Router 通过 OpenAI 兼容接口接入，作为 AI Provider 的一种配置。

### 老板四类目标的一期取舍

- A：关键词筛选达人，作为一期主闭环之一。
- B：内容追踪进入一期完整闭环，支持输入文字内容/视频内容/链接，定位关键词、搜索同类内容、创建追踪任务并持续分析。
- C：友商监控做结构拆分版，包含关键词、标签、内容类型、发布时间、爆款率。
- D：关键词热度与推流/限流判断由我们定义，输出标签 + 分数 + 证据解释，并同时展示 24 小时 vs 7 日均值、7 日 vs 30 日均值。

## Product Scope

Phase one includes:

- Vertical and scene-pack keyword library.
- AI keyword expansion through an OpenAI-compatible provider, including 4Router.
- Creator discovery with local-first search and optional real-time crawler discovery.
- Candidate creator scoring, evidence, and confirmation workflow.
- Monitor pools grouped by business goal.
- Add to monitor and add-and-crawl-now actions.
- Content keyword extraction from text, video metadata, post links, or manually pasted content samples.
- Similar content search and recurring content tracking tasks.
- Content tracking analysis for keyword hits, similar-content clusters, engagement trends, creator overlap, and AI summaries.
- Advanced automation options with manual review or direct monitoring modes.
- Competitor monitoring with traffic composition breakdown.
- Keyword heat and push/cooldown model with label, score, and evidence.

Phase one does not include:

- Deep comparison between competitor accounts and owned creator pools.
- Fully automatic recurring discovery without human-configured thresholds.
- Heavy video frame/audio analysis beyond metadata, captions, OCR, transcript, or text available through crawler sources. Phase one can store these text-derived fields when available, but does not require a full media-processing pipeline.

## Existing Foundation

The codebase already contains useful primitives:

- `research_jobs` with `collection_mode=search/detail/creator`.
- `creator-search` APIs for intent parsing, creator profile search, candidate pools, and export.
- `research_creator_profiles`, `research_creator_candidates`, `research_competitor_accounts`, and daily snapshot tables.
- Crawl unit scheduling and execution through `ResearchScheduler`, `ResearchExecutionManager`, and `crawler_manager`.
- Platform capabilities, global defaults, keyword sets, AI providers, prompts, and export surfaces.
- React research console with pages for overview, creator/audience workflow, direct crawler, competitor monitoring, keyword heat, AI analysis, and export.

The new work should extend these primitives instead of creating a separate crawler or analytics stack.

## Vertical Keyword Library

The keyword library uses two levels:

- Vertical: a broad business category, such as `K12教育`, `美妆护肤`, or `科技数码`.
- Scene pack: a specific audience, scenario, or demand cluster under a vertical, such as `单亲妈妈`, `鸡娃家庭`, `家庭教育焦虑`, or `初中升学`.

Each scene pack contains:

- Primary keywords: required matches for creator discovery.
- Secondary keywords: scoring boosters.
- Synonyms and aliases: recall expansion.
- Negative keywords: exclusion or score penalty.
- Platform-adapted keywords: platform-specific wording for Xiaohongshu, Douyin, Weibo, Zhihu, Bilibili, and other supported platforms.
- Weight: scoring contribution.
- Usage flags: creator discovery, content tracking, keyword heat, competitor analysis.

Search behavior:

- Default search selects one scene pack.
- Users can switch to multi-select scene packs.
- Single-pack matching requires a primary keyword match and then adds score for secondary and platform-adapted keywords.
- Multi-pack matching accepts candidates that satisfy any selected pack's primary match rule. Candidates matching multiple packs receive additional score.
- Candidate evidence must show matched vertical, scene packs, primary keywords, secondary keywords, negative keyword hits, and source posts.

## AI Keyword Expansion

The UI adds an AI keyword expansion panel in the keyword library workflow.

Input:

- Vertical keyword or existing vertical name.
- Optional scene-pack hint.
- Optional target platforms.
- Optional business goal, such as creator discovery, content tracking, heat monitoring, or competitor analysis.

AI output:

- Primary keywords.
- Secondary keywords.
- Synonyms and aliases.
- Negative keywords.
- Platform-adapted keywords.
- Monitoring reason for each keyword or group.
- Recommended weight.
- Recommended usage flags.

AI suggestions must not automatically enter the official keyword library. The user must review, edit, select, and save suggestions manually.

4Router integration:

- Use existing AI Provider configuration where possible.
- 4Router can be configured as an OpenAI-compatible provider.
- Base URL: `https://4router.net/v1`.
- Authentication: Bearer API key.
- Recommended model is user-configurable. The app should not hard-code one model.
- API keys must be stored server-side through provider configuration and never exposed in client code.

## Creator Discovery Flow

Creator discovery is a closed loop:

1. User enters keywords and filter conditions.
2. The system searches local creator profiles, historical posts, tags, and candidate pools first.
3. If real-time discovery is enabled, the system triggers platform keyword search crawling.
4. The crawler collects content and author information.
5. The system extracts or updates creator profiles from collected authors and posts.
6. Candidate creators are scored and enriched with business metrics.
7. Candidate list is displayed for manual selection, Top N addition, or automation.
8. Selected creators are added to a monitor pool.
9. The system creates or updates creator-mode research jobs for that monitor pool.
10. If the user chooses add-and-crawl-now, the same long-term monitor job is executed immediately once.

Real-time discovery:

- Default is off.
- It must be explicitly enabled by the user.
- Platform selection uses search-form platforms first.
- If the form does not select platforms, the system falls back to global default platforms.
- If neither exists, the UI blocks execution and asks the user to select platforms or configure defaults.
- Default execution is asynchronous and shows discovery task status.
- A secondary action `等待完成并刷新` waits for completion and refreshes candidates.

Candidate fields:

- Avatar when available.
- Display name.
- Platform.
- Region.
- Bio.
- Verified status.
- Follower count.
- Recent post count in the last 30 days.
- Average engagement rate.
- Hot post rate.
- Latest post time.
- Contact clues.
- Match score.
- Matched vertical and scene packs.
- Matched keywords and evidence posts.
- Monitoring status.

## Monitor Pools

Long-term creator monitoring is grouped by monitor pool.

Pool behavior:

- A monitor pool represents a topic or business goal, such as `K12教育达人池`.
- One pool can include multiple platforms and multiple creators.
- Adding creators creates or updates a research job with `collection_mode="creator"`.
- The research job's `creator_ids` come from creators in the pool.
- The default schedule is every 12 hours, meaning two runs per day.
- Users can customize frequency with presets or a custom minute value.
- Comment policy is selected during monitor creation:
  - no comments
  - first-level comments
  - first-level comments plus sub-comments
- Default comment policy is first-level comments.
- Add-and-crawl-now executes the same long-term monitor job immediately and does not create a separate one-off task.

Monitor pool actions:

- Create pool.
- Add selected creators.
- Add Top N creators.
- Add and crawl now.
- Pause or resume a pool.
- Edit frequency and comment policy.
- View latest crawl status and new posts.

## Automation Options

Advanced automation is available but off by default.

Rules:

- Mode switch:
  - pending confirmation queue
  - direct add to monitoring
- Default mode is pending confirmation queue.
- Default Top N is 10.
- Default minimum match score is 80.
- Default minimum recent post count is 3 in the last 30 days.
- Optional follower count range.
- Exclude already monitored creators by default.
- Default monitor frequency is every 12 hours.
- Default comment policy is first-level comments.
- Automation can choose add-only or add-and-crawl-now.

The UI must clearly show how many creators will be affected before applying automation.

## Content Tracking Flow

Content tracking is the full phase-one implementation for business goal B: locate keywords from content, find similar content, and monitor the trend over time.

### Content Inputs

The content tracking page supports multiple input types:

- Plain text pasted by the user.
- Video title, description, caption, OCR text, or transcript when available.
- Post or video URL.
- Platform content ID.
- Uploaded CSV/Excel rows containing titles, descriptions, URLs, or content IDs.
- Existing collected post selected from the data browser.

The UI should clearly label which fields are user-provided and which fields are collected from a platform. Video media itself is not required for phase one unless text metadata, OCR, captions, or transcripts are already available.

### Keyword Location

After content input, the system extracts and ranks keywords:

- Exact keyword hits against the vertical and scene-pack keyword library.
- Synonym and platform-adapted keyword hits.
- AI-assisted keyword suggestions when an AI Provider is configured.
- Negative keyword warnings.
- Named entities, product names, audience terms, pain points, and scenario terms.
- Confidence score for each extracted keyword.

The result must show:

- extracted keyword
- source span or evidence text
- keyword type: primary, secondary, synonym, platform-adapted, negative, AI-suggested
- matched vertical and scene pack
- confidence
- monitoring reason
- recommended search query variants

AI suggestions must be inspectable and editable. They should not silently enter the official keyword library unless the user saves them through the keyword library confirmation workflow.

### Similar Content Search

After keyword extraction, the user can search similar content.

Search inputs:

- selected extracted keywords
- selected vertical and scene packs
- platform list
- date range
- content type
- minimum engagement threshold
- exclude already tracked content
- real-time search switch

Search behavior:

- Local-first: search existing collected posts and raw records.
- Optional real-time search: if enabled, create platform search crawl tasks using selected keywords.
- Platform choice follows the same rule as creator discovery: form platforms first, global defaults second, otherwise block execution.
- Default execution is asynchronous.
- The page provides `等待完成并刷新`.

Similar content result fields:

- title or summary
- platform
- author/creator
- publish time
- content type
- matched keywords
- similarity score
- engagement metrics
- URL
- tracking status
- evidence snippets

Similarity scoring starts as a rule-based model:

- keyword overlap
- scene-pack overlap
- title/description text similarity
- author/topic overlap
- engagement quality
- recency

AI can summarize why content is similar, but the initial score should be deterministic and inspectable.

### Tracking Objects

Users can save selected keywords and similar-content criteria as a tracking object.

Tracking object fields:

- name
- description
- vertical ID
- scene-pack IDs
- platforms
- included keywords
- excluded keywords
- seed content IDs or URLs
- search query variants
- schedule interval
- comment policy
- raw record mode
- enabled status

Default frequency:

- Content tracking defaults to every 12 hours, matching monitor pool defaults.
- Users can change it to 1 hour, 6 hours, 12 hours, 24 hours, or a custom minute value.

Tracking execution:

- The system creates or updates a `collection_mode="search"` research job for the tracking object.
- Selected keywords become `keywords`.
- If the tracking object is URL/ID based, the system can also create `collection_mode="detail"` jobs for seed content.
- `立即追踪` executes the same long-term tracking job immediately.
- The system should not create a separate one-off task for immediate tracking unless implementation constraints require it.

### Content Analysis Outputs

Each tracking object has an analysis page with:

- new similar content count
- total tracked content count
- platform distribution
- keyword hit trend
- engagement trend
- hot content list
- creator overlap
- repeated content patterns
- sentiment or stance distribution when AI analysis results exist
- comment themes when comments are collected
- AI summary and recommended actions

Required evidence:

- why a content item matched
- which keywords matched
- which scene packs matched
- whether the item came from local data or real-time search
- whether the sample size is enough for reliable judgment

### Content Tracking Automation

Automation is optional and off by default.

Rules:

- Automatically add similar content to tracking candidates.
- Automatically create tracking objects from high-confidence keyword extraction.
- Minimum similarity score threshold, default 75.
- Minimum engagement threshold, optional.
- Exclude already tracked content by default.
- Mode switch:
  - pending confirmation queue
  - direct tracking
- Default mode is pending confirmation queue.

The UI must show affected content count before applying automation.

### Content Tracking APIs

New or enhanced APIs:

- `POST /api/content-tracking/extract-keywords`
- `POST /api/content-tracking/search-similar`
- `POST /api/content-tracking/realtime-discovery`
- `GET /api/content-tracking/discovery/{id}/status`
- `POST /api/content-tracking/discovery/{id}/wait-refresh`
- `POST /api/content-tracking/trackers`
- `PATCH /api/content-tracking/trackers/{id}`
- `GET /api/content-tracking/trackers`
- `GET /api/content-tracking/trackers/{id}`
- `POST /api/content-tracking/trackers/{id}/execute`
- `GET /api/content-tracking/trackers/{id}/analysis`
- `POST /api/content-tracking/candidates/bulk-action`

These APIs should reuse `ResearchRepository`, `ResearchScheduler`, `ResearchExecutionManager`, and existing research jobs where possible.

### Content Tracking Models

New or enhanced models:

- Content input sample.
- Extracted keyword result.
- Similar content candidate.
- Content tracking object.
- Content tracking candidate decision.
- Content tracking analysis snapshot.

The models should keep enough evidence to explain future AI summaries and scoring decisions.

## Competitor Monitoring

Phase one competitor monitoring is the structure breakdown version.

Capabilities:

- Add competitor accounts by platform and creator/account ID.
- Group competitors by vertical or business category.
- Daily collection of competitor posts and engagement data.
- Daily snapshot per competitor account.
- Total traffic view:
  - total posts
  - total likes
  - total comments
  - total shares or platform equivalent
  - new posts
  - top content
- Composition breakdown:
  - keyword distribution
  - tag distribution
  - content type distribution
  - posting time distribution
  - hot post rate

Phase one should provide enough evidence for daily review. Deep opportunity-gap analysis against owned monitor pools can be deferred.

## Keyword Heat And Platform Signal Model

Keyword heat and platform signal output must include:

- Label:
  - `推流中`
  - `正常波动`
  - `降温`
  - `疑似限流`
- Heat Score.
- Push Score.
- Cooldown Risk.
- Data confidence:
  - high
  - medium
  - low
- Evidence explanations, normally 3-5 bullet points.

Time windows:

- Primary judgment uses the last 24 hours compared with the 7-day average.
- Trend reference uses the last 7 days compared with the 30-day average.
- The UI should show both the short-term signal and medium-term trend.

Suggested proxy metrics:

- Content volume for matching keywords.
- Total engagement.
- Engagement rate.
- Hot post rate.
- Distinct creator count.
- Comment activity.
- New content startup speed.
- Mid-tier creator performance.
- Head creator versus ordinary creator divergence.

Example evidence:

- `近 24 小时内容量较 7 日均值上涨 42%`.
- `中腰部达人互动率高于过去 7 日均值 31%`.
- `爆款率连续 2 天下降，疑似降温`.
- `样本量不足 30 条，置信度为低`.

The model should be transparent and rule-based at first. AI can summarize evidence, but the underlying scores should be deterministic and inspectable.

## Frontend Design

New or expanded pages:

- Keyword library:
  - vertical management
  - scene-pack management
  - manual keyword edit
  - CSV/Excel import/export
  - AI keyword expansion with selectable suggestions
- Creator discovery:
  - local-first search
  - real-time discovery switch
  - async discovery task state
  - wait-and-refresh action
  - candidate table
  - evidence drawer
  - automation panel
  - monitor pool selection/create dialog
  - add to monitor and add-and-crawl-now actions
- Monitor pools:
  - pool list
  - creator list per pool
  - frequency and comment policy
  - latest crawl status
  - immediate crawl action
- Content tracking:
  - content input panel for text, links, content IDs, uploaded rows, or existing collected posts
  - extracted keyword list with source spans, confidence, matched verticals, and matched scene packs
  - AI keyword suggestions with manual confirmation
  - similar content search controls
  - local-first results and optional real-time discovery state
  - wait-and-refresh action
  - similar content candidate table
  - evidence drawer
  - tracking object creation dialog
  - immediate tracking action
  - tracking analysis dashboard
- Competitor monitoring:
  - account pool
  - daily snapshot
  - traffic composition panels
- Keyword heat:
  - platform and keyword filters
  - short-term signal and medium-term trend
  - score cards
  - evidence list

The dashboard should link these flows without turning the overview page into a large form. Heavy configuration belongs in pages, drawers, and panels.

## Backend Design

New or enhanced models:

- Vertical.
- Scene pack.
- Scene-pack keyword item.
- AI keyword suggestion session.
- Creator discovery session.
- Creator candidate enriched fields.
- Monitor pool.
- Monitor pool creator membership.
- Content input sample.
- Extracted content keyword.
- Similar content candidate.
- Content tracker.
- Content tracking snapshot.
- Keyword heat snapshot.
- Competitor traffic composition snapshot.

New or enhanced APIs:

- Keyword library CRUD.
- CSV/Excel import/export for keyword library.
- AI keyword expansion.
- Creator discovery search.
- Real-time discovery start.
- Discovery status.
- Wait discovery completion and refresh candidates.
- Candidate bulk action.
- Monitor pool CRUD.
- Add selected creators to pool.
- Add Top N creators to pool.
- Add and crawl now.
- Content keyword extraction.
- Similar content search.
- Real-time similar-content discovery.
- Content tracker CRUD.
- Content tracker immediate execution.
- Content tracker analysis.
- Keyword heat calculation and snapshot listing.
- Competitor composition snapshot.

Implementation should reuse:

- `ResearchRepository`.
- `ResearchScheduler`.
- `ResearchExecutionManager`.
- existing `creator-search` APIs.
- existing competitor service and snapshot primitives.
- existing AI Provider config where possible.

## Error Handling

The UI should handle:

- SQL storage not enabled.
- No global default platforms and no selected platforms.
- Real-time discovery already running.
- Crawler process already busy.
- AI provider missing or API key not configured.
- AI output not valid JSON.
- Content input cannot be parsed.
- Post URL platform cannot be detected.
- Similar-content search has too few results.
- Real-time content discovery is requested without selected or default platforms.
- Too few samples for reliable heat scoring.
- Duplicate creator membership in a pool.
- Platform capability disabled for search or creator crawling.

User-facing errors should explain the required next action.

## Testing Plan

Backend tests:

- Keyword library CRUD and validation.
- AI keyword suggestion parsing and manual confirmation.
- Creator discovery local-first search.
- Real-time discovery request creation without starting a real crawler in unit tests.
- Monitor pool creates or updates creator-mode research jobs.
- Add-and-crawl-now calls the same monitor job execution path.
- Automation thresholds produce pending or direct actions.
- Content keyword extraction from text, URL metadata, and existing posts.
- Similar content candidate scoring and evidence.
- Content tracker creates or updates search/detail research jobs.
- Content tracker immediate execution calls the same long-term tracking job path.
- Content tracking automation produces pending or direct actions.
- Content tracking analysis aggregates keyword hits, platform distribution, engagement trends, and hot content.
- Keyword heat scoring returns label, scores, confidence, and evidence.
- Competitor composition aggregation.

Frontend checks:

- Build succeeds with `npm run build`.
- Keyword library page supports manual edit and AI suggestion selection.
- Creator discovery page handles local-only and real-time modes.
- Add selected, add Top N, and automation flows show affected creator counts.
- Monitor pool dialog can configure frequency and comment policy.
- Content tracking page extracts keywords and displays editable evidence.
- Similar content search supports local-only and real-time modes.
- Content tracker dialog configures platforms, schedule, comment policy, and immediate tracking.
- Content tracking analysis displays trends and evidence without layout overflow.
- Keyword heat page displays both time windows and evidence.
- Competitor monitoring page displays composition breakdown without layout overflow.

Regression checks:

- Existing `/api/research/*` behavior remains compatible.
- `/crawler` direct crawler console remains available.
- `/research` remains the primary entry.

## Open Decisions

The following can be decided during implementation if no stronger requirement appears:

- Exact CSV/Excel template column names.
- First default 4Router model name.
- Exact heat score weights.
- Exact text similarity weighting for similar content.
- Whether uploaded video files should ever be accepted directly in phase one.
- Whether contact clues should be rule-based only or optionally AI-assisted.
- Whether monitor pool tasks should split by platform if one pool contains many platforms and creators.

Recommended defaults:

- CSV/Excel template columns should mirror the scene-pack keyword item model.
- 4Router model should be configured by user in AI Provider, not hard-coded.
- Heat score weights should start as config constants and later move to UI config.
- Similar content scoring should start rule-based with AI summaries as optional evidence.
- Uploaded video files should not be required in phase one; URLs, captions, OCR, transcripts, titles, descriptions, and text rows are enough.
- Contact clues should start rule-based and only summarize with AI.
- Monitor pool can initially create one creator-mode research job per pool; platform splitting can be added if execution constraints require it.
