# MediaCrawler API-only Build

This folder is an extracted API-only copy. It keeps the WebUI, FastAPI backend,
TikHub API crawler, research analysis modules, store layer, and the local SQLite
database.

## What is included

- `api/` and `api/webui/` for backend routes and frontend assets.
- `media_platform/tikhub/` for TikHub API collection.
- `research/`, `database/`, `store/`, `model/`, and shared utility modules.
- `database/sqlite_tables.db`, copied from the original project.

## What is excluded

- Legacy platform browser crawler packages.
- Playwright/CDP browser tools.
- Playwright, OpenCV, and PyExecJS runtime dependencies.

## Run

Set the third-party API keys you need in `.env`, then start the backend:

- `TIKHUB_*` for existing TikHub-backed integrations
- `JUSTONE_*` for new JustOneAPI-backed integrations

They are intentionally separate. Do not replace `TIKHUB_*` with `JUSTONE_*` unless the corresponding code path has been migrated.

```powershell
.\scripts\start_api_server.ps1
```

For foreground logs during debugging:

```powershell
.\scripts\start_api_server.ps1 -Foreground
```

Realtime creator discovery currently depends on outbound HTTPS access to the
configured TikHub base URL (`TIKHUB_BASE_URL`). Future JustOneAPI migrations
should use `JUSTONE_BASE_URL` and `JUSTONE_API_KEY` without removing the
TikHub settings that other routes still depend on.

You can verify realtime availability after boot with:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8080/api/creator-search/realtime/check" `
  -ContentType "application/json" `
  -Body '{"raw_query":"K12 家长","platforms":["xhs","dy"]}'
```

The default SQLite path is:

```text
database/sqlite_tables.db
```

The original project at `D:\program\media_analyse\MediaCrawler` is not modified
by this extracted copy.
