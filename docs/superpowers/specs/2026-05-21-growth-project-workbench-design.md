# Growth Project Workbench Design

## Purpose

The current collection workbench exposes individual crawler jobs as the primary object. That is useful for engineering and diagnostics, but it makes the product feel like a task queue instead of a growth intelligence workspace.

The new design promotes a business-level object: the growth project. A growth project represents a concrete research or growth campaign, such as "2026 summer education enrollment topic research" or "AI tool keyword expansion". Collection jobs remain important, but they move under the project as execution records.

## Product Direction

The primary user view is mixed, with a business-first default:

- Operators and content teams should quickly understand whether a project has opportunity and what to do next.
- Owners should see the current decision state without reading crawler logs.
- Data and collection users should be able to drill down into task health, raw records, and failures when needed.

The main page should therefore show growth projects, not individual research jobs.

## Core Objects

### Growth Project

A growth project is the top-level business object.

Suggested fields:

- `id`
- `name`
- `primary_goal`
- `platforms`
- `status`
- `sample_status`
- `recommended_action`
- `opportunity_score`
- `last_collected_at`
- `created_at`
- `updated_at`

Supported `primary_goal` values:

- `topic_discovery`
- `creator_discovery`
- `keyword_expansion`
- `competitor_monitoring`
- `mixed_research`

Each project must have one primary goal, even when it also contains secondary goals. This keeps recommendations focused.

### Project Assets

A project can contain:

- keyword groups
- platform scope
- research jobs
- post, comment, creator, and raw samples
- AI insights
- opportunity judgments
- recommended next actions
- monitoring settings

### Research Jobs

Existing research jobs become execution records under a project. A project can have many jobs:

- keyword search jobs
- comment backfill jobs
- creator timeline jobs
- competitor collection jobs
- AI analysis jobs

Long term, `research_jobs` should include a `growth_project_id`. For the first iteration, jobs can be grouped through a frontend or backend aggregation layer using existing metadata, naming conventions, or a lightweight `project_key`.

## Main Page

The workbench main page should become a growth project list.

Each project appears once. The card should answer:

- What is this project?
- What is the main goal?
- What should I do next?
- Is the sample good enough?
- Is there a meaningful opportunity?
- Are there collection issues that need attention?

### Project Card Content

Recommended card hierarchy:

1. Project identity
2. Recommended action
3. Sample status
4. Opportunity score and short evidence
5. Data and collection health summary

Example:

```text
2026 summer education enrollment topic research
Topic discovery · Douyin / Xiaohongshu · Updated today 14:20

Recommended action: backfill comments, then generate topic insights
Sample status: posts sufficient, comments insufficient
Opportunity score: 78
Evidence: recent signals cluster around junior high planning, summer childcare, and enrollment conversion.

144 posts · 0 comments · 18 creators · 100 raw · 2 failed jobs
```

### Primary Actions

Each card should show at most two visible buttons:

- Primary: view overview
- Secondary: execute the current recommended action

Additional actions move into a more menu:

- backfill posts
- backfill comments
- generate insight
- view collection records
- export report
- settings

The secondary button label should be dynamic. If the recommended action is "generate insight", the button says "Generate insight". If the action is "backfill comments", the button says "Backfill comments".

### Filters And Sorting

Suggested filters:

- All
- Needs action
- Ready for analysis
- High opportunity
- Collection issue
- Monitored

Suggested sorting:

- Recommendation priority
- Opportunity score
- Recently updated
- Sample size

## Project Detail Page

Clicking a project opens the project detail page. The default tab is Overview, not collection records.

Tabs:

- Overview
- AI Insights
- Sample Data
- Keyword Group
- Collection Records
- Settings

The creator and competitor view can initially live under Sample Data or AI Insights. It can become a dedicated tab later when the domain model is deeper.

### Persistent Status Bar

The detail page should keep a compact project status bar visible above all tabs:

```text
Recommended action: backfill comments, then generate topic insights
Sample status: posts sufficient, comments insufficient
Opportunity score: 78
```

This keeps the business goal visible even when users drill into collection records.

### Overview Tab

The Overview tab is the decision page for the project.

Sections:

- current judgment
- recommended actions
- sample status
- key trends
- representative content
- collection health

Example current judgment:

```text
Opportunity: medium-high
Summary: Summer education enrollment content is showing usable demand signals, but comments are missing. Generate only preliminary topics until comments are backfilled.
```

### AI Insights Tab

This tab shows business interpretation, not task logs.

Sections:

- opportunity judgment
- topic suggestions
- keyword suggestions
- creator suggestions
- competitor observations
- risks and uncertainty
- missing data needed for a stronger decision

If AI has not run yet, the empty state should be actionable:

```text
144 posts are available, but comment samples are missing. Backfill comments for stronger topic judgment, or generate preliminary insight from posts.
```

Actions:

- Backfill comments
- Generate preliminary insight

### Sample Data Tab

This tab shows readable data, not raw crawler internals by default.

Subviews:

- Posts
- Comments
- Creators
- Raw

Default to Posts. Raw should be available for debugging but should not be the first view for business users.

Recommended post fields:

- title or content summary
- platform
- engagement
- publish time
- matched keyword
- author
- value marker

### Keyword Group Tab

This tab manages the project's keyword assets.

Keyword types:

- core
- expanded
- pending
- excluded
- high-potential
- low-efficiency

Actions:

- add keyword
- AI expand keywords
- add to monitoring
- exclude keyword
- backfill by keyword

### Collection Records Tab

This tab contains the current task queue view. It is a diagnostic and operational surface, not the default business view.

Columns:

- task name
- platform
- collection mode
- keyword or target
- status
- posts
- comments
- raw records
- started at
- finished at
- failure reason

Actions:

- rerun
- backfill comments
- view raw
- view logs
- cancel

### Settings Tab

Settings configure the project:

- primary goal
- platforms
- refresh cadence
- comment collection policy
- monitoring pool
- AI analysis template
- sample thresholds
- notifications

Advanced crawler-specific settings should stay out of the default create flow.

## Create Growth Project Flow

The primary entry is "New Growth Project".

Use a single-page form with a collection plan preview:

- Left: project configuration
- Right: generated collection plan

Fields:

- project name
- primary goal
- platforms
- initial keywords
- collection depth
- refresh cadence
- AI analysis option

Collection depth options:

- lightweight: posts only
- standard: posts and basic comments
- deep: posts, comments, and creator profiles

Default depth: standard.

Refresh cadence:

- off
- daily
- every 3 days
- weekly
- custom

Default refresh: off. This avoids implying that every project is automatically a scheduled crawler.

The preview should explain what will be created:

```text
Will create:
- Douyin keyword search job
- Xiaohongshu keyword search job
- comment backfill job
- AI insight job

Expected outputs:
- content samples
- comment samples
- candidate creators
- keyword opportunities
- project overview
```

After creation, route to the project detail page.

## Recommendation Logic

Use rules first, AI second.

Rules own deterministic state:

- whether collection failed
- whether jobs are running
- whether sample counts are below thresholds
- whether comments are insufficient
- whether new data exists after the last AI insight
- whether monitoring is enabled

AI owns business interpretation:

- why a rule action matters
- which keywords are worth deeper collection
- which creators or topics look promising
- what uncertainty remains
- which next step is most useful for the project's primary goal

### Project States

Suggested states:

- waiting_for_collection
- collecting
- sample_insufficient
- preliminarily_analyzable
- deeply_analyzable
- new_sample_pending_analysis
- collection_issue
- monitored
- paused

### Rule Action Priority

Recommended priority:

1. Collection issue
2. Collecting
3. Sample insufficient
4. Comment insufficient
5. New sample pending analysis
6. Ready to generate insight
7. Ready to monitor

This prevents contradictory states, such as suggesting topic generation while a collection failure needs attention.

### Goal-Specific Signals

Topic discovery:

- posts
- comments
- high-engagement content
- keyword coverage

Creator discovery:

- creator count
- creator profile samples
- engagement performance
- category fit

Keyword expansion:

- keyword coverage
- low-result terms
- high-growth terms
- related terms

Competitor monitoring:

- account updates
- engagement changes
- topic shifts
- refresh continuity

Mixed research:

- use the configured priority goal
- if no priority is set, ask the user to choose the current focus

## MVP Scope

The MVP should solve the current information architecture problem:

The main page should no longer flatten research jobs. It should aggregate them into growth projects, with collection records nested in project detail.

### MVP In Scope

- Growth project list page
- Project cards with recommendation, sample status, and data health
- Project detail page with Overview as the default tab
- Collection Records tab using the existing task queue data
- Lightweight aggregation from existing `research_jobs`
- Rule-based recommended actions
- Basic create growth project form

### MVP Out Of Scope

- full opportunity scoring model
- complete creator and competitor module split
- complex permissions and collaboration
- multi-step project creation wizard
- automatic long-term monitoring strategy
- many AI templates
- full database rewrite

## Data Migration Strategy

Use a two-step rollout.

### Step 1: Soft Aggregation

Do not change crawler execution or worker logic.

Add an aggregation layer that exposes project-like cards from existing jobs. This can use:

- job metadata
- naming rules
- platform and keyword overlap
- optional `project_key`

Jobs that cannot be matched go into "Unclassified collection records".

### Step 2: Formal Project Model

After the UI validates the model, add durable project tables:

- `growth_projects`
- `growth_project_keywords`
- `research_jobs.growth_project_id`

Existing jobs can then be attached to projects explicitly.

## Success Criteria

The redesign is successful when:

- users can explain the page as growth projects, not crawler tasks
- the main page shows one row or card per business project
- each project has one clear recommended next action
- sample status is more prominent than job completion status
- collection tasks are still easy to find for troubleshooting
- existing research jobs remain usable without changing crawler execution

## Open Implementation Notes

- Keep the current research job APIs intact during MVP.
- Prefer adding an aggregation API over rewriting job execution.
- Avoid exposing crawler-specific settings in the main create flow.
- Treat AI opportunity scoring as optional until sample quality and rule recommendations are reliable.
