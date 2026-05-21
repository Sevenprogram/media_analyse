# Boss Opportunity Decision Dashboard Design

Date: 2026-05-21

## Goal

Build a boss and operations focused decision layer that answers: which keywords, content, creators, and competitor moves are worth following up now, why they are worth following, what risks exist, and what the next action should be.

This is not a generic analytics dashboard. The first version should produce auditable opportunity decisions, expose enough evidence to trust or challenge them, and turn high-value opportunities into controlled actions.

## Primary User

The first version serves the boss and operations decision view.

The page should prioritize:

- Clear conclusions.
- Top opportunities.
- Risks and confidence.
- Next actions.

Researcher and collection-ops needs remain supported through drill-downs, evidence panels, data browsing, and task workflows, but they are not the primary first-screen audience.

## Core Decision Question

The homepage should answer:

> What should we follow up today, why, how risky is it, and what should we do next?

The default action category is hot opportunity follow-up, not retrospective reporting or infrastructure monitoring.

## Opportunity Scope

The opportunity board should mix these object types in one ranked list:

- Keywords.
- Content.
- Creators.
- Competitor actions.

Every opportunity must carry a type label so mixed ranking stays readable.

## Ranking Model

The default ranking is a composite opportunity score.

Weights:

- Heat growth: 35%.
- Sample confidence: 25%.
- Competition gap: 20%.
- Actionability: 20%.

This is the balanced first-version profile: aggressive enough for hotspot discovery, but constrained by data confidence and action feasibility.

### Heat Growth

Heat growth should use:

- Default trend window: 7 days.
- Acceleration signal: 24 hour change.
- Optional comparison windows: 14 days and 30 days.

The main board sorts primarily through the composite score, where the heat component uses 7 day trend and shows 24 hour acceleration as supporting context.

### Sample Confidence

Low-sample opportunities can appear, but they must be downweighted and risk-labeled. They cannot rank first in the main Top 5.

Suggested thresholds:

- High confidence: at least 100 samples, at least 2 platforms, updated within 24 hours.
- Medium confidence: at least 30 samples, or 1 primary platform updated within 24 hours.
- Low confidence: fewer than 30 samples, or updated more than 48 hours ago.
- Very low confidence: fewer than 10 samples. These go to the watchlist, not the main Top 5.

### Competition Gap

The first version defines competition gap as:

- Similar high-quality content supply is insufficient.
- Competitor coverage is insufficient.

This prevents false positives where competitors are absent because demand is weak. Competition gap only matters when paired with heat growth or meaningful sample evidence.

### Actionability

An opportunity is actionable when the system can generate a clear next action and already has enough input parameters to support that action.

High actionability examples:

- Keyword, platform, and time window are known, so a collection task can be prefilled.
- Creator or competitor ID is known, so the object can be added to monitoring.
- Evidence samples exist, so the user can inspect and export context.

Low actionability examples:

- Abstract topic only.
- No platform, keyword, object ID, or evidence sample.
- AI-only guess without local sample or collection path.

## Board Capacity

The homepage shows:

- Main board: Top 5 opportunities.
- Watchlist: 3 early or risky opportunities.

The system should force prioritization. It should not turn the boss homepage into a long sortable table.

## Risk Tags

First version fixed risk tags:

- Small-sample spike: fast 24 hour growth but insufficient sample count.
- Single-platform signal: evidence is concentrated on one platform.
- Stale data: latest update is older than 48 hours.
- Overheated competition: competitors or high-engagement similar content already cover the opportunity heavily.
- Missing execution parameters: missing keyword, platform, creator ID, competitor ID, or time window.
- High cost: the next action triggers real collection, bulk AI analysis, report generation, or sensitive export.

Risk tags must affect behavior:

- Small-sample spike can appear in the watchlist but cannot rank first.
- Missing execution parameters disables direct execution and only allows prefilled navigation.
- High cost always requires confirmation.
- Stale data should suggest refresh or backfill before execution.

## Evidence Depth

Opportunity details should show auditable summaries and expandable raw samples.

First version detail drawer:

- Score breakdown: heat growth, sample confidence, competition gap, actionability.
- Key evidence summary: 3 to 5 short explanations.
- Sample scope: time window, platforms, sample count, last update.
- Risk tags and risk explanation.
- Expandable raw samples: up to 10 items.
- Feedback controls: valid, false positive, watch.
- Next actions.

Raw samples should be typed:

- Keyword opportunity: related posts or comments, platform, publish time, engagement, matched keyword.
- Content opportunity: similar content title, similarity score, keyword hits, engagement.
- Creator opportunity: creator ID/name, followers, recent 30 day posts, matched tags, evidence content.
- Competitor action: competitor account, recent content, publish time, engagement change, action type.

Do not show raw payload by default. Provide a route into data browsing or raw records when needed.

## Feedback

Users can label each opportunity:

- Valid.
- False positive.
- Watch.

First version feedback behavior:

- Valid records positive feedback and keeps the opportunity available for execution.
- False positive removes the opportunity from the current Top 5 and moves it to an ignored or folded area.
- Watch moves the opportunity to the watchlist.
- Feedback does not change global scoring weights.
- Backend records feedback for later analysis.

## Action Rules

Actions should be real where practical, but high-risk actions require confirmation. Complex actions use prefilled navigation.

High-risk actions:

- Actions that trigger real collection: create-and-run collection task, real-time discovery, backfill.
- Actions that expand monitoring: batch creator add, competitor long-term monitoring, higher schedule frequency.
- Actions that incur external cost: AI analysis, bulk analysis, model-backed report generation.
- Actions that export sensitive data: raw comments, author data, raw payloads.

Low-risk actions:

- View evidence details.
- Switch chart dimensions.
- Open data browser.
- Prefill a task form without submitting.
- Download already generated files.

Recommended first-version behavior:

- Create collection task: prefill and confirm before create/run.
- Add to monitor pool: confirm, choose or default a pool, then execute.
- View evidence: direct drawer open.
- Generate topic or AI analysis: prefill/navigate first; running analysis requires confirmation.
- Export report: navigate first; sensitive export requires confirmation.

## Diagnostic Empty States

Do not invent conclusions when data is incomplete. Use diagnostic empty states.

Rules:

- No collection data: show no opportunity decision, explain missing collection data, and offer create collection task.
- Data exists but samples are insufficient: show watchlist only, explain sample weakness, and suggest backfill or platform expansion.
- Missing competitor data: keyword/content opportunities can show, but competition gap is marked as unverified.
- Missing creator profiles: keyword/content opportunities can show, creator opportunities are empty, and the next action is rebuild creator profiles.
- AI unavailable: rule-based scoring still works; hide AI summaries and prompt provider configuration.

## Backend Contract

Backend should produce standardized opportunity decision fields. Frontend should display and interact with them, not calculate business scoring ad hoc.

Suggested response shape:

```json
{
  "top_opportunities": [],
  "watchlist": [],
  "diagnostics": [],
  "scoring_profile": {
    "weights": {
      "heat_growth": 0.35,
      "sample_confidence": 0.25,
      "competition_gap": 0.2,
      "actionability": 0.2
    },
    "window": "7d_plus_24h"
  }
}
```

Each opportunity:

```json
{
  "id": "keyword:xhs:k12-companion-learning",
  "type": "keyword",
  "name": "K12 companion learning",
  "score": 82,
  "score_breakdown": {
    "heat_growth": 86,
    "sample_confidence": 72,
    "competition_gap": 80,
    "actionability": 88
  },
  "risk_tags": ["single_platform_signal"],
  "evidence_summary": [],
  "sample_scope": {
    "window": "7d",
    "platforms": ["xhs"],
    "sample_count": 128,
    "last_updated_at": "2026-05-21T02:00:00Z"
  },
  "trend": {
    "change_24h": 18.4,
    "points_7d": [],
    "points_14d": [],
    "points_30d": []
  },
  "actions": [],
  "samples": []
}
```

Feedback endpoint should accept:

```json
{
  "opportunity_id": "keyword:xhs:k12-companion-learning",
  "feedback": "valid",
  "note": "Good fit for this week's content push"
}
```

Allowed feedback values:

- `valid`
- `false_positive`
- `watch`

## Chart Design

Charts can be richer than the current implementation, but they must remain decision-oriented. Every chart should answer a question and connect to evidence or action.

### Homepage First Screen

Charts and visual elements:

- Top 5 opportunity board.
- Composite score breakdown for the selected opportunity.
- 7 day trend with 24 hour change marker.
- Platform signal distribution.
- Risk tag strip.

Purpose:

- Let the boss identify the strongest opportunity quickly.
- Show why it ranks high.
- Show whether the signal is risky.
- Provide immediate next actions.

### Homepage Analysis Area

Add comparison charts below the first screen:

- Opportunity type distribution: keyword/content/creator/competitor mix.
- Opportunity matrix: x-axis actionability, y-axis heat growth, bubble size sample confidence, bubble color opportunity type.
- Competition gap ranking: high heat with low competitor coverage.
- Watchlist trend: low sample but fast-growing early signals.
- Risk distribution: frequency of the six risk tags across Top 5 and watchlist.

Purpose:

- Explain the shape of the opportunity pool.
- Help users compare tradeoffs instead of only accepting a ranked list.
- Make risky early signals visible without promoting them too strongly.

### Opportunity Detail Drawer

Charts:

- Four-part score breakdown: horizontal bars, not decorative gauge.
- Trend window chart: 7d default, toggle 14d and 30d.
- 24h acceleration card: 24h change compared with 7d average.
- Platform contribution chart: samples and engagement by platform.
- Sample quality chart: valid, weakly related, duplicate, stale, raw-parse issue.
- Competitor coverage timeline: when competitors started covering the topic and how densely.
- Similar content supply chart: high-engagement content count, normal content count, gap judgement.
- Evidence sample panel: up to 10 typed samples beside or below the charts.

Purpose:

- Make the score auditable.
- Show whether the opportunity is broad or platform-specific.
- Separate true opportunities from noisy spikes.
- Give the user enough evidence to mark valid, false positive, or watch.

### Data Browser

Charts:

- Filter result summary: sample count, time window, platform count, keyword count.
- Publish time distribution.
- Platform comparison: samples, engagement, comments.
- Keyword hit ranking.
- Interaction distribution.
- Sentiment or stance distribution when AI results exist.
- Data quality panel: missing title, missing publish time, duplicates, raw parse failures.

Purpose:

- Support evidence verification after clicking through from an opportunity.
- Help researchers understand the slice behind a decision.

### Chart Component Candidates

First version components:

- `OpportunityScoreBars`
- `OpportunityTrendChart`
- `PlatformSignalChart`
- `OpportunityMatrixChart`
- `RiskDistributionChart`
- `CompetitionGapRanking`
- `SampleQualityChart`
- `CompetitorCoverageTimeline`
- `SimilarContentSupplyChart`
- `EvidenceSamplePanel`

Use Recharts for the first version because the project already depends on it.

## Frontend Layout

Homepage first screen:

- Left: Top 5 opportunities and watchlist.
- Right: selected opportunity explanation panel with score bars, trend, platform distribution, risk tags, and primary actions.

Homepage lower area:

- Matrix and distribution charts.
- Risk and competition gap panels.
- Diagnostics if data is missing.

Opportunity detail:

- Drawer or full-width detail panel.
- Keep summary and actions sticky near the top.
- Charts and evidence samples below.

Data browser:

- Keep table as the primary research surface.
- Add charts above or beside the table, depending on width.
- Row click opens typed detail drawer instead of expanding raw JSON inline.

## Out Of Scope

- AI-only opportunity generation without structured evidence.
- Automatic scoring-weight learning from feedback.
- Full team workflow with approvals and assignees.
- Complete redesign of all growth tools.
- Raw payload browsing inside the boss homepage.

## Acceptance Criteria

- Homepage shows Top 5 opportunities and 3 watchlist items when data is sufficient.
- Opportunities are ranked by composite score with the 35/25/20/20 weights.
- Low-sample opportunities are downweighted and cannot rank first.
- Each opportunity shows score breakdown, risk tags, sample scope, and next actions.
- Detail view shows auditable summaries and up to 10 typed raw samples.
- Feedback supports valid, false positive, and watch, and affects the current board without changing global weights.
- High-risk actions require confirmation.
- Missing data produces diagnostic empty states rather than fake conclusions.
- Frontend charts answer clear decision questions and use backend-standardized fields.
