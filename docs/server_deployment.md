# Server Deployment Guide

This deployment profile runs MediaCrawler as a research collection service:

- `api`: FastAPI WebUI and research API.
- `scheduler`: expands pending research jobs into crawl units.
- `worker`: claims crawl units, starts platform crawlers, and backfills normalized research data.
- `postgres`: primary research database.

## Local Compose Run

Copy the environment template first:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set a long private `RESEARCH_AUTHOR_HASH_SALT`. Do not change it after data has been collected, because author hashes depend on this value.

Start the stack:

```powershell
docker compose up --build
```

The Dockerfile builds the React research console during the image build and
copies `api/webui/dist` into the API image, so `/research` serves the compiled
frontend in server deployments.

Open:

```text
http://127.0.0.1:8080/
http://127.0.0.1:8080/research
```

## Manual Server Commands

Initialize tables:

```powershell
uv run python -m research.bootstrap --db-type postgres
```

Schedule one job:

```powershell
uv run python -m research.scheduler --job-id 1
```

Run scheduler loop:

```powershell
uv run python -m research.scheduler --interval 60
```

Run one worker pass:

```powershell
uv run python -m research.worker --once --headless
```

Run worker loop:

```powershell
uv run python -m research.worker --interval 10 --headless
```

Inspect worker status:

```text
GET /api/research/workers/status
```

Configure platform rate limiting:

```text
PUT /api/research/platform-rate-limits/wb
```

Configure platform cookies:

```text
POST /api/research/auth-profiles
```

Build the real collection validation checklist:

```powershell
uv run python -m research.validation --platform wb
```

## Research Workflow

1. Create a research job in `/research`.
2. Optional: enable periodic scheduling on the job and set `schedule_interval_minutes`.
3. Call `POST /api/research/jobs/{job_id}/schedule`, or let the scheduler loop pick up pending/due jobs.
4. The scheduler marks the job `queued` after crawl units are created.
5. Worker processes claim crawl units from `research_crawl_units` with PostgreSQL row locks.
6. Failed units move to `retrying` with backoff before they can be claimed again.
7. Each unit records events in `crawl_events`.
8. Worker heartbeats are visible through the worker status API.
9. Normalized posts, comments, authors, raw records, AI results, charts, and exports stay tied to the research job id.

The first production-safe mode is still conservative: one unit is `platform + keyword` for search jobs, `platform + target_id` for detail jobs, or `platform + creator_id` for creator jobs. Full-depth collection should remain opt-in with comment guardrails.
