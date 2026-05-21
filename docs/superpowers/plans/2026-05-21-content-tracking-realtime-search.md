# Content Tracking Realtime Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional realtime TikHub search path to the content tracking page that searches Xiaohongshu and Douyin, imports results, and refreshes local candidates with a progress-bar UI.

**Architecture:** Keep the current local search path as the default. When `SimilarContentSearchRequest.realtime` is true, the content tracking router resolves the requested platforms to `xhs`/`dy`, creates a `content_realtime_discovery` research job, waits for completion, then reruns the same local `search_similar_content(...)` path. The frontend adds a checkbox and stage-based progress bar around the existing search button.

**Tech Stack:** FastAPI, Pydantic, pytest, React, TypeScript, Vite, existing TikHub crawler/research job pipeline.

---

## File Structure

- Modify `api/routers/content_tracking.py`: add realtime platform resolver, shared local search helper, and `realtime=true` branch in `/search-similar`.
- Modify `tests/test_content_tracking_api.py`: add backend coverage for platform resolution, realtime search scheduling, unsupported platforms, and local behavior preservation.
- Modify `api/webui/src/pages/ResearchModulePages.tsx`: add realtime checkbox, progress state, realtime request flow, unsupported platform guard, and realtime status messaging.
- Modify `api/webui/src/styles.css`: add compact checkbox/progress bar styles scoped to content tracking.

No new Python runtime module is needed. The existing `SimilarContentSearchRequest.realtime` field, TikHub endpoints, and research scheduler are enough.

---

### Task 1: Backend Realtime Platform Resolution

**Files:**
- Modify: `api/routers/content_tracking.py`
- Test: `tests/test_content_tracking_api.py`

- [ ] **Step 1: Write failing resolver tests**

Append these tests near the existing realtime content tracking tests in `tests/test_content_tracking_api.py`:

```python
def test_content_realtime_platform_resolution_all_defaults_to_xhs_and_dy():
    import api.routers.content_tracking as content_router

    assert content_router._resolve_realtime_platforms([]) == ["xhs", "dy"]


def test_content_realtime_platform_resolution_keeps_supported_single_platform():
    import api.routers.content_tracking as content_router

    assert content_router._resolve_realtime_platforms(["xhs"]) == ["xhs"]
    assert content_router._resolve_realtime_platforms(["dy"]) == ["dy"]


def test_content_realtime_platform_resolution_rejects_unsupported_platform():
    import api.routers.content_tracking as content_router

    try:
        content_router._resolve_realtime_platforms(["bili"])
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
        assert "小红书和抖音" in str(getattr(exc, "detail", exc))
    else:
        raise AssertionError("unsupported realtime platform should fail")
```

- [ ] **Step 2: Run resolver tests and verify they fail**

Run:

```bash
pytest tests/test_content_tracking_api.py::test_content_realtime_platform_resolution_all_defaults_to_xhs_and_dy tests/test_content_tracking_api.py::test_content_realtime_platform_resolution_keeps_supported_single_platform tests/test_content_tracking_api.py::test_content_realtime_platform_resolution_rejects_unsupported_platform -q
```

Expected: FAIL because `_resolve_realtime_platforms` does not exist.

- [ ] **Step 3: Implement resolver**

In `api/routers/content_tracking.py`, add this constant and helper after `router = APIRouter(...)`:

```python
REALTIME_CONTENT_PLATFORMS = {"xhs", "dy"}


def _resolve_realtime_platforms(platforms: list[str]) -> list[str]:
    selected = [item for item in platforms if item]
    if not selected:
        return ["xhs", "dy"]

    unsupported = sorted(set(selected) - REALTIME_CONTENT_PLATFORMS)
    if unsupported:
        raise HTTPException(
            status_code=400,
            detail="实时搜索暂只支持小红书和抖音",
        )
    return selected
```

- [ ] **Step 4: Run resolver tests and verify they pass**

Run:

```bash
pytest tests/test_content_tracking_api.py::test_content_realtime_platform_resolution_all_defaults_to_xhs_and_dy tests/test_content_tracking_api.py::test_content_realtime_platform_resolution_keeps_supported_single_platform tests/test_content_tracking_api.py::test_content_realtime_platform_resolution_rejects_unsupported_platform -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/routers/content_tracking.py tests/test_content_tracking_api.py
git commit -m "feat: resolve realtime content platforms"
```

---

### Task 2: Backend Realtime Search Branch

**Files:**
- Modify: `api/routers/content_tracking.py`
- Test: `tests/test_content_tracking_api.py`

- [ ] **Step 1: Write failing realtime search tests**

Append these tests after the resolver tests in `tests/test_content_tracking_api.py`:

```python
def test_search_similar_realtime_schedules_job_and_refreshes(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    calls = {"created_job": None, "scheduled": None, "waited": None}

    class FakeRepository:
        async def create_job(self, payload):
            calls["created_job"] = payload
            return {"id": 42, **payload}

        async def get_job(self, job_id):
            return {"id": job_id, "status": "completed", "keywords": ["K12"]}

        async def list_all_posts(self, job_id=None, platform=None, limit=None):
            calls["list_job_id"] = job_id
            return [
                {
                    "platform": "xhs",
                    "platform_post_id": "p-live",
                    "title": "K12 realtime imported post",
                    "content": "K12 tutoring",
                    "engagement_json": {"liked_count": 40},
                }
            ]

    async def fake_schedule(job_id, background=True, force_schedule=True):
        calls["scheduled"] = {
            "job_id": job_id,
            "background": background,
            "force_schedule": force_schedule,
        }
        return {"status": "accepted", "job_id": job_id}

    async def fake_wait(job_id):
        calls["waited"] = job_id
        return {"id": job_id, "status": "completed", "keywords": ["K12"]}

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(content_router, "schedule_and_execute_research_job", fake_schedule)
    monkeypatch.setattr(content_router, "wait_for_research_job_status", fake_wait)

    client = TestClient(app)
    response = client.post(
        "/api/content-tracking/search-similar",
        json={"keywords": ["K12"], "platforms": [], "realtime": True, "limit": 50},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["realtime"]["enabled"] is True
    assert body["realtime"]["job_id"] == 42
    assert body["realtime"]["platforms"] == ["xhs", "dy"]
    assert body["realtime"]["status"] == "completed"
    assert body["realtime"]["matched_count"] == 1
    assert body["candidates"][0]["platform_post_id"] == "p-live"
    assert body["candidates"][0]["evidence"]["source"] == "realtime_imported"
    assert calls["created_job"]["topic"] == "content_realtime_discovery"
    assert calls["created_job"]["platforms"] == ["xhs", "dy"]
    assert calls["scheduled"]["job_id"] == 42
    assert calls["waited"] == 42


def test_search_similar_realtime_rejects_unsupported_platform(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/content-tracking/search-similar",
        json={"keywords": ["K12"], "platforms": ["bili"], "realtime": True},
    )

    assert response.status_code == 400
    assert "小红书和抖音" in response.json()["detail"]


def test_search_similar_realtime_busy_returns_409(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def create_job(self, payload):
            return {"id": 7, **payload}

    async def fake_schedule(job_id, background=True, force_schedule=True):
        return {"status": "busy", "job_id": 99, "message": "A research execution is already running"}

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(content_router, "schedule_and_execute_research_job", fake_schedule)

    client = TestClient(app)
    response = client.post(
        "/api/content-tracking/search-similar",
        json={"keywords": ["K12"], "platforms": ["xhs"], "realtime": True},
    )

    assert response.status_code == 409
    assert "already running" in response.json()["detail"]
```

- [ ] **Step 2: Run realtime branch tests and verify they fail**

Run:

```bash
pytest tests/test_content_tracking_api.py::test_search_similar_realtime_schedules_job_and_refreshes tests/test_content_tracking_api.py::test_search_similar_realtime_rejects_unsupported_platform tests/test_content_tracking_api.py::test_search_similar_realtime_busy_returns_409 -q
```

Expected: FAIL because `/search-similar` ignores `realtime`.

- [ ] **Step 3: Extract local search helper**

In `api/routers/content_tracking.py`, replace the current `search_similar` body with a helper-backed version:

```python
@router.post("/search-similar")
async def search_similar(request: SimilarContentSearchRequest):
    require_research_database()
    if request.realtime:
        return await _search_similar_with_realtime(request)

    repository = ResearchRepository()
    candidates = await _local_similar_candidates(repository, request)
    return {"candidates": candidates}


async def _local_similar_candidates(
    repository: ResearchRepository,
    request: SimilarContentSearchRequest,
    *,
    job_id: int | None = None,
    evidence_source: str | None = None,
) -> list[dict[str, Any]]:
    platform = request.platforms[0] if len(request.platforms) == 1 else None
    posts = await repository.list_all_posts(
        job_id=job_id,
        platform=platform,
        limit=500,
    )
    candidates = search_similar_content(
        keywords=request.keywords,
        posts=posts,
        limit=request.limit,
    )
    if evidence_source:
        for candidate in candidates:
            evidence = candidate.setdefault("evidence", {})
            evidence["source"] = evidence_source
    return candidates
```

Then update any existing call sites in the same file only if needed by type errors. The current tracker analysis can stay as-is.

- [ ] **Step 4: Implement realtime search helper**

Add this helper below `_local_similar_candidates`:

```python
async def _search_similar_with_realtime(request: SimilarContentSearchRequest) -> dict[str, Any]:
    realtime_platforms = _resolve_realtime_platforms(request.platforms)
    repository = ResearchRepository()
    job = await repository.create_job(
        {
            "name": f"content realtime discovery - {' '.join(request.keywords)}",
            "topic": "content_realtime_discovery",
            "platforms": realtime_platforms,
            "collection_mode": "search",
            "keywords": request.keywords,
            "target_ids": [],
            "creator_ids": [],
            "start_date": date.today(),
            "end_date": date.today(),
            "status": "pending",
            "comment_policy": {
                "enable_comments": False,
                "enable_sub_comments": False,
            },
            "raw_record_mode": "minimal",
            "anonymize_authors": True,
        }
    )

    execution = await schedule_and_execute_research_job(
        job["id"],
        background=True,
        force_schedule=True,
    )
    if execution.get("status") == "busy":
        raise HTTPException(
            status_code=409,
            detail=execution.get("message") or "A research execution is already running",
        )

    completed_job = await wait_for_research_job_status(job["id"])
    if completed_job is None:
        raise HTTPException(status_code=404, detail="Content discovery job not found")

    candidates = await _local_similar_candidates(
        repository,
        request,
        job_id=job["id"],
        evidence_source="realtime_imported",
    )
    return {
        "realtime": {
            "enabled": True,
            "job_id": job["id"],
            "platforms": realtime_platforms,
            "status": completed_job.get("status"),
            "matched_count": len(candidates),
            "errors": [],
        },
        "candidates": candidates,
    }
```

- [ ] **Step 5: Keep `/realtime-discovery` behavior consistent**

In `start_realtime_content_discovery`, replace the current platform validation block:

```python
    if not request.platforms:
        raise HTTPException(
            status_code=400,
            detail="Realtime content discovery requires selected or global default platforms",
        )
```

with:

```python
    realtime_platforms = _resolve_realtime_platforms(request.platforms)
```

and change the job payload line:

```python
            "platforms": request.platforms,
```

to:

```python
            "platforms": realtime_platforms,
```

- [ ] **Step 6: Run backend content tracking API tests**

Run:

```bash
pytest tests/test_content_tracking_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add api/routers/content_tracking.py tests/test_content_tracking_api.py
git commit -m "feat: run realtime content search from tracking"
```

---

### Task 3: Frontend Realtime Checkbox and Progress State

**Files:**
- Modify: `api/webui/src/pages/ResearchModulePages.tsx`

- [ ] **Step 1: Add realtime state**

Inside `ContentTrackingPage`, after the existing `error` state, add:

```tsx
  const [realtimeSearchEnabled, setRealtimeSearchEnabled] = React.useState(false);
  const [realtimeProgress, setRealtimeProgress] = React.useState(0);
  const [realtimeStage, setRealtimeStage] = React.useState("");
  const [realtimeMetadata, setRealtimeMetadata] = React.useState<UnknownRecord | null>(null);
```

After `platformQuery`, add:

```tsx
  const realtimeSupportedPlatform = platform === "all" || platform === "xhs" || platform === "dy";
```

- [ ] **Step 2: Add progress helpers**

Inside `ContentTrackingPage`, before `runLocalSearch`, add:

```tsx
  function setRealtimeStep(progress: number, stage: string) {
    setRealtimeProgress(progress);
    setRealtimeStage(stage);
  }

  function resetRealtimeProgress() {
    setRealtimeProgress(0);
    setRealtimeStage("");
    setRealtimeMetadata(null);
  }
```

- [ ] **Step 3: Update extract keyword reset behavior**

In `runExtractKeywords`, after `setHasSearched(false);`, add:

```tsx
      resetRealtimeProgress();
```

- [ ] **Step 4: Update search request flow**

Replace the body of `runLocalSearch` after the keyword validation with this code:

```tsx
    if (realtimeSearchEnabled && !realtimeSupportedPlatform) {
      setError("实时搜索暂只支持小红书和抖音");
      return;
    }
    setRunning("search");
    setError(null);
    setMessage(null);
    setHasSearched(true);
    if (realtimeSearchEnabled) {
      setRealtimeStep(10, "准备实时搜索");
    } else {
      resetRealtimeProgress();
    }
    try {
      if (realtimeSearchEnabled) {
        setRealtimeStep(35, platform === "all" ? "正在搜索小红书和抖音" : platform === "xhs" ? "正在搜索小红书" : "正在搜索抖音");
      }
      const similarPromise = api<{ candidates: UnknownRecord[]; realtime?: UnknownRecord }>("/api/content-tracking/search-similar", {
        method: "POST",
        body: JSON.stringify({
          keywords: terms,
          platforms: platformPayload,
          realtime: realtimeSearchEnabled,
          limit: 50,
        }),
      });
      if (realtimeSearchEnabled) {
        setRealtimeStep(65, "正在写入内容库");
      }
      const analysisPromise = api<UnknownRecord>("/api/content-tracking/analyze", {
        method: "POST",
        body: JSON.stringify({ query: terms.join(" "), platform: platformQuery, limit: 30 }),
      });
      const [similar, analysis] = await Promise.all([similarPromise, analysisPromise]);
      if (realtimeSearchEnabled) {
        setRealtimeStep(85, "正在刷新本地结果");
      }
      setCandidates(similar.candidates || []);
      setComments(array(analysis.comments));
      setLocalSummary(asRecord(analysis.summary));
      setInsights(textArray(analysis.insights));
      setRealtimeMetadata(asRecord(similar.realtime));
      if (realtimeSearchEnabled) {
        setRealtimeStep(100, "搜索完成");
        setMessage(`实时搜索完成，找到 ${similar.candidates?.length || 0} 条同类内容`);
      } else {
        setMessage(`本地库找到 ${similar.candidates?.length || 0} 条同类内容`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(null);
    }
```

This replaces the existing `setRunning("search")` through `finally` block inside `runLocalSearch`.

- [ ] **Step 5: Add checkbox UI**

Inside the JSX, immediately after the `.content-source-preview` div and before `.content-action-row`, add:

```tsx
          <label className={`content-realtime-toggle ${!realtimeSupportedPlatform ? "disabled" : ""}`}>
            <input
              type="checkbox"
              checked={realtimeSearchEnabled}
              disabled={!realtimeSupportedPlatform || Boolean(running)}
              onChange={(event) => {
                setRealtimeSearchEnabled(event.target.checked);
                if (!event.target.checked) resetRealtimeProgress();
              }}
            />
            <span>
              <strong>是否实时搜索</strong>
              <small>{realtimeSupportedPlatform ? "勾选后会先从 TikHub 搜索小红书/抖音并入库" : "实时搜索暂只支持小红书和抖音"}</small>
            </span>
          </label>
```

- [ ] **Step 6: Update search button label**

Replace the search button text:

```tsx
              {running === "search" ? <Loader2 size={16} className="spin" /> : <Search size={16} />}搜索同类内容
```

with:

```tsx
              {running === "search" ? <Loader2 size={16} className="spin" /> : <Search size={16} />}
              {realtimeSearchEnabled ? "实时搜索并入库" : "搜索同类内容"}
```

If the existing file displays mojibake literals, preserve the file's current style only where surrounding text is already mojibake; do not convert unrelated text in this task.

- [ ] **Step 7: Add progress bar UI**

After the `.content-action-row` div and before the status message block, add:

```tsx
          {realtimeSearchEnabled && (running === "search" || realtimeProgress > 0) && (
            <div className="content-realtime-progress" aria-live="polite">
              <div className="content-realtime-progress-header">
                <span>{realtimeStage || "等待实时搜索"}</span>
                <strong>{realtimeProgress}%</strong>
              </div>
              <div className="content-realtime-progress-track">
                <span style={{ width: `${realtimeProgress}%` }} />
              </div>
              {realtimeMetadata && (
                <small>
                  Job #{text(realtimeMetadata.job_id)} · {text(realtimeMetadata.status, "-")} · 匹配 {formatOptionalNumber(realtimeMetadata.matched_count)} 条
                </small>
              )}
            </div>
          )}
```

- [ ] **Step 8: Run TypeScript build and fix type errors**

Run:

```bash
npm.cmd run build
```

Expected: PASS. If TypeScript complains about optional fields, keep the existing `UnknownRecord` helpers and use `text(...)`, `asRecord(...)`, `formatOptionalNumber(...)` instead of introducing new types.

- [ ] **Step 9: Commit**

```bash
git add api/webui/src/pages/ResearchModulePages.tsx
git commit -m "feat: add realtime content search controls"
```

---

### Task 4: Frontend Progress Styling

**Files:**
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Add styles**

Append these styles near the existing `.content-*` rules in `api/webui/src/styles.css`:

```css
.content-realtime-toggle {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-muted);
  color: var(--text);
}

.content-realtime-toggle input {
  margin-top: 3px;
}

.content-realtime-toggle span {
  display: grid;
  gap: 3px;
}

.content-realtime-toggle strong {
  font-size: 13px;
  font-weight: 700;
}

.content-realtime-toggle small {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}

.content-realtime-toggle.disabled {
  opacity: 0.62;
}

.content-realtime-progress {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
}

.content-realtime-progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.content-realtime-progress-header strong {
  font-variant-numeric: tabular-nums;
}

.content-realtime-progress-track {
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface-muted);
}

.content-realtime-progress-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--accent);
  transition: width 180ms ease;
}

.content-realtime-progress small {
  color: var(--muted);
  font-size: 12px;
}
```

If any CSS variable names do not exist in this stylesheet, replace them with the closest existing variables used by adjacent `.content-*` rules.

- [ ] **Step 2: Build frontend**

Run:

```bash
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add api/webui/src/styles.css
git commit -m "style: add realtime content search progress"
```

---

### Task 5: Verification

**Files:**
- No code files expected.

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
pytest tests/test_content_tracking_api.py tests/test_tikhub_endpoints.py tests/test_tikhub_client.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 3: Start local dev server**

Run:

```bash
npm.cmd run dev
```

Expected: Vite starts and prints a local URL, usually `http://127.0.0.1:5173/`.

- [ ] **Step 4: Browser smoke check**

Open the research console in the in-app browser. Navigate to the content tracking page and verify:

- Checkbox is visible under the source preview.
- Checkbox is enabled for `all`, `xhs`, and `dy`.
- Checkbox is disabled or produces a clear message for `bili`, `wb`, and `zhihu`.
- With checkbox unchecked, the existing local search still works.
- With checkbox checked, the search button says `实时搜索并入库`.
- During search, the progress bar and stage text are visible.
- On failure, old candidates remain visible and the error message is shown.

- [ ] **Step 5: Final status**

Run:

```bash
git status --short
```

Expected: no unintended files changed. Existing unrelated dirty files may remain; do not stage or revert them.
