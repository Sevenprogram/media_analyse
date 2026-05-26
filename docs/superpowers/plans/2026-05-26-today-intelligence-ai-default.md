# Today Intelligence AI Default Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make 今日情报 default to AI-generated analysis from real backend data, with rule-based facts, evidence references, UI AI status, and graceful fallback.

**Architecture:** Add a focused backend service that builds the existing dashboard summary, database stats, rule candidates, and compact AI input, then calls the existing OpenAI-compatible gateway from `AI_GATEWAY_*`. Add `/api/reports/today-intelligence` and `/api/reports/today-intelligence/run`, persist the latest result in `research_global_settings`, and update the React page to render AI status and AI-authored explanations while keeping rule metrics authoritative.

**Tech Stack:** FastAPI, async Python, existing `ResearchRepository`, existing `OpenAICompatibleProvider`, React 19, TypeScript, Vite, lucide-react.

---

## File Structure

- Create `research/today_intelligence.py`: one service module for building the real data bundle, rule fallback, AI prompt, AI output normalization, persistence payload, and stale checks.
- Modify `api/routers/reports.py`: add request schema and two endpoints, and reuse the service.
- Modify `api/webui/src/types.ts`: add `TodayIntelligenceSummary` and related UI types.
- Modify `api/webui/src/main.tsx`: load today intelligence by default for the `today` tab, store it in React state, pass it into `TodayIntelligencePage`, and call the regenerate endpoint from refresh.
- Modify `api/webui/src/pages/GrowthIntelligencePages.tsx`: remove normal-path mock injection, render AI status, AI summary, AI explanations, and rule fallback states.
- Modify `api/webui/src/styles.css`: add compact AI status and summary styles consistent with the existing operational dashboard.
- Add `tests/test_today_intelligence_ai.py`: test AI success, fallback on provider failure, latest result persistence, and API shape.

## Task 1: Backend Service

**Files:**
- Create: `research/today_intelligence.py`
- Test: `tests/test_today_intelligence_ai.py`

- [ ] **Step 1: Write service unit tests**

Create tests that call the service directly with a fake repository and fake provider. Assert:

```python
async def test_run_today_intelligence_uses_ai_provider_and_persists():
    result = await run_today_intelligence_analysis(fake_repo, provider_factory=stub_provider)
    assert result["status"] == "completed"
    assert result["source"] == "ai"
    assert result["executive_summary"] == "AI 今日情报已生成。"
    assert fake_repo.saved_setting["value"]["provider"]["model"] == "gpt-5.4-mini"
```

```python
async def test_run_today_intelligence_falls_back_when_ai_fails():
    result = await run_today_intelligence_analysis(fake_repo, provider_factory=failing_provider)
    assert result["status"] == "fallback"
    assert result["source"] == "rules"
    assert result["error"]
    assert result["actions"]
```

- [ ] **Step 2: Implement `research/today_intelligence.py`**

Implement these public functions:

```python
TODAY_INTELLIGENCE_SETTING_KEY = "reports:today-intelligence:latest"

async def get_latest_today_intelligence(repository, *, max_age_minutes: int = 120) -> dict[str, Any] | None: ...
async def run_today_intelligence_analysis(repository, *, platform: str | None = None, force: bool = False, provider_factory=None) -> dict[str, Any]: ...
def build_today_intelligence_prompt(input_summary: dict[str, Any]) -> str: ...
def build_rule_based_today_intelligence_fallback(input_summary: dict[str, Any], *, reason: str) -> dict[str, Any]: ...
```

Use `repository.upsert_global_setting()` for persistence and `repository.get_database_collection_stats()` for stats.

- [ ] **Step 3: Run backend service tests**

Run:

```powershell
uv run pytest tests/test_today_intelligence_ai.py -q
```

Expected: PASS.

## Task 2: API Endpoints

**Files:**
- Modify: `api/routers/reports.py`
- Test: `tests/test_today_intelligence_ai.py`

- [ ] **Step 1: Add endpoint tests**

Add API tests using `ASGITransport`:

```python
response = await client.get("/api/reports/today-intelligence")
assert response.status_code == 200
payload = response.json()
assert payload["dashboard"]
assert payload["ai_status"]["status"] in {"completed", "fallback", "missing"}
```

```python
response = await client.post("/api/reports/today-intelligence/run", json={"force": True})
assert response.status_code == 200
assert response.json()["generated_at"]
```

- [ ] **Step 2: Implement API routes**

Add:

```python
class TodayIntelligenceRunRequest(BaseModel):
    force: bool = False
    platform: str | None = None

@router.get("/today-intelligence")
async def get_today_intelligence(platform: str | None = None, max_age_minutes: int = 120): ...

@router.post("/today-intelligence/run")
async def run_today_intelligence(request: TodayIntelligenceRunRequest): ...
```

`GET` returns latest persisted AI result when fresh, otherwise runs a default analysis. `POST` always runs analysis when `force=True`.

- [ ] **Step 3: Run API tests**

Run:

```powershell
uv run pytest tests/test_today_intelligence_ai.py -q
```

Expected: PASS.

## Task 3: Frontend Data Flow

**Files:**
- Modify: `api/webui/src/types.ts`
- Modify: `api/webui/src/main.tsx`

- [ ] **Step 1: Add TypeScript types**

Add `TodayIntelligenceSummary` with:

```ts
export type TodayIntelligenceSummary = {
  status: "completed" | "fallback" | "running" | "missing" | "stale" | "error";
  source: "ai" | "rules" | "none";
  generated_at?: string | null;
  expires_at?: string | null;
  error?: string | null;
  provider?: { name?: string | null; model?: string | null } | null;
  executive_summary?: string;
  actions?: Array<Record<string, unknown>>;
  opportunity_explanations?: Array<Record<string, unknown>>;
  risk_explanations?: Array<Record<string, unknown>>;
  sample_quality_explanation?: Record<string, unknown>;
  data_bias_notes?: string[];
  assumptions?: string[];
  dashboard: DashboardSummary;
  database_stats: DatabaseStats;
};
```

- [ ] **Step 2: Load today intelligence by default**

In `main.tsx`, create state:

```ts
const [todayIntelligence, setTodayIntelligence] = React.useState<TodayIntelligenceSummary | null>(null);
```

Change the today tab refresh to call `/api/reports/today-intelligence`, then set `dashboard`, `databaseStats`, and `todayIntelligence` from that response.

- [ ] **Step 3: Add regenerate handler**

Add:

```ts
const regenerateTodayIntelligence = React.useCallback(async () => {
  const data = await api<TodayIntelligenceSummary>("/api/reports/today-intelligence/run", {
    method: "POST",
    body: JSON.stringify({ force: true }),
  });
  setTodayIntelligence(data);
  setDashboard(data.dashboard);
  setDatabaseStats(data.database_stats);
}, []);
```

Pass it to `TodayIntelligencePage`.

## Task 4: Today Page UI

**Files:**
- Modify: `api/webui/src/pages/GrowthIntelligencePages.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Add props**

Extend `TodayIntelligencePageProps`:

```ts
todayIntelligence: TodayIntelligenceSummary | null;
onRegenerate: () => Promise<void>;
```

- [ ] **Step 2: Replace normal-path mock usage**

Use real rows first:

```ts
const blendedActions = React.useMemo(() => {
  const aiActions = normalizeAiActions(todayIntelligence?.actions || []);
  const realActions = actionRows(dashboard);
  return aiActions.length ? aiActions : normalizeDashboardActions(realActions);
}, [dashboard, todayIntelligence]);
```

Only show static examples when `databaseStats.total_collected === 0` and no dashboard actions exist, with an explicit empty-state label.

- [ ] **Step 3: Render AI status and summary**

Add an AI status pill beside the refresh controls and a compact summary strip under the page subtitle. Show provider model, generated time, fallback reason, and the executive summary.

- [ ] **Step 4: Attach AI explanations to opportunities and risks**

Map `opportunity_explanations` by `opportunity_id` and `risk_explanations` by `risk_id`. Prefer AI explanation text for card bodies, but keep rule score and sample metrics unchanged.

## Task 5: Verification

**Files:**
- Verify only; no new files.

- [ ] **Step 1: Run backend tests**

Run:

```powershell
uv run pytest tests/test_today_intelligence_ai.py -q
```

Expected: PASS.

- [ ] **Step 2: Run build**

Run:

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 3: Start dev server**

Run:

```powershell
npm.cmd run dev
```

Expected: Vite prints a local URL.

- [ ] **Step 4: Verify in browser**

Open the Vite URL and inspect 今日情报. Expected:

- AI status is visible.
- Executive summary is visible when AI succeeds or fallback summary appears when it fails.
- Normal business cards come from backend data, not `mockActions`.
- Console has no runtime errors.

## Self-Review

- Spec coverage: default AI, real data aggregation, Provider env usage, fallback, AI status UI, mock removal, evidence and sample constraints are covered by Tasks 1-4.
- Placeholder scan: no task uses TBD/TODO or unspecified implementation.
- Type consistency: `TodayIntelligenceSummary`, `dashboard`, and `database_stats` are used consistently across backend and frontend tasks.
