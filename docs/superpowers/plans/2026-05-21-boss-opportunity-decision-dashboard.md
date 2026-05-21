# Boss Opportunity Decision Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a boss/operations decision dashboard that ranks keyword, content, creator, and competitor opportunities with auditable scoring, risks, evidence, feedback, and decision-oriented charts.

**Architecture:** Extend the existing `/api/reports/dashboard-summary` path instead of creating a parallel dashboard. The backend owns scoring, risk tags, diagnostics, evidence shape, and feedback state; the frontend renders standardized fields, charts, confirmation flows, and current-board feedback behavior.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, existing `ResearchRepository`, React 19, TypeScript, Recharts, lucide-react.

---

## File Structure

- Modify `D:/program/media_analyse/MediaCrawler/research/dashboard.py`
  - Replace the current loose opportunity builders with standardized scoring, risk tagging, diagnostics, Top 5, watchlist, chart-support fields, and feedback application helpers.
- Modify `D:/program/media_analyse/MediaCrawler/api/routers/reports.py`
  - Keep `/api/reports/dashboard-summary`, add feedback submit route, and pass feedback records into `build_dashboard_summary`.
- Modify `D:/program/media_analyse/MediaCrawler/research/models.py`
  - Add `ResearchOpportunityFeedback` table.
- Modify `D:/program/media_analyse/MediaCrawler/research/repository.py`
  - Add feedback create/list methods and dict conversion.
- Modify `D:/program/media_analyse/MediaCrawler/research/setup_status.py`
  - Add feedback table to required research table list.
- Modify `D:/program/media_analyse/MediaCrawler/research/schema_migration.py`
  - Add safe migration for feedback table.
- Modify `D:/program/media_analyse/MediaCrawler/api/webui/src/main.tsx`
  - Update dashboard types, homepage layout, opportunity detail drawer, feedback controls, high-risk confirmations, and data browser chart section.
- Modify `D:/program/media_analyse/MediaCrawler/api/webui/src/styles.css`
  - Add styles for opportunity board, score bars, risk tags, chart grid, typed evidence samples, diagnostics, and feedback states.
- Modify tests:
  - `D:/program/media_analyse/MediaCrawler/tests/test_dashboard_summary.py`
  - `D:/program/media_analyse/MediaCrawler/tests/test_dashboard_api.py`
  - `D:/program/media_analyse/MediaCrawler/tests/test_research_models.py`
  - `D:/program/media_analyse/MediaCrawler/tests/test_research_schema_migration.py`

---

### Task 1: Backend Contract And Scoring Model

**Files:**
- Modify: `D:/program/media_analyse/MediaCrawler/research/dashboard.py`
- Test: `D:/program/media_analyse/MediaCrawler/tests/test_dashboard_summary.py`

- [ ] **Step 1: Add failing tests for the new dashboard response contract**

Add these tests to `tests/test_dashboard_summary.py`:

```python
def test_dashboard_summary_returns_standard_decision_contract():
    summary = build_dashboard_summary(
        jobs=[],
        creator_candidates=[],
        keyword_heat_snapshots=[
            {
                "keyword": "K12教育",
                "platform": "xhs",
                "heat_score": 90,
                "growth_score": 40,
                "platform_signal": "boosting",
                "sample_count": 128,
                "snapshot_date": "2026-05-21",
                "evidence": {"items": ["24h 讨论上升"]},
            }
        ],
        competitor_compositions=[],
        content_snapshots=[],
        monitor_pools=[],
        platform="xhs",
    )

    assert summary["scoring_profile"]["weights"] == {
        "heat_growth": 0.35,
        "sample_confidence": 0.25,
        "competition_gap": 0.2,
        "actionability": 0.2,
    }
    assert summary["scoring_profile"]["window"] == "7d_plus_24h"
    assert len(summary["top_opportunities"]) == 1
    opportunity = summary["top_opportunities"][0]
    assert opportunity["score_breakdown"].keys() == {
        "heat_growth",
        "sample_confidence",
        "competition_gap",
        "actionability",
    }
    assert opportunity["sample_scope"]["sample_count"] == 128
    assert "risk_tags" in opportunity
    assert "samples" in opportunity
    assert summary["opportunities"] == summary["top_opportunities"]
```

- [ ] **Step 2: Add failing tests for low-sample downranking and watchlist behavior**

Add:

```python
def test_low_sample_spike_goes_to_watchlist_not_first():
    summary = build_dashboard_summary(
        jobs=[],
        creator_candidates=[],
        keyword_heat_snapshots=[
            {
                "keyword": "小样本暴涨",
                "platform": "xhs",
                "heat_score": 99,
                "growth_score": 95,
                "sample_count": 5,
                "snapshot_date": "2026-05-21",
                "evidence": {"items": ["少量样本暴涨"]},
            },
            {
                "keyword": "稳定机会",
                "platform": "xhs",
                "heat_score": 82,
                "growth_score": 30,
                "sample_count": 150,
                "snapshot_date": "2026-05-21",
                "evidence": {"items": ["多平台稳定增长"]},
            },
        ],
        competitor_compositions=[],
        content_snapshots=[],
        monitor_pools=[],
        platform="xhs",
    )

    assert summary["top_opportunities"][0]["name"] == "稳定机会"
    watch_names = [item["name"] for item in summary["watchlist"]]
    assert "小样本暴涨" in watch_names
    spike = next(item for item in summary["watchlist"] if item["name"] == "小样本暴涨")
    assert "small_sample_spike" in spike["risk_tags"]
```

- [ ] **Step 3: Implement constants and standardized opportunity helpers**

In `research/dashboard.py`, add:

```python
SCORING_WEIGHTS = {
    "heat_growth": 0.35,
    "sample_confidence": 0.25,
    "competition_gap": 0.2,
    "actionability": 0.2,
}

RISK_SMALL_SAMPLE_SPIKE = "small_sample_spike"
RISK_SINGLE_PLATFORM_SIGNAL = "single_platform_signal"
RISK_STALE_DATA = "stale_data"
RISK_OVERHEATED_COMPETITION = "overheated_competition"
RISK_MISSING_EXECUTION_PARAMETERS = "missing_execution_parameters"
RISK_HIGH_COST = "high_cost"

def _weighted_score(breakdown: dict[str, float]) -> float:
    return round(
        breakdown["heat_growth"] * SCORING_WEIGHTS["heat_growth"]
        + breakdown["sample_confidence"] * SCORING_WEIGHTS["sample_confidence"]
        + breakdown["competition_gap"] * SCORING_WEIGHTS["competition_gap"]
        + breakdown["actionability"] * SCORING_WEIGHTS["actionability"],
        2,
    )

def _sample_confidence_score(sample_count: int, platforms: list[str], stale: bool) -> float:
    if stale:
        return 30.0
    if sample_count >= 100 and len(set(platforms)) >= 2:
        return 95.0
    if sample_count >= 100:
        return 80.0
    if sample_count >= 30:
        return 65.0
    if sample_count >= 10:
        return 40.0
    return 20.0
```

- [ ] **Step 4: Replace each `_creator_opportunity`, `_keyword_opportunity`, `_competitor_opportunity`, and `_content_opportunity` output shape**

Each builder must return this shape:

```python
{
    "id": "keyword:xhs:K12教育",
    "type": "keyword",
    "name": "K12教育",
    "platform": "xhs",
    "score": 82.0,
    "score_breakdown": {
        "heat_growth": 86.0,
        "sample_confidence": 72.0,
        "competition_gap": 80.0,
        "actionability": 88.0,
    },
    "risk_tags": [],
    "evidence_summary": ["平台信号：boosting。"],
    "sample_scope": {
        "window": "7d",
        "platforms": ["xhs"],
        "sample_count": 128,
        "last_updated_at": "2026-05-21",
    },
    "trend": {
        "change_24h": 18.4,
        "points_7d": [],
        "points_14d": [],
        "points_30d": [],
    },
    "actions": [
        {"kind": "view_evidence", "label": "查看证据", "risk": "low", "payload": {}},
        {"kind": "prefill_collection_task", "label": "预填采集任务", "risk": "high", "payload": {"keyword": "K12教育", "platform": "xhs"}},
    ],
    "samples": [],
    "detail": {
        "summary": ["平台信号：boosting。"],
        "trend_30d": [],
        "evidence": {},
    },
}
```

Keep `detail`, `change_24h`, `trend_7d`, `confidence`, `reason`, `evidence_count`, and `payload` as compatibility fields until the frontend is fully migrated.

- [ ] **Step 5: Implement Top 5 and watchlist split**

Change `build_dashboard_summary` to return:

```python
return {
    "decision": decision,
    "actions": _build_actions(opportunities=top_opportunities, decision=decision),
    "monitoring": monitoring,
    "opportunities": top_opportunities,
    "top_opportunities": top_opportunities,
    "watchlist": watchlist,
    "diagnostics": diagnostics,
    "scoring_profile": {"weights": SCORING_WEIGHTS, "window": "7d_plus_24h"},
}
```

Rules:

- Very low confidence sample count under 10 goes to watchlist.
- Low-sample spike cannot be first in `top_opportunities`.
- `top_opportunities` length is at most 5.
- `watchlist` length is at most 3.

- [ ] **Step 6: Run backend contract tests**

Run:

```powershell
pytest tests/test_dashboard_summary.py -q
```

Expected: all dashboard summary tests pass.

---

### Task 2: Diagnostics And Feedback Persistence

**Files:**
- Modify: `D:/program/media_analyse/MediaCrawler/research/models.py`
- Modify: `D:/program/media_analyse/MediaCrawler/research/repository.py`
- Modify: `D:/program/media_analyse/MediaCrawler/research/setup_status.py`
- Modify: `D:/program/media_analyse/MediaCrawler/research/schema_migration.py`
- Modify: `D:/program/media_analyse/MediaCrawler/research/dashboard.py`
- Test: `D:/program/media_analyse/MediaCrawler/tests/test_research_models.py`
- Test: `D:/program/media_analyse/MediaCrawler/tests/test_research_schema_migration.py`
- Test: `D:/program/media_analyse/MediaCrawler/tests/test_dashboard_summary.py`

- [ ] **Step 1: Add model test for feedback table**

Add to `tests/test_research_models.py`:

```python
def test_research_opportunity_feedback_model_columns():
    from research.models import ResearchOpportunityFeedback

    columns = set(ResearchOpportunityFeedback.__table__.columns.keys())
    assert {
        "id",
        "opportunity_id",
        "feedback",
        "note",
        "opportunity_type",
        "opportunity_name",
        "payload_json",
        "created_at",
    }.issubset(columns)
```

- [ ] **Step 2: Add SQLAlchemy model**

In `research/models.py`, add near the other research dashboard tables:

```python
class ResearchOpportunityFeedback(Base):
    __tablename__ = "research_opportunity_feedback"

    id = Column(Integer, primary_key=True)
    opportunity_id = Column(String(255), nullable=False, index=True)
    opportunity_type = Column(String(32), nullable=True, index=True)
    opportunity_name = Column(Text, nullable=True)
    feedback = Column(String(32), nullable=False, index=True)
    note = Column(Text, nullable=True)
    payload_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
```

- [ ] **Step 3: Add schema migration test and table registration**

Add to `tests/test_research_schema_migration.py`:

```python
def test_missing_research_feedback_table_is_required():
    from research.setup_status import REQUIRED_RESEARCH_TABLES

    assert "research_opportunity_feedback" in REQUIRED_RESEARCH_TABLES
```

Add `"research_opportunity_feedback"` to `REQUIRED_RESEARCH_TABLES` in `research/setup_status.py`.

In `research/schema_migration.py`, add the table creation statement to the existing table migration mechanism using the same dialect-safe pattern used for other research tables.

- [ ] **Step 4: Add repository methods**

In `research/repository.py`, add:

```python
async def create_opportunity_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
    async with self.session_factory() as session:
        item = ResearchOpportunityFeedback(
            opportunity_id=payload["opportunity_id"],
            opportunity_type=payload.get("opportunity_type"),
            opportunity_name=payload.get("opportunity_name"),
            feedback=payload["feedback"],
            note=payload.get("note"),
            payload_json=payload.get("payload") or {},
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return self._opportunity_feedback_to_dict(item)

async def list_opportunity_feedback(self, limit: int = 500) -> list[dict[str, Any]]:
    async with self.session_factory() as session:
        stmt = (
            select(ResearchOpportunityFeedback)
            .order_by(ResearchOpportunityFeedback.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [self._opportunity_feedback_to_dict(item) for item in result.scalars().all()]

def _opportunity_feedback_to_dict(self, item: ResearchOpportunityFeedback) -> dict[str, Any]:
    return {
        "id": item.id,
        "opportunity_id": item.opportunity_id,
        "opportunity_type": item.opportunity_type,
        "opportunity_name": item.opportunity_name,
        "feedback": item.feedback,
        "note": item.note,
        "payload": item.payload_json or {},
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }
```

Import `ResearchOpportunityFeedback` where repository imports models.

- [ ] **Step 5: Add feedback application tests**

Add to `tests/test_dashboard_summary.py`:

```python
def test_feedback_moves_false_positive_out_of_top_opportunities():
    summary = build_dashboard_summary(
        jobs=[],
        creator_candidates=[],
        keyword_heat_snapshots=[
            {"keyword": "误判", "platform": "xhs", "heat_score": 95, "growth_score": 45, "sample_count": 130, "evidence": {"items": ["x"]}},
            {"keyword": "保留", "platform": "xhs", "heat_score": 80, "growth_score": 30, "sample_count": 130, "evidence": {"items": ["y"]}},
        ],
        competitor_compositions=[],
        content_snapshots=[],
        monitor_pools=[],
        platform="xhs",
        feedback=[
            {"opportunity_id": "keyword:xhs:误判", "feedback": "false_positive"},
        ],
    )

    assert all(item["name"] != "误判" for item in summary["top_opportunities"])
    assert any(item["name"] == "误判" for item in summary["ignored_opportunities"])
```

- [ ] **Step 6: Update `build_dashboard_summary` signature**

Change:

```python
def build_dashboard_summary(..., platform: str | None) -> dict[str, Any]:
```

to:

```python
def build_dashboard_summary(..., platform: str | None, feedback: list[dict[str, Any]] | None = None) -> dict[str, Any]:
```

Apply feedback:

- `false_positive`: remove from Top 5 and place in `ignored_opportunities`.
- `watch`: place in watchlist.
- `valid`: keep in ranking and add `feedback_state: "valid"`.

- [ ] **Step 7: Run persistence and dashboard tests**

Run:

```powershell
pytest tests/test_research_models.py tests/test_research_schema_migration.py tests/test_dashboard_summary.py -q
```

Expected: all selected tests pass.

---

### Task 3: Dashboard API Feedback Route

**Files:**
- Modify: `D:/program/media_analyse/MediaCrawler/api/routers/reports.py`
- Test: `D:/program/media_analyse/MediaCrawler/tests/test_dashboard_api.py`

- [ ] **Step 1: Add API tests**

Add to `tests/test_dashboard_api.py`:

```python
def test_dashboard_summary_includes_top_opportunities_watchlist_and_profile(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_jobs(self):
            return []
        async def list_creator_candidates(self, vertical_id=None, platform=None, pool_name=None):
            return []
        async def list_keyword_heat_snapshots(self, vertical_id=None, scene_pack_id=None, platform=None, limit=None):
            return [{"keyword": "K12教育", "platform": "xhs", "heat_score": 85, "growth_score": 20, "sample_count": 100, "evidence": {"items": ["增长"]}}]
        async def list_competitor_composition_snapshots(self, competitor_id=None, platform=None, limit=None):
            return []
        async def list_content_tracking_snapshots(self, tracker_id=None, platform=None, limit=None):
            return []
        async def list_monitor_pools(self, enabled_only=False):
            return []
        async def list_opportunity_feedback(self, limit=500):
            return []

    import api.routers.reports as reports_router
    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/reports/dashboard-summary?platform=xhs")

    assert response.status_code == 200
    body = response.json()
    assert body["top_opportunities"]
    assert "watchlist" in body
    assert body["scoring_profile"]["window"] == "7d_plus_24h"
```

Add:

```python
def test_opportunity_feedback_api_records_feedback(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def create_opportunity_feedback(self, payload):
            return {"id": 1, **payload, "created_at": "2026-05-21T00:00:00Z"}

    import api.routers.reports as reports_router
    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/reports/opportunity-feedback",
        json={"opportunity_id": "keyword:xhs:K12教育", "feedback": "watch", "note": "needs more samples"},
    )

    assert response.status_code == 200
    assert response.json()["feedback"]["feedback"] == "watch"
```

- [ ] **Step 2: Add request schema**

In `api/routers/reports.py`, add:

```python
class OpportunityFeedbackRequest(BaseModel):
    opportunity_id: str = Field(min_length=1, max_length=255)
    feedback: str = Field(pattern="^(valid|false_positive|watch)$")
    note: str | None = Field(default=None, max_length=1000)
    opportunity_type: str | None = Field(default=None, max_length=32)
    opportunity_name: str | None = Field(default=None, max_length=500)
    payload: dict = Field(default_factory=dict)
```

- [ ] **Step 3: Load feedback in summary endpoint**

In `get_dashboard_summary`, load:

```python
feedback = await _maybe_call(repository, "list_opportunity_feedback", limit=500, default=[])
```

Pass `feedback=feedback` into `build_dashboard_summary`.

- [ ] **Step 4: Add feedback endpoint**

Add:

```python
@router.post("/opportunity-feedback")
async def create_opportunity_feedback(request: OpportunityFeedbackRequest):
    require_research_database()
    repository = ResearchRepository()
    feedback = await repository.create_opportunity_feedback(request.model_dump())
    return {"feedback": feedback}
```

- [ ] **Step 5: Run API tests**

Run:

```powershell
pytest tests/test_dashboard_api.py -q
```

Expected: all dashboard API tests pass.

---

### Task 4: Frontend Types And Dashboard Data Model

**Files:**
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/src/main.tsx`

- [ ] **Step 1: Update TypeScript types**

Replace `DashboardOpportunity` and `DashboardSummary` with fields matching the backend contract while keeping compatibility fields optional:

```typescript
type OpportunityRiskTag =
  | "small_sample_spike"
  | "single_platform_signal"
  | "stale_data"
  | "overheated_competition"
  | "missing_execution_parameters"
  | "high_cost";

type OpportunityAction = {
  kind: string;
  label: string;
  risk: "low" | "high";
  payload: Record<string, unknown>;
};

type OpportunitySample = {
  type: "post" | "comment" | "content" | "creator" | "competitor";
  title?: string;
  body?: string;
  platform?: string | null;
  url?: string | null;
  publish_time?: string | null;
  engagement?: Record<string, unknown>;
  matched_terms?: string[];
  raw_ref?: Record<string, unknown>;
};

type DashboardOpportunity = {
  id: string;
  type: "creator" | "keyword" | "competitor" | "content";
  name: string;
  platform?: string | null;
  score: number;
  score_breakdown: {
    heat_growth: number;
    sample_confidence: number;
    competition_gap: number;
    actionability: number;
  };
  risk_tags: OpportunityRiskTag[];
  evidence_summary: string[];
  sample_scope: {
    window: string;
    platforms: string[];
    sample_count: number;
    last_updated_at?: string | null;
  };
  trend: {
    change_24h: number;
    points_7d: Array<Record<string, unknown>>;
    points_14d: Array<Record<string, unknown>>;
    points_30d: Array<Record<string, unknown>>;
  };
  actions: OpportunityAction[];
  samples: OpportunitySample[];
  feedback_state?: "valid" | "false_positive" | "watch" | null;
  change_24h?: number;
  trend_7d?: number;
  confidence?: DashboardConfidence;
  reason?: string;
  evidence_count?: number;
  payload?: Record<string, unknown>;
  detail?: { summary: string[]; trend_30d: Array<Record<string, unknown>>; evidence: unknown };
};

type DashboardSummary = {
  decision: { headline: string; confidence: DashboardConfidence; sample_status: DashboardSampleStatus; sample_summary: string; risk_notes: string[]; evidence_count: number };
  actions: { do_now: DashboardAction[]; watch_today: DashboardAction[]; defer: DashboardAction[] };
  monitoring: { running_jobs: number; today_collected: number; errors: number; monitor_pools: number; realtime_jobs: number; last_updated_at?: string | null };
  opportunities: DashboardOpportunity[];
  top_opportunities: DashboardOpportunity[];
  watchlist: DashboardOpportunity[];
  ignored_opportunities?: DashboardOpportunity[];
  diagnostics: Array<{ code: string; title: string; body: string; action?: string }>;
  scoring_profile: { weights: Record<string, number>; window: string };
};
```

- [ ] **Step 2: Add label helpers**

Add:

```typescript
const RISK_LABELS: Record<OpportunityRiskTag, string> = {
  small_sample_spike: "小样本突增",
  single_platform_signal: "平台单一",
  stale_data: "数据过旧",
  overheated_competition: "竞争过热",
  missing_execution_parameters: "执行参数缺失",
  high_cost: "成本较高",
};

const scoreParts = [
  ["heat_growth", "热度增长"],
  ["sample_confidence", "样本可信度"],
  ["competition_gap", "竞争空档"],
  ["actionability", "可执行性"],
] as const;
```

- [ ] **Step 3: Update fallback dashboard**

In `BossDashboardOverviewPage`, update `fallbackDashboard` to include:

```typescript
top_opportunities: [],
watchlist: [],
ignored_opportunities: [],
diagnostics: [{ code: "no_data", title: "暂无机会判断", body: "先采集样本后再生成机会榜。" }],
scoring_profile: { weights: { heat_growth: 0.35, sample_confidence: 0.25, competition_gap: 0.2, actionability: 0.2 }, window: "7d_plus_24h" },
```

- [ ] **Step 4: Run frontend type check through build**

Run:

```powershell
npm.cmd run build
```

Expected: TypeScript passes. This task must not introduce unresolved UI references before the chart components are added.

---

### Task 5: Frontend Boss Dashboard And Charts

**Files:**
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/src/main.tsx`
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/src/styles.css`

- [ ] **Step 1: Replace opportunity board layout**

In `BossDashboardOverviewPage`, render:

```tsx
const topOpportunities = model.top_opportunities?.length ? model.top_opportunities : model.opportunities || [];
const selected = selectedOpportunity || topOpportunities[0] || model.watchlist?.[0] || null;

return (
  <section className="growth-workspace">
    <div className="boss-dashboard-grid wide-main">
      <OpportunityDecisionBoard top={topOpportunities} watchlist={model.watchlist || []} selectedId={selected?.id || null} onSelect={onViewOpportunity} />
      <OpportunityExplanationPanel opportunity={selected} onExecute={onRequestExecution} />
    </div>
    <OpportunityAnalyticsSection opportunities={topOpportunities} watchlist={model.watchlist || []} />
    <DiagnosticPanel diagnostics={model.diagnostics || []} />
  </section>
);
```

Keep `DecisionSummaryPanel` and `MonitoringCards` if useful, but move them below the first decision grid if they crowd the first screen.

- [ ] **Step 2: Implement `OpportunityDecisionBoard`**

It renders:

- Top 5 opportunity cards.
- Watchlist cards.
- Score, type label, 7d/24h values, risk chips, and sample count.

Use this structure:

```tsx
function OpportunityDecisionBoard({ top, watchlist, selectedId, onSelect }: { top: DashboardOpportunity[]; watchlist: DashboardOpportunity[]; selectedId: string | null; onSelect: (item: DashboardOpportunity) => void }) {
  return <section className="panel opportunity-decision-board">...</section>;
}
```

- [ ] **Step 3: Implement chart components**

Add these local components in `main.tsx`:

- `OpportunityScoreBars`
- `OpportunityTrendChart`
- `PlatformSignalChart`
- `OpportunityMatrixChart`
- `RiskDistributionChart`
- `CompetitionGapRanking`

Use Recharts components already imported. For scatter/bubble matrix, add `ScatterChart`, `Scatter`, and `ZAxis` to the import list.

- [ ] **Step 4: Implement `OpportunityExplanationPanel`**

Panel includes:

- Score bars.
- 7d trend chart with 24h badge.
- Platform signal chart.
- Risk tag strip.
- Evidence summary.
- Primary buttons: view evidence, execute/prefill action.

High-risk action buttons should call the existing `onRequestExecution` confirmation path instead of direct execution.

- [ ] **Step 5: Implement `OpportunityAnalyticsSection`**

Render:

- Opportunity matrix.
- Risk distribution.
- Competition gap ranking.
- Opportunity type distribution using bar chart or pie chart only if categories are fewer than 5.

- [ ] **Step 6: Add styles**

In `styles.css`, add:

```css
.opportunity-decision-board,
.opportunity-explanation,
.opportunity-analytics {
  min-width: 0;
}

.opportunity-card {
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  background: var(--panel-soft);
  padding: 12px;
  display: grid;
  gap: 8px;
}

.opportunity-card.active {
  border-color: var(--accent);
  box-shadow: inset 3px 0 0 var(--accent);
}

.risk-strip,
.score-bars {
  display: grid;
  gap: 8px;
}

.risk-chip {
  display: inline-flex;
  border-radius: 999px;
  padding: 4px 8px;
  background: var(--warning-soft);
  color: #9a5a00;
  font-size: 12px;
  font-weight: 700;
}
```

- [ ] **Step 7: Run frontend build**

Run:

```powershell
npm.cmd run build
```

Expected: build succeeds.

---

### Task 6: Opportunity Detail Drawer, Evidence Samples, And Feedback

**Files:**
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/src/main.tsx`
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/src/styles.css`

- [ ] **Step 1: Add feedback API helper**

In `App`, add:

```typescript
async function submitOpportunityFeedback(opportunity: DashboardOpportunity, feedback: "valid" | "false_positive" | "watch", note = "") {
  await api<{ feedback: Record<string, unknown> }>("/api/reports/opportunity-feedback", {
    method: "POST",
    body: JSON.stringify({
      opportunity_id: opportunity.id,
      opportunity_type: opportunity.type,
      opportunity_name: opportunity.name,
      feedback,
      note,
      payload: { score: opportunity.score, risk_tags: opportunity.risk_tags },
    }),
  });
  await loadDashboardSummary();
}
```

Pass it into `OpportunityDetailDrawer`.

- [ ] **Step 2: Replace existing detail drawer body**

The drawer should show:

- Score breakdown chart.
- Sample scope.
- Risk tags.
- Trend chart.
- Platform contribution chart.
- Evidence sample list, maximum 10.
- Feedback buttons.
- Existing execute button.

- [ ] **Step 3: Implement `EvidenceSamplePanel`**

Use typed rendering:

```tsx
function EvidenceSamplePanel({ samples }: { samples: OpportunitySample[] }) {
  const visible = samples.slice(0, 10);
  return <div className="evidence-samples">{visible.map((sample, index) => <EvidenceSampleCard key={index} sample={sample} />)}</div>;
}
```

Each sample card displays platform, title/body, publish time, engagement summary, matched terms, and link if present.

- [ ] **Step 4: Add feedback behavior in UI**

Add buttons:

- `有效`
- `误判`
- `先观察`

On click, call `submitOpportunityFeedback`. After success:

- Close drawer for false positive and watch.
- Keep drawer open for valid and show active state.

- [ ] **Step 5: Add styles**

Add:

```css
.evidence-samples {
  display: grid;
  gap: 10px;
}

.evidence-sample {
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  padding: 11px;
  background: var(--panel-soft);
}

.feedback-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
```

- [ ] **Step 6: Build**

Run:

```powershell
npm.cmd run build
```

Expected: build succeeds.

---

### Task 7: Data Browser Decision Charts

**Files:**
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/src/main.tsx`
- Modify: `D:/program/media_analyse/MediaCrawler/api/webui/src/styles.css`

- [ ] **Step 1: Add data-browser chart helpers**

Add local helpers:

```typescript
function platformRows(posts: PostRecord[], comments: CommentRecord[]) {
  const counts = new Map<string, { platform: string; posts: number; comments: number }>();
  for (const post of posts) {
    const row = counts.get(post.platform) || { platform: post.platform, posts: 0, comments: 0 };
    row.posts += 1;
    counts.set(post.platform, row);
  }
  for (const comment of comments) {
    const row = counts.get(comment.platform) || { platform: comment.platform, posts: 0, comments: 0 };
    row.comments += 1;
    counts.set(comment.platform, row);
  }
  return [...counts.values()];
}
```

Add `buildPublishDateRows` for publish date buckets and `buildKeywordHitRows` for keyword hits using `title`, `content`, and `engagement_json.source_keyword`.

- [ ] **Step 2: Add `DataBrowserInsights` above the table**

Render:

- Sample count.
- Time range.
- Platform comparison.
- Publish time distribution.
- Keyword hit ranking.
- Data quality mini panel.

- [ ] **Step 3: Replace raw JSON-heavy table cells where possible**

For post engagement and AI results, show a compact summary first:

- likes/comments/shares where present.
- AI result key-value preview.
- keep full JSON available in `pre` only in detail area or truncated preview.

- [ ] **Step 4: Build**

Run:

```powershell
npm.cmd run build
```

Expected: build succeeds.

---

### Task 8: Full Verification

**Files:**
- All files touched above.

- [ ] **Step 1: Run focused backend tests**

Run:

```powershell
pytest tests/test_dashboard_summary.py tests/test_dashboard_api.py tests/test_research_models.py tests/test_research_schema_migration.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run frontend build**

Run:

```powershell
npm.cmd run build
```

Expected: TypeScript and Vite build pass. Vite chunk-size warning is acceptable.

- [ ] **Step 3: Browser smoke test**

Run preview:

```powershell
npm.cmd run preview -- --host 127.0.0.1 --port 4177
```

Open:

```text
http://127.0.0.1:4177/static/dist/
```

Verify:

- Homepage shows diagnostic empty state when backend or samples are missing.
- With mocked or real dashboard data, Top 5 and watchlist render.
- Selecting an opportunity updates score bars and charts.
- Detail drawer opens and shows samples.
- Feedback buttons call `/api/reports/opportunity-feedback`.
- High-risk action opens confirmation instead of direct execution.
- Data browser charts render without overlapping the table.

- [ ] **Step 4: Review diff scope**

Run:

```powershell
git diff -- research/dashboard.py api/routers/reports.py research/models.py research/repository.py research/setup_status.py research/schema_migration.py api/webui/src/main.tsx api/webui/src/styles.css tests/test_dashboard_summary.py tests/test_dashboard_api.py tests/test_research_models.py tests/test_research_schema_migration.py
```

Expected: changes are limited to decision model, feedback persistence, dashboard API, and dashboard/data-browser frontend.
