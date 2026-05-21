# Research Backtesting Design

## Goal

Add a historical backtesting workflow for the research console so users can validate keyword heat, creator scoring, competitor composition, and opportunity summaries against the past 7/14/30 days of real collected data.

## Scope

The first version is a single-machine orchestration layer on top of the existing research database. It does not introduce a distributed queue or new crawler provider behavior. It uses local normalized posts first, can optionally create a historical research search job, and then replays daily snapshots by simulating each day as the current date.

## User Flow

1. Open the research console and go to the historical backtest page.
2. Enter a scenario such as `K12教育 + 单亲妈妈`.
3. Select platforms, date range, and whether to use local data only or create a supplemental research job.
4. Start the backtest.
5. Review daily keyword heat, opportunity score, sample sufficiency, evidence, and suggested calibration notes.

## Backend Design

New API group: `/api/backtests`.

- `POST /api/backtests`: create a backtest record.
- `GET /api/backtests`: list recent backtests.
- `GET /api/backtests/{id}`: read one backtest.
- `POST /api/backtests/{id}/run`: execute replay against normalized data.
- `GET /api/backtests/{id}/report`: return the stored report.

The run step loads normalized posts from `research_posts`, filters by platform, keyword, and publish time, then computes daily replay results. For each replay date it calls the existing keyword heat aggregator with `now` set to that date end. The report contains:

- daily rows with sample counts and keyword heat labels;
- keyword summary for the latest replay date;
- sample sufficiency status;
- calibration notes for business review;
- optional supplemental research job id when a crawl job was created.

## Data Model

Add `research_backtests`:

- scenario, vertical_id, scene_pack_id
- keywords, platforms
- start_date, end_date
- use_local_data, use_tikhub_backfill, replay_daily
- status
- research_job_id
- report_json, error_message
- timestamps

The table stores the report as JSON because this is an analysis artifact, not a core business entity.

## Frontend Design

Add a sidebar entry `历史回测`. The page includes:

- scenario and keyword inputs;
- platform checkboxes;
- date range and 7/14/30 day quick presets;
- switches for local data and TikHub supplemental job;
- run button;
- report cards for sample sufficiency, daily heat, and calibration notes.

## Testing

Backend unit/API tests cover:

- creating and listing backtests;
- running a backtest from seeded historical posts;
- daily replay labels and sample counts;
- report endpoint behavior;
- validation for invalid date ranges and missing keywords.

Frontend verification uses `npm.cmd run build`.
