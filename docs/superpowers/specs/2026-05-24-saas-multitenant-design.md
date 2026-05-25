# SaaS Multi-Tenant Growth Intelligence Design

Date: 2026-05-24
Status: Draft for user review
Scope: Productizing the current API-only MediaCrawler build as an externally available SaaS with registration, login, tenant isolation, configurable verticals, crawler execution, analysis, quotas, and a detailed platform admin console.

## Context

The current project is a FastAPI backend plus React WebUI around MediaCrawler-style collection and the `research` module. It already has many of the domain objects needed for a growth intelligence product:

- `ResearchVertical`
- `ResearchScenePack`
- `ResearchGrowthProject`
- `ResearchJob`
- `ResearchMonitorPool`
- `ResearchContentTracker`
- `ResearchPlatformCapability`
- `ResearchPlatformRateLimit`
- AI provider, prompt, analysis job, export, and report-related models

The current architecture is still effectively single-tenant. Routers are mounted directly under `/api`, there is no required authenticated request context, and repository methods generally query globally rather than by tenant. For an external SaaS this is the main risk: users, jobs, results, credentials, exports, quotas, and admin operations need strict tenant boundaries.

## Product Direction

The product should be framed as a multi-tenant growth intelligence SaaS, not as a crawler console with login.

The normal user flow should be:

1. Register or log in.
2. Create or enter an organization workspace.
3. Select a vertical.
4. Select or customize a scene pack.
5. Create a growth project.
6. Configure platforms, keywords, competitors, monitor pools, and collection depth.
7. Run crawler and analysis tasks.
8. Review dashboards, reports, opportunities, creator discovery, competitor monitoring, and exports.

The platform admin flow should be:

1. Monitor platform health, tenants, jobs, queues, worker status, and quota usage.
2. Manage users, organizations, subscriptions, quotas, and risk controls.
3. Manage system verticals, scene packs, prompt templates, platform capabilities, and crawler rate limits.
4. Inspect and intervene in failed or abusive tasks.

## Goals

- Add self-serve external user registration and login.
- Use organization-level multi-tenancy for all customer data.
- Preserve the existing `research` domain model where possible.
- Make crawler and analysis execution queue-backed and operable.
- Add quotas and usage accounting before expensive work starts.
- Add a detailed admin console for platform operations.
- Keep the first implementation as a modular monolith to avoid premature service decomposition.

## Non-Goals For The First Release

- Full payment-provider integration.
- Complex invitation and SSO flows.
- Fine-grained per-field permissions.
- Cross-region deployment.
- Full microservice split.
- A complete marketplace for third-party crawler plugins.

These can be added later after tenant isolation, quota controls, and task operations are reliable.

## Recommended Architecture

Use a modular monolith plus background workers:

```text
React WebUI
  -> FastAPI API
    -> Auth and organization context
    -> Billing and quota checks
    -> Research service layer
    -> Persistent task queue
      -> Crawler workers
      -> Analysis workers
      -> Export/report workers
    -> PostgreSQL
    -> Object storage for exports
```

Keep FastAPI, React, SQLAlchemy, and the existing `research` modules. Move from direct in-process execution toward persistent task records and worker polling.

PostgreSQL should be the production database. SQLite may remain for local development only.

## Backend Module Boundaries

Suggested package layout:

```text
api/
  routers/
    auth.py
    orgs.py
    billing.py
    admin/
    research/
  deps/
    auth.py
    org.py
    permissions.py

saas/
  auth/
  organizations/
  billing/
  audit/
  quotas/

research/
  models.py
  repository.py
  service.py
  scheduler.py
  execution.py

workers/
  crawler_worker.py
  analysis_worker.py
  export_worker.py
```

Request flow:

```text
Router
  -> authenticate request
  -> resolve current organization
  -> check role and feature permission
  -> check quota when needed
  -> service applies business rules
  -> repository performs scoped DB access
  -> audit log for important writes
```

Repository methods must receive `org_id` for tenant-owned resources. Methods like `list_jobs()`, `get_job(job_id)`, and `create_job(payload)` should become scoped methods such as `list_jobs(org_id)`, `get_job(org_id, job_id)`, and `create_job(org_id, user_id, payload)`.

## Authentication And Tenancy

Use organization-level tenancy rather than only user-level ownership.

Core tables:

```text
users
organizations
organization_memberships
refresh_tokens
platform_admins
audit_logs
```

`users` represents a person. `organizations` represents the customer workspace. `organization_memberships` maps users to organizations with roles:

```text
owner
admin
member
viewer
```

Registration creates:

1. A user.
2. A default organization.
3. An owner membership.
4. A refresh token session.

Authentication:

- Passwords are stored with Argon2 or bcrypt hashes.
- Access tokens are short-lived JWTs.
- Refresh tokens are persisted and revocable.
- Logout revokes the refresh token.
- Admin access is separate from organization membership and comes from `platform_admins`.

Every authenticated business request should resolve:

```text
current_user
current_org
current_membership
```

## SaaS Billing And Quotas

Core tables:

```text
plans
subscriptions
usage_events
quota_ledger
quota_adjustments
```

First-release plan fields:

```text
max_projects
daily_crawl_jobs
daily_collected_items
daily_ai_runs
max_concurrent_tasks
enabled_platforms
data_retention_days
allow_custom_auth_profiles
allow_custom_ai_provider
max_team_members
```

Quota checks should happen before enqueueing expensive work:

- Project creation checks `max_projects`.
- Crawler enqueue checks `daily_crawl_jobs`, `daily_collected_items`, `max_concurrent_tasks`, and `enabled_platforms`.
- AI analysis enqueue checks `daily_ai_runs` and provider availability.
- Export enqueue checks export allowance and data retention.

Actual usage should be recorded as immutable `usage_events`, not only as counters on a subscription row. This makes quota debugging, billing reconciliation, and admin dashboards possible.

## Research Data Ownership

Tenant-owned business tables must include `org_id`.

Highest priority tables:

```text
research_growth_projects
research_jobs
research_crawl_units
crawl_events
raw_records
research_posts
research_comments
research_authors
research_auth_profiles
ai_provider_configs
ai_analysis_jobs
ai_analysis_results
```

Second priority tables:

```text
research_monitor_pools
research_monitor_pool_creators
research_content_trackers
research_content_tracking_snapshots
research_competitor_accounts
research_leads
research_lead_touchpoints
research_lead_conversion_events
research_opportunity_feedback
research_backtests
research_ai_insight_runs
research_ai_hotspots
research_ai_topic_ideas
```

Global unique constraints should become tenant-scoped where the data belongs to a tenant:

```text
unique(name)
  -> unique(org_id, name)

unique(platform, creator_id)
  -> unique(org_id, platform, creator_id)

unique(platform, content_id)
  -> unique(org_id, platform, content_id)
```

Any endpoint that retrieves an object by ID must include `org_id` in the lookup. If another organization requests the ID, return 404 rather than leaking that the object exists.

## Verticals And Scene Packs

Verticals and scene packs should support both system templates and tenant customizations.

Recommended model:

```text
research_verticals
  id
  org_id nullable
  source: system | custom
  code
  name
  description
  enabled

research_scene_packs
  id
  org_id nullable
  vertical_id
  source: system | custom
  name
  description
  primary_goal
  default_platforms
  default_collection_depth
  default_ai_template
  archived
  enabled
```

`org_id = null` means a system template managed by platform admins. `org_id` set means tenant-owned custom content.

User project creation should allow:

1. Selecting a system vertical and scene pack.
2. Copying default keywords, negative keywords, default platforms, and analysis prompts into a project.
3. Customizing the copy without modifying the system template.

Admin-managed system verticals should include:

- code
- name
- recommended platforms
- default keywords
- negative keywords
- synonyms
- tag groups
- prompt templates
- sample quality rules
- risk keywords

## Task Queue And Workers

API requests should not execute crawler or AI work directly. They should create task records.

Core tables:

```text
task_queue
task_attempts
worker_heartbeats
task_logs
```

Task fields:

```text
id
org_id
user_id
project_id
research_job_id
task_type: crawl | analysis | export | report
platform
status: pending | running | succeeded | failed | cancelled
priority
quota_reserved
quota_cost
scheduled_at
started_at
finished_at
locked_by
locked_at
error_code
error_message
payload_json
result_json
created_at
updated_at
```

Workers should:

1. Poll for pending tasks.
2. Lock one task using DB row locking or a Redis queue mechanism.
3. Write a worker heartbeat.
4. Create an attempt record.
5. Execute crawler, analysis, export, or report work.
6. Write task logs and result metadata.
7. Record final usage events.
8. Release quota reservations or apply final quota cost.

The current in-memory execution state should be replaced for production. Existing scheduler and execution modules can be adapted to create and process queue tasks.

## Platform Capabilities And Rate Limits

Platform capability and rate limit records remain platform-admin managed.

Admin must be able to configure:

```text
enabled
crawl_search_enabled
crawl_detail_enabled
crawl_creator_enabled
comments_enabled
analysis_enabled
daily_monitor_enabled
keyword_heat_enabled
rate_limit_per_minute
max_daily_jobs
cooldown_seconds
global_concurrency
```

If a platform is paused, users can still view historical data but cannot enqueue new tasks for that platform. Queued tasks for the paused platform should either stay pending with a paused reason or be marked as paused by platform configuration.

## User-Facing Routes

Suggested routes:

```text
/login
/register
/onboarding

/app
/app/dashboard
/app/projects
/app/projects/new
/app/projects/:projectId
/app/projects/:projectId/jobs
/app/projects/:projectId/reports
/app/projects/:projectId/settings

/app/verticals
/app/scene-packs
/app/competitors
/app/content-tracking
/app/creator-discovery
/app/keyword-opportunities
/app/exports
/app/billing
/app/team
/app/settings
```

Suggested user API groups:

```text
/api/auth/*
/api/me
/api/orgs/*
/api/team/*

/api/research/verticals
/api/research/scene-packs
/api/research/projects
/api/research/projects/{project_id}
/api/research/projects/{project_id}/jobs
/api/research/jobs/{job_id}/execute
/api/research/jobs/{job_id}/events
/api/research/jobs/{job_id}/reports

/api/research/competitors/*
/api/research/content-trackers/*
/api/research/creator-search/*
/api/research/keyword-opportunities/*

/api/billing/*
/api/usage/*
/api/exports/*
```

## Admin Console

Admin should have its own shell and route namespace:

```text
/admin
/admin/dashboard
/admin/users
/admin/orgs
/admin/orgs/:orgId
/admin/plans
/admin/usage
/admin/tasks
/admin/workers
/admin/platforms
/admin/verticals
/admin/scene-packs
/admin/prompts
/admin/ai-providers
/admin/audit-logs
/admin/system-settings
```

Suggested admin API groups:

```text
/api/admin/dashboard
/api/admin/users
/api/admin/orgs
/api/admin/orgs/{org_id}
/api/admin/orgs/{org_id}/members
/api/admin/orgs/{org_id}/usage
/api/admin/orgs/{org_id}/tasks
/api/admin/orgs/{org_id}/quota-adjustments

/api/admin/plans
/api/admin/subscriptions
/api/admin/usage-events

/api/admin/tasks
/api/admin/tasks/{task_id}
/api/admin/tasks/{task_id}/cancel
/api/admin/tasks/{task_id}/retry
/api/admin/workers

/api/admin/platforms
/api/admin/platforms/{platform}/capability
/api/admin/platforms/{platform}/rate-limit
/api/admin/platforms/{platform}/pause

/api/admin/verticals
/api/admin/scene-packs
/api/admin/prompts
/api/admin/ai-providers
/api/admin/audit-logs
```

### Admin Dashboard

Top metrics:

- Active organizations
- New users today
- Running tasks
- Queue backlog
- Collected items today
- AI runs today
- Task failure rate
- Estimated AI/provider cost

Sections:

- System health: database, queue, workers, AI providers, platform status.
- Task posture: running, queued, failed, cancelled, retrying.
- Tenant risk: abnormal usage, high failure rate, suspected abuse, quota spikes.
- Platform performance: success rate, latency, error codes, cooldown state.

### User And Organization Management

User list filters:

- email
- status
- organization
- plan
- created date
- last login date

Organization detail should show:

- organization profile
- subscription and plan
- members and roles
- active projects
- recent jobs
- failed jobs
- data volume
- quota usage
- auth profile changes
- login records
- audit log
- admin actions

Admin actions:

- disable or restore user
- disable or restore organization
- reset active sessions
- adjust quota
- switch plan
- pause organization tasks
- view tenant data volume

### Plan And Quota Management

Admin can manage:

- plan names
- limits
- enabled platforms
- team member allowance
- data retention
- custom auth profile allowance
- custom AI provider allowance

Admin can also create organization-specific quota adjustments:

- temporary crawl job increase
- temporary collected item increase
- AI run credit
- concurrency override
- platform blocklist

### Task Center

Task filters:

- organization
- platform
- status
- worker
- task type
- created date
- error code

List fields:

- task ID
- organization
- project
- platform
- task type
- status
- priority
- quota cost
- start time
- duration
- output count
- error summary

Detail panel:

- input payload
- execution logs
- task attempts
- worker heartbeat
- quota reservation and usage events
- output statistics
- error stack
- retry history

Actions:

- cancel
- retry
- pause organization tasks
- raise priority
- lower priority
- mark reviewed
- download logs

### Platform Management

Admin can manage each platform:

- enabled state
- supported collection modes
- comment crawling availability
- default rate limit
- global concurrency
- retry attempts
- cooldown
- daily request count
- success rate
- latest errors

The page needs a one-click pause action for platform incidents.

### Vertical And Scene Pack Management

Admin can manage system templates:

- vertical code and name
- status
- recommended platforms
- default keywords
- negative keywords
- synonyms
- tag groups
- scene packs
- prompt templates
- sample quality rules
- risk keywords

Users can consume these templates when creating projects but cannot modify system templates.

### AI Provider And Prompt Management

Admin can manage:

- provider name
- base URL
- encrypted API key
- model
- timeout
- max concurrency
- default params
- provider status
- task-specific prompt templates
- vertical-specific prompt templates
- output schemas
- provider health test results

Advanced tenant plans may allow custom tenant-owned AI providers. Those providers must be scoped by `org_id`.

### Audit And Compliance

Audit logs must capture:

- login
- logout
- registration
- organization changes
- membership changes
- project creation and deletion
- task creation, cancellation, retry
- export download
- auth profile creation and update
- AI provider creation and update
- admin quota adjustment
- admin user or organization disablement
- platform pause or resume

Crawler-specific compliance controls:

- platform pause switch
- per-tenant rate limits
- export limits
- sensitive task review flag
- auth profile change log
- suspicious usage detection

## Frontend Structure

Suggested frontend layout:

```text
api/webui/src/pages/auth
api/webui/src/pages/app
api/webui/src/pages/admin
api/webui/src/components/admin
api/webui/src/components/app
api/webui/src/lib/auth.ts
api/webui/src/lib/org.ts
api/webui/src/lib/api.ts
```

Use two route shells:

```text
UserAppShell
AdminAppShell
```

The admin shell should not reuse the normal product navigation. Admin users need platform operations, diagnostics, and intervention workflows; normal users need project and insight workflows.

## Error Handling

User-facing errors should use stable error codes and product-safe messages:

```text
AUTH_REQUIRED
ORG_FORBIDDEN
QUOTA_EXCEEDED
PLATFORM_DISABLED
TASK_ALREADY_RUNNING
CRAWLER_START_FAILED
AI_PROVIDER_UNAVAILABLE
EXPORT_NOT_FOUND
```

Admin task details should expose deeper diagnostics:

```text
error_code
error_message
stack_trace
worker_id
attempt_count
payload_json
recent_logs
```

## MVP Iterations

### Iteration 1: SaaS Foundation

Deliver:

- `users`
- `organizations`
- `organization_memberships`
- `refresh_tokens`
- `platform_admins`
- `audit_logs`
- register
- login
- refresh
- logout
- `/api/me`
- `/api/orgs/current`

Acceptance:

- Users can register.
- Registration creates a default organization.
- Login returns access and refresh tokens.
- Logged-out users cannot access `/api/research/*`.
- Logged-in users can resolve their current organization.

### Iteration 2: Tenant Isolation For Core Research Data

Deliver:

- `org_id` on core research tables.
- Scoped repository methods.
- Scoped route dependencies.
- Tenant-safe 404 behavior.

Acceptance:

- Organization A cannot list or read organization B projects.
- Organization A cannot access organization B jobs by guessing IDs.
- New projects, jobs, raw records, posts, comments, and analysis jobs are written with `org_id`.

### Iteration 3: User Workspace

Deliver:

- `/app/dashboard`
- `/app/projects`
- `/app/projects/new`
- `/app/projects/:projectId`
- `/app/projects/:projectId/jobs`
- `/app/projects/:projectId/reports`
- `/app/billing`
- `/app/settings`

Acceptance:

- User lands in the workspace after login.
- User creates a growth project by selecting vertical, platform, and keywords.
- User can start one collection task.
- User can view task status and basic results.

### Iteration 4: Admin Foundation

Deliver:

- `/admin/dashboard`
- `/admin/users`
- `/admin/orgs`
- `/admin/orgs/:orgId`
- `/admin/tasks`
- `/admin/platforms`

Acceptance:

- Normal users cannot access `/admin`.
- Platform admins can view users, organizations, and tasks.
- Admin can disable or restore users and organizations.
- Admin can pause a platform.
- Admin writes are recorded in audit logs.

### Iteration 5: Plans And Quotas

Deliver:

- `plans`
- `subscriptions`
- `usage_events`
- `quota_ledger`
- `quota_adjustments`
- quota checks before task enqueue

Acceptance:

- Project creation respects plan limits.
- Task enqueue respects daily crawl job limits.
- Task completion writes usage events.
- Quota-exceeded responses use a stable error code.
- Admin can grant a temporary quota adjustment.

### Iteration 6: Persistent Task Queue

Deliver:

- `task_queue`
- `task_attempts`
- `worker_heartbeats`
- `task_logs`
- crawler worker
- analysis worker

Acceptance:

- API enqueues tasks instead of running them directly.
- Worker claims and executes tasks.
- Failed tasks create attempt records.
- API restart does not lose task state.
- Admin can cancel and retry tasks.

### Iteration 7: System Verticals And Scene Packs

Deliver:

- system and tenant-scoped verticals
- system and tenant-scoped scene packs
- admin template editor
- project creation from template

Acceptance:

- Admin can create a system vertical.
- Admin can create a system scene pack.
- User can create a project from a system scene pack.
- Tenant customization does not modify the system template.
- Custom verticals are invisible to other tenants.

## Testing Strategy

Required tests:

- Registration, login, refresh, logout.
- Unauthenticated requests are rejected.
- Cross-organization reads return 404.
- Cross-organization writes are rejected.
- Platform admin access is separated from organization roles.
- Quota checks block task enqueue when limits are exceeded.
- Usage events are written after task completion.
- Platform pause prevents new task enqueue.
- Task queue supports enqueue, claim, success, failure, retry, and cancel.
- Admin writes create audit logs.

## First Release Completion Standard

The first release is complete when:

- External users can self-register and log in.
- Each user's data is isolated by organization.
- Users can create a project and run one collection or analysis flow.
- Admins can inspect and intervene in users, organizations, tasks, and platforms.
- Quotas prevent unlimited crawler or AI resource consumption.

## Implementation Notes

- Keep the project as a modular monolith for the first production version.
- Make PostgreSQL the production database target.
- Keep SQLite only for local development.
- Start by scoping the smallest core data path, then expand table coverage.
- Do not expose raw Python exceptions to normal users.
- Do not allow any tenant-owned credential, cookie, AI key, or export to be read without matching `org_id`.
- Treat Admin pages as operational tools with diagnostics and intervention actions, not just CRUD tables.
