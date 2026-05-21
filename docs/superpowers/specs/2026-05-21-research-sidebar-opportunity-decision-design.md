# Research Sidebar Opportunity Decision Design

## Goal

Restore the full Research console navigation and add a first-class sidebar module named `增长机会决策`. The module helps bosses and operators decide what to follow today, why it matters, what risks exist, and what action should happen next.

This replaces the simplified two-tab frontend direction. The new work must live inside the existing Research console experience, not as a separate HTML page, standalone app, or replacement shell.

## Confirmed Decisions

- Add `增长机会决策` as a top-level left-sidebar item.
- Place it after `总览` and `任务工作台`, before growth tool pages.
- Restore the full Research console navigation:
  - `总览`
  - `任务工作台`
  - `增长机会决策`
  - `达人发现`
  - `关键词库`
  - `友商监控`
  - `内容跟踪`
  - `数据浏览`
  - `AI 分析`
  - `导出中心`
  - `配置`
- Use a conclusion-first layout for `增长机会决策`.
- Optimize both `增长机会决策` and `数据浏览`, with separate responsibilities.
- Use `shadcn/ui` style local components, Radix primitives, `lucide-react`, and Recharts.
- Keep high-risk actions visible, but require confirmation or prefilled navigation before execution.

## Information Architecture

The Research console keeps its existing left-sidebar mental model. `增长机会决策` is a decision layer between task execution and growth tools:

- `总览`: operational health and high-level status.
- `任务工作台`: create, run, schedule, and inspect collection tasks.
- `增长机会决策`: decide which keyword, content, creator, or competitor opportunity deserves action.
- Growth tools: manage the inputs that feed opportunities.
- `数据浏览`: audit sample quality and inspect raw evidence.
- `AI 分析`, `导出中心`, `配置`: supporting workflows.

The new module must not hide or remove existing Research workflows. It should make the console feel more complete, not narrower.

## Opportunity Decision Page

The first screen is conclusion-first:

1. Page heading and controls:
   - title `增长机会决策中心`
   - time window selector with default `7 天趋势 + 24 小时变化`
   - refresh action
   - opportunity-type tabs: `全部 / 关键词 / 内容 / 达人 / 友商动作`
2. Today conclusion card:
   - one-sentence decision headline
   - sample status
   - opportunity score
   - risk count
   - sample count
   - next recommended action
3. Top opportunity section:
   - Top 5 opportunity list
   - Watchlist with 3 items
   - low-sample opportunities may appear in watchlist but cannot rank first
4. Selected opportunity explanation:
   - score breakdown
   - 7/14/30 day trend
   - platform signal
   - risk tags
   - evidence summary
   - primary next action
5. Core chart row:
   - score breakdown
   - trend chart
   - platform signal chart
   - risk distribution
6. Expandable analysis:
   - competition gap ranking
   - opportunity matrix
   - content supply gap
   - typed evidence samples

The page should look like an operations decision desk, not a generic admin table. Cards should have clear hierarchy, stable chart dimensions, restrained colors, and compact but readable spacing.

## Opportunity Details

Clicking an opportunity keeps the page context and opens a right-side detail drawer. The drawer includes:

- opportunity name, type, platform, and current score
- score breakdown
- trend chart with 7/14/30 day switch
- platform contribution
- risk tags
- sample scope
- auditable summary
- up to 10 typed evidence samples
- expandable raw fields
- feedback buttons: `有效 / 误判 / 先观察`
- action controls

High-risk actions remain visible but do not execute immediately. Clicking them opens a confirmation modal or prefilled destination:

- real collection task creation and immediate run
- realtime discovery
- backfill
- batch creator monitoring
- competitor long-term monitoring
- schedule-frequency increases
- AI/batch AI/report generation with model cost
- sensitive export including raw comments, author info, or raw payload

## Data Browser Optimization

`数据浏览` changes from table-first to `摘要 + 可展开明细`.

Default structure:

1. Task/data source selector.
2. Data quality summary:
   - total samples
   - platform coverage
   - time coverage
   - raw record coverage
   - AI result coverage
3. Core charts:
   - platform distribution
   - publish-time distribution
   - keyword hits
   - engagement distribution
4. Sample cards:
   - title/body summary
   - platform
   - publish time
   - engagement summary
   - matched keyword/source keyword
5. Expandable detail:
   - original fields
   - raw payload
   - AI result JSON

The data browser answers: where did the data come from, how fresh is it, how broad is the platform coverage, and whether the samples are credible enough to support the decision page.

## Component System

Use `shadcn/ui` style components locally so the UI feels polished without importing a heavy opinionated admin system.

Recommended component boundaries:

- `Button`
- `Badge`
- `Card`
- `Tabs`
- `Drawer`
- `Dialog`
- `Tooltip`
- `Select`
- `Table`
- `Skeleton`

Use Radix primitives for interaction semantics where useful:

- tabs
- dialog/drawer
- tooltip
- select/dropdown

Use `lucide-react` for navigation and action icons. Continue using Recharts for business charts.

Do not introduce Ant Design for this work. Its default visual system would make the page feel like a generic management backend instead of a tailored operations decision console.

## Backend Contract

The backend remains responsible for standardized decision fields. The frontend must display and interact with the contract rather than recomputing opportunity scores.

The opportunity decision page consumes:

- `top_opportunities`
- `watchlist`
- `ignored_opportunities`
- `scoring_profile`
- `score_breakdown`
- `risk_tags`
- `sample_scope`
- `trend`
- `actions`
- `samples`
- `diagnostics`
- `feedback_state`

Compatibility fields remain available:

- `opportunities`
- `reason`
- `confidence`
- `payload`
- `change_24h`
- `trend_7d`
- `evidence_count`
- `detail`

The score weights remain unchanged:

- heat growth: `35%`
- sample confidence: `25%`
- competition gap: `20%`
- actionability: `20%`

## Empty And Error States

The frontend must not pretend to have conclusions when the data is insufficient.

Use diagnostic empty states that explain:

- what is missing
- why that prevents a conclusion
- what the next action is

Examples:

- no opportunity data: suggest running collection or realtime discovery
- low sample coverage: explain sample count and platform coverage
- stale data: show last update time and suggest refresh/backfill
- missing execution parameters: show which parameters are missing

## Feedback Behavior

Feedback actions are lightweight:

- `有效`
- `误判`
- `先观察`

Feedback affects the current board presentation:

- `有效`: mark as validated
- `误判`: remove from Top 5 and place in ignored opportunities
- `先观察`: move or keep in watchlist

Feedback does not change global scoring weights in this version.

## Implementation Boundaries

This design does not add a new HTML page.

It does not add a separate `/opportunity` backend route.

It restores and extends the existing Research console frontend:

- restore full sidebar information architecture
- insert `增长机会决策`
- improve `增长机会决策`
- improve `数据浏览`
- keep existing backend dashboard summary and feedback API direction

## Verification

Implementation should verify:

- sidebar contains the full Research module list in the confirmed order
- `增长机会决策` renders as a standalone sidebar module
- default page is not reduced to only two tabs
- Top 5 and watchlist render from backend fields
- type tabs filter opportunity categories
- core charts render without layout shift or overlap
- detail drawer opens and closes correctly
- feedback calls the feedback endpoint and updates the board
- high-risk actions open confirmation or prefilled navigation
- data browser defaults to summary and sample cards
- raw fields/JSON are available only through expansion
- diagnostic empty states appear when data is missing
- TypeScript build passes
- focused backend tests still pass
