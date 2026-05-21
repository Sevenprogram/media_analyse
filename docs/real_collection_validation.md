# Real Collection Validation

Run real platform validation only after the server stack is healthy and the worker hardening checks pass.

Use one platform and one keyword at a time:

1. Configure `SAVE_DATA_OPTION=postgres`.
2. Configure `RESEARCH_AUTHOR_HASH_SALT`.
3. Configure an auth profile for the target platform if the platform needs cookies.
4. Configure a conservative platform rate limit.
5. Create one research job with one keyword and limited comments.
6. Schedule the job.
7. Confirm one crawl unit is created.
8. Start one worker.
9. Confirm events appear in `crawl_events`.
10. Confirm normalized rows appear in `research_posts` and, if enabled, `research_comments`.
11. Confirm charts and export can read the collected rows.

Checklist command:

```powershell
uv run python -m research.validation --platform wb
```

API:

```text
GET /api/research/validation/checklist?platform=wb
```

Recommended order:

1. Weibo with one keyword.
2. Zhihu with one keyword or one question id.
3. Bilibili with one video id and limited comments.
4. Xiaohongshu with one note id.
5. Douyin with one video id.
6. Kuaishou with one video id.

Do not run full collection until the limited validation for that platform has passed.
