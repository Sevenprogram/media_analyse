# Lead Attribution V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first production-usable lead attribution pipeline that connects existing research content data with imported lead and conversion events, then powers the `线索归因` page with real summary and breakdown APIs.

**Architecture:** Reuse the existing `research` domain as the source-of-truth for projects, posts, raw evidence, and reports. Add a minimal attribution bridge layer inside `research` for leads, touchpoints, conversion events, attribution results, and daily snapshots; expose import and report endpoints through existing `research` and `reports` routers; then wire the existing frontend page to those APIs.

**Tech Stack:** FastAPI, SQLAlchemy ORM, existing `research` repository/service pattern, React + TypeScript WebUI, pytest.

---

## File Structure

**Existing files to modify**

- `D:\program\media_analyse_api_only\research\models.py`
  Add lead attribution domain tables under the existing `research_` namespace.
- `D:\program\media_analyse_api_only\research\repository.py`
  Add persistence and query methods for leads, touchpoints, conversion events, attribution configs, attribution results, and snapshots.
- `D:\program\media_analyse_api_only\research\schemas.py`
  Add request/response models for imports, config updates, and read payloads.
- `D:\program\media_analyse_api_only\api\routers\research.py`
  Add import/config/detail endpoints under `/research/growth-projects/...`.
- `D:\program\media_analyse_api_only\api\routers\reports.py`
  Add summary/breakdown endpoints under `/reports/lead-attribution/...`.
- `D:\program\media_analyse_api_only\api\webui\src\types.ts`
  Add frontend types for attribution summary, rows, lead detail, and config.
- `D:\program\media_analyse_api_only\api\webui\src\main.tsx`
  Add API loaders for attribution data.
- `D:\program\media_analyse_api_only\api\webui\src\pages\LeadAttributionPage.tsx`
  Replace mock data with real API-backed rendering and empty/error states.

**New files to create**

- `D:\program\media_analyse_api_only\research\lead_attribution.py`
  Domain logic for attribution config defaults, event matching, first-touch/last-touch/linear calculation, and daily snapshot assembly.
- `D:\program\media_analyse_api_only\tests\test_lead_attribution_api.py`
  API coverage for import/config/report endpoints.
- `D:\program\media_analyse_api_only\tests\test_lead_attribution_domain.py`
  Domain coverage for attribution calculation rules.

**Files to inspect during implementation**

- `D:\program\media_analyse_api_only\research\service.py`
- `D:\program\media_analyse_api_only\research\growth_projects.py`
- `D:\program\media_analyse_api_only\api\main.py`
- `D:\program\media_analyse_api_only\tests\test_content_tracking_api.py`

---

### Task 1: Add Lead Attribution Storage Model

**Files:**
- Modify: `D:\program\media_analyse_api_only\research\models.py`
- Test: `D:\program\media_analyse_api_only\tests\test_lead_attribution_domain.py`

- [ ] **Step 1: Write the failing model test**

```python
from research import models


def test_lead_attribution_models_exist():
    assert hasattr(models, "ResearchLead")
    assert hasattr(models, "ResearchLeadTouchpoint")
    assert hasattr(models, "ResearchLeadConversionEvent")
    assert hasattr(models, "ResearchLeadAttributionResult")
    assert hasattr(models, "ResearchLeadAttributionDailySnapshot")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_lead_attribution_domain.py::test_lead_attribution_models_exist -v`

Expected: FAIL because the attribution models do not exist yet.

- [ ] **Step 3: Add minimal ORM tables**

```python
class ResearchLead(Base):
    __tablename__ = "research_leads"
    __table_args__ = (
        UniqueConstraint("project_id", "external_lead_id", name="uq_research_lead_external"),
    )

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("research_growth_projects.id"), nullable=False, index=True)
    external_lead_id = Column(String(255), nullable=True, index=True)
    lead_status = Column(String(32), nullable=False, default="new", index=True)
    lead_score = Column(Float, nullable=True)
    owner = Column(String(128), nullable=True, index=True)
    name_masked = Column(String(255), nullable=True)
    phone_hash = Column(String(128), nullable=True, index=True)
    wechat_hash = Column(String(128), nullable=True, index=True)
    source_platform = Column(String(32), nullable=True, index=True)
    source_keyword = Column(String(255), nullable=True, index=True)
    first_touch_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_touch_at = Column(DateTime(timezone=True), nullable=True, index=True)
    meta_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
```

```python
class ResearchLeadTouchpoint(Base):
    __tablename__ = "research_lead_touchpoints"

    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("research_leads.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("research_growth_projects.id"), nullable=False, index=True)
    touch_type = Column(String(64), nullable=False, index=True)
    platform = Column(String(32), nullable=True, index=True)
    source_keyword = Column(String(255), nullable=True, index=True)
    creator_id = Column(String(255), nullable=True, index=True)
    post_id = Column(Integer, ForeignKey("research_posts.id"), nullable=True, index=True)
    raw_record_id = Column(Integer, ForeignKey("raw_records.id"), nullable=True, index=True)
    touch_time = Column(DateTime(timezone=True), nullable=False, index=True)
    session_key = Column(String(128), nullable=True, index=True)
    weight_hint = Column(Float, nullable=True)
    evidence_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

```python
class ResearchLeadConversionEvent(Base):
    __tablename__ = "research_lead_conversion_events"

    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("research_leads.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("research_growth_projects.id"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    event_value = Column(Float, nullable=True)
    event_count = Column(Integer, nullable=False, default=1)
    event_time = Column(DateTime(timezone=True), nullable=False, index=True)
    source_system = Column(String(64), nullable=False, default="manual", index=True)
    operator = Column(String(128), nullable=True)
    payload_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

```python
class ResearchLeadAttributionResult(Base):
    __tablename__ = "research_lead_attribution_results"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("research_growth_projects.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("research_leads.id"), nullable=False, index=True)
    conversion_event_id = Column(Integer, ForeignKey("research_lead_conversion_events.id"), nullable=False, index=True)
    model = Column(String(32), nullable=False, index=True)
    dimension = Column(String(32), nullable=False, index=True)
    dimension_key = Column(String(255), nullable=False, index=True)
    credit = Column(Float, nullable=False, default=0.0)
    window_days = Column(Integer, nullable=False, default=7)
    meta_json = Column(json_column(), nullable=False, default=dict)
    computed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
```

```python
class ResearchLeadAttributionDailySnapshot(Base):
    __tablename__ = "research_lead_attribution_daily_snapshots"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("research_growth_projects.id"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    model = Column(String(32), nullable=False, index=True)
    funnel_json = Column(json_column(), nullable=False, default=dict)
    platform_metrics_json = Column(json_column(), nullable=False, default=list)
    keyword_metrics_json = Column(json_column(), nullable=False, default=list)
    content_metrics_json = Column(json_column(), nullable=False, default=list)
    creator_metrics_json = Column(json_column(), nullable=False, default=list)
    summary_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_lead_attribution_domain.py::test_lead_attribution_models_exist -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add research/models.py tests/test_lead_attribution_domain.py
git commit -m "feat: add lead attribution storage models"
```

### Task 2: Add Domain Logic For Attribution Matching And Credit Allocation

**Files:**
- Create: `D:\program\media_analyse_api_only\research\lead_attribution.py`
- Test: `D:\program\media_analyse_api_only\tests\test_lead_attribution_domain.py`

- [ ] **Step 1: Write the failing domain tests**

```python
from datetime import datetime, timezone

from research.lead_attribution import compute_attribution_rows


def test_first_touch_assigns_full_credit_to_earliest_touch():
    rows = compute_attribution_rows(
        model="first_touch",
        conversion_event={"id": 7, "event_time": datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)},
        touchpoints=[
            {"id": 1, "platform": "xhs", "source_keyword": "猫粮", "post_id": 101, "touch_time": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)},
            {"id": 2, "platform": "dy", "source_keyword": "幼猫粮", "post_id": 102, "touch_time": datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)},
        ],
        window_days=7,
    )
    assert rows[0]["dimension"] == "platform"
    assert rows[0]["dimension_key"] == "xhs"
    assert rows[0]["credit"] == 1.0


def test_linear_assigns_split_credit():
    rows = compute_attribution_rows(
        model="linear",
        conversion_event={"id": 9, "event_time": datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)},
        touchpoints=[
            {"id": 1, "platform": "xhs", "source_keyword": "猫粮", "post_id": 101, "touch_time": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)},
            {"id": 2, "platform": "dy", "source_keyword": "幼猫粮", "post_id": 102, "touch_time": datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)},
        ],
        window_days=7,
    )
    assert sum(row["credit"] for row in rows if row["dimension"] == "platform") == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_lead_attribution_domain.py -v`

Expected: FAIL because `research.lead_attribution` does not exist.

- [ ] **Step 3: Write minimal attribution logic**

```python
from datetime import timedelta


SUPPORTED_MODELS = {"first_touch", "last_touch", "linear"}
SUPPORTED_DIMENSIONS = ("platform", "keyword", "content")


def normalize_attribution_config(config: dict | None) -> dict:
    config = dict(config or {})
    return {
        "default_model": config.get("default_model") or "last_touch",
        "window_days": int(config.get("window_days") or 7),
        "enabled_dimensions": config.get("enabled_dimensions") or ["platform", "keyword", "content"],
        "dedupe_by": config.get("dedupe_by") or "external_lead_id",
    }


def filter_touchpoints_for_window(conversion_event: dict, touchpoints: list[dict], window_days: int) -> list[dict]:
    event_time = conversion_event["event_time"]
    start_time = event_time - timedelta(days=window_days)
    return [
        item
        for item in sorted(touchpoints, key=lambda row: row["touch_time"])
        if start_time <= item["touch_time"] <= event_time
    ]


def compute_attribution_rows(model: str, conversion_event: dict, touchpoints: list[dict], window_days: int) -> list[dict]:
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported attribution model: {model}")
    scoped = filter_touchpoints_for_window(conversion_event, touchpoints, window_days)
    if not scoped:
        return []
    if model == "first_touch":
        scoped = [scoped[0]]
        credits = [1.0]
    elif model == "last_touch":
        scoped = [scoped[-1]]
        credits = [1.0]
    else:
        credits = [1 / len(scoped)] * len(scoped)

    rows = []
    for touchpoint, credit in zip(scoped, credits):
        if touchpoint.get("platform"):
            rows.append({"dimension": "platform", "dimension_key": touchpoint["platform"], "credit": credit})
        if touchpoint.get("source_keyword"):
            rows.append({"dimension": "keyword", "dimension_key": touchpoint["source_keyword"], "credit": credit})
        if touchpoint.get("post_id"):
            rows.append({"dimension": "content", "dimension_key": f"post:{touchpoint['post_id']}", "credit": credit})
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_lead_attribution_domain.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add research/lead_attribution.py tests/test_lead_attribution_domain.py
git commit -m "feat: add lead attribution domain logic"
```

### Task 3: Add Repository Support For Leads, Events, Attribution Results, And Snapshots

**Files:**
- Modify: `D:\program\media_analyse_api_only\research\repository.py`
- Test: `D:\program\media_analyse_api_only\tests\test_lead_attribution_api.py`

- [ ] **Step 1: Write the failing repository/API test**

```python
def test_repository_supports_lead_import_and_summary(client):
    response = client.post(
        "/api/research/growth-projects/pet-food-growth/leads/import",
        json={"source_system": "manual", "items": [{"external_lead_id": "L-1", "lead_status": "new"}]},
    )
    assert response.status_code == 200
    assert response.json()["created"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_lead_attribution_api.py::test_repository_supports_lead_import_and_summary -v`

Expected: FAIL with 404 because the import endpoint and repository methods do not exist.

- [ ] **Step 3: Add repository methods**

```python
async def create_lead(self, payload: dict[str, Any]) -> dict[str, Any]:
    async with get_session() as session:
        item = ResearchLead(**payload)
        session.add(item)
        await session.flush()
        await session.refresh(item)
        return self._lead_to_dict(item)


async def get_lead_by_external_id(self, project_id: int, external_lead_id: str) -> dict[str, Any] | None:
    async with get_session() as session:
        result = await session.execute(
            select(ResearchLead).where(
                ResearchLead.project_id == project_id,
                ResearchLead.external_lead_id == external_lead_id,
            )
        )
        item = result.scalar_one_or_none()
        return self._lead_to_dict(item) if item else None
```

```python
async def create_lead_touchpoint(self, payload: dict[str, Any]) -> dict[str, Any]:
    ...


async def create_lead_conversion_event(self, payload: dict[str, Any]) -> dict[str, Any]:
    ...


async def replace_lead_attribution_results(self, conversion_event_id: int, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ...


async def list_project_leads(self, project_id: int, **filters) -> list[dict[str, Any]]:
    ...


async def list_project_touchpoints(self, lead_id: int) -> list[dict[str, Any]]:
    ...


async def list_project_conversion_events(self, lead_id: int) -> list[dict[str, Any]]:
    ...
```

- [ ] **Step 4: Run test to verify repository-backed import now works**

Run: `pytest tests/test_lead_attribution_api.py::test_repository_supports_lead_import_and_summary -v`

Expected: still FAIL until router/schema work is added, but repository import helpers should be in place for the next task.

- [ ] **Step 5: Commit**

```bash
git add research/repository.py tests/test_lead_attribution_api.py
git commit -m "feat: add repository support for lead attribution entities"
```

### Task 4: Add Schemas And Research Import Endpoints

**Files:**
- Modify: `D:\program\media_analyse_api_only\research\schemas.py`
- Modify: `D:\program\media_analyse_api_only\api\routers\research.py`
- Test: `D:\program\media_analyse_api_only\tests\test_lead_attribution_api.py`

- [ ] **Step 1: Write failing API tests for imports and config**

```python
def test_update_attribution_config(client):
    response = client.put(
        "/api/research/growth-projects/pet-food-growth/attribution-config",
        json={"default_model": "last_touch", "window_days": 7, "enabled_dimensions": ["platform", "keyword", "content"]},
    )
    assert response.status_code == 200
    assert response.json()["config"]["default_model"] == "last_touch"
```

```python
def test_import_conversion_event(client):
    response = client.post(
        "/api/research/growth-projects/pet-food-growth/conversion-events/import",
        json={
            "source_system": "csv_import",
            "items": [{"external_lead_id": "L-1", "event_type": "deal_closed", "event_value": 399.0, "event_time": "2026-05-24T10:00:00+00:00"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["created"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_lead_attribution_api.py -v`

Expected: FAIL because the routes and schemas do not exist.

- [ ] **Step 3: Add request models**

```python
class AttributionConfigUpdate(BaseModel):
    default_model: Literal["first_touch", "last_touch", "linear"] = "last_touch"
    window_days: int = Field(default=7, ge=1, le=30)
    enabled_dimensions: list[Literal["platform", "keyword", "content"]] = Field(
        default_factory=lambda: ["platform", "keyword", "content"]
    )
    dedupe_by: Literal["external_lead_id", "phone_hash", "wechat_hash"] = "external_lead_id"
```

```python
class LeadImportItem(BaseModel):
    external_lead_id: str
    lead_status: str = "new"
    owner: str | None = None
    phone_hash: str | None = None
    wechat_hash: str | None = None
    source_platform: str | None = None
    source_keyword: str | None = None
```

```python
class LeadImportRequest(BaseModel):
    source_system: str = "manual"
    items: list[LeadImportItem] = Field(min_length=1)
```

```python
class TouchpointImportItem(BaseModel):
    external_lead_id: str
    touch_type: str
    platform: str | None = None
    source_keyword: str | None = None
    creator_id: str | None = None
    post_id: int | None = None
    raw_record_id: int | None = None
    touch_time: datetime
```

```python
class ConversionEventImportItem(BaseModel):
    external_lead_id: str
    event_type: str
    event_value: float | None = None
    event_time: datetime
    operator: str | None = None
```

- [ ] **Step 4: Add router endpoints**

```python
@router.get("/growth-projects/{project_id}/attribution-config")
async def get_growth_project_attribution_config(project_id: str):
    ...


@router.put("/growth-projects/{project_id}/attribution-config")
async def update_growth_project_attribution_config(project_id: str, request: AttributionConfigUpdate):
    ...


@router.post("/growth-projects/{project_id}/leads/import")
async def import_growth_project_leads(project_id: str, request: LeadImportRequest):
    ...


@router.post("/growth-projects/{project_id}/touchpoints/import")
async def import_growth_project_touchpoints(project_id: str, request: TouchpointImportRequest):
    ...


@router.post("/growth-projects/{project_id}/conversion-events/import")
async def import_growth_project_conversion_events(project_id: str, request: ConversionEventImportRequest):
    ...
```

- [ ] **Step 5: Run tests to verify import/config endpoints pass**

Run: `pytest tests/test_lead_attribution_api.py -v`

Expected: PASS for import/config tests

- [ ] **Step 6: Commit**

```bash
git add research/schemas.py api/routers/research.py tests/test_lead_attribution_api.py
git commit -m "feat: add lead attribution import and config endpoints"
```

### Task 5: Add Report Aggregation And `/reports/lead-attribution/*` Endpoints

**Files:**
- Modify: `D:\program\media_analyse_api_only\research\lead_attribution.py`
- Modify: `D:\program\media_analyse_api_only\api\routers\reports.py`
- Test: `D:\program\media_analyse_api_only\tests\test_lead_attribution_api.py`

- [ ] **Step 1: Write failing report tests**

```python
def test_lead_attribution_summary_report(client):
    response = client.get("/api/reports/lead-attribution/summary?project_id=pet-food-growth&model=last_touch")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "funnel" in data
    assert "top_platforms" in data
```

```python
def test_lead_attribution_content_breakdown(client):
    response = client.get("/api/reports/lead-attribution/content?project_id=pet-food-growth&model=last_touch")
    assert response.status_code == 200
    assert "rows" in response.json()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_lead_attribution_api.py -v`

Expected: FAIL because the report routes do not exist.

- [ ] **Step 3: Add aggregation helpers**

```python
def build_lead_attribution_summary(leads: list[dict], conversion_events: list[dict], attribution_rows: list[dict]) -> dict:
    return {
        "summary": {
            "lead_count": len(leads),
            "qualified_lead_count": sum(1 for lead in leads if lead.get("lead_status") in {"qualified", "contacted", "dealt"}),
            "deal_count": sum(1 for event in conversion_events if event["event_type"] == "deal_closed"),
            "deal_amount": sum(float(event.get("event_value") or 0) for event in conversion_events if event["event_type"] == "deal_closed"),
        },
        "funnel": [],
        "top_platforms": [],
        "top_keywords": [],
        "top_contents": [],
        "diagnostics": [],
    }
```

```python
def group_attribution_rows(attribution_rows: list[dict], dimension: str) -> list[dict]:
    grouped = {}
    for row in attribution_rows:
        if row["dimension"] != dimension:
            continue
        bucket = grouped.setdefault(row["dimension_key"], {"dimension_key": row["dimension_key"], "credit": 0.0})
        bucket["credit"] += float(row["credit"])
    return sorted(grouped.values(), key=lambda item: item["credit"], reverse=True)
```

- [ ] **Step 4: Add report routes**

```python
@router.get("/lead-attribution/summary")
async def get_lead_attribution_summary(project_id: str, model: str = "last_touch", date_from: str | None = None, date_to: str | None = None):
    ...


@router.get("/lead-attribution/platform")
async def get_lead_attribution_platform(project_id: str, model: str = "last_touch"):
    ...


@router.get("/lead-attribution/keyword")
async def get_lead_attribution_keyword(project_id: str, model: str = "last_touch"):
    ...


@router.get("/lead-attribution/content")
async def get_lead_attribution_content(project_id: str, model: str = "last_touch"):
    ...
```

- [ ] **Step 5: Run tests to verify report endpoints pass**

Run: `pytest tests/test_lead_attribution_api.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add research/lead_attribution.py api/routers/reports.py tests/test_lead_attribution_api.py
git commit -m "feat: add lead attribution reporting endpoints"
```

### Task 6: Add Lead Detail And Timeline APIs For UI Drilldown

**Files:**
- Modify: `D:\program\media_analyse_api_only\api\routers\research.py`
- Modify: `D:\program\media_analyse_api_only\research\repository.py`
- Test: `D:\program\media_analyse_api_only\tests\test_lead_attribution_api.py`

- [ ] **Step 1: Write failing detail tests**

```python
def test_get_lead_detail(client):
    response = client.get("/api/research/leads/1")
    assert response.status_code == 200
    assert "lead" in response.json()
    assert "touchpoints" in response.json()
    assert "conversion_events" in response.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_lead_attribution_api.py::test_get_lead_detail -v`

Expected: FAIL because the endpoint does not exist.

- [ ] **Step 3: Add repository and routes**

```python
async def get_lead_detail(self, lead_id: int) -> dict[str, Any] | None:
    lead = ...
    touchpoints = ...
    conversion_events = ...
    attribution = ...
    return {
        "lead": lead,
        "touchpoints": touchpoints,
        "conversion_events": conversion_events,
        "attribution": attribution,
    }
```

```python
@router.get("/leads/{lead_id}")
async def get_lead_detail(lead_id: int):
    ...


@router.get("/leads/{lead_id}/timeline")
async def get_lead_timeline(lead_id: int):
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_lead_attribution_api.py::test_get_lead_detail -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/routers/research.py research/repository.py tests/test_lead_attribution_api.py
git commit -m "feat: add lead attribution detail and timeline endpoints"
```

### Task 7: Wire Frontend Types And API Loading

**Files:**
- Modify: `D:\program\media_analyse_api_only\api\webui\src\types.ts`
- Modify: `D:\program\media_analyse_api_only\api\webui\src\main.tsx`
- Test: manual browser verification plus frontend build

- [ ] **Step 1: Add frontend types**

```ts
export type LeadAttributionSummary = {
  summary: {
    lead_count: number;
    qualified_lead_count: number;
    deal_count: number;
    deal_amount: number;
  };
  funnel: Array<{ key: string; label: string; value: number; rate?: number | null }>;
  top_platforms: Array<{ dimension_key: string; credit: number }>;
  top_keywords: Array<{ dimension_key: string; credit: number }>;
  top_contents: Array<{ dimension_key: string; credit: number; title?: string }>;
  diagnostics: Array<{ code: string; title: string; body: string }>;
};
```

```ts
export type LeadAttributionRow = {
  dimension_key: string;
  credit: number;
  lead_count?: number;
  deal_count?: number;
  deal_amount?: number;
  title?: string;
  platform?: string;
  source_keyword?: string;
};
```

- [ ] **Step 2: Add API loaders in `main.tsx`**

```ts
const [leadAttributionSummary, setLeadAttributionSummary] = React.useState<LeadAttributionSummary | null>(null);

const loadLeadAttribution = React.useCallback(async (projectId: string) => {
  const data = await api<LeadAttributionSummary>(
    `/api/reports/lead-attribution/summary?project_id=${encodeURIComponent(projectId)}&model=last_touch`,
  );
  setLeadAttributionSummary(data);
}, []);
```

- [ ] **Step 3: Run frontend build**

Run: `npm.cmd run build`

Expected: PASS with generated `dist` assets.

- [ ] **Step 4: Commit**

```bash
git add api/webui/src/types.ts api/webui/src/main.tsx
git commit -m "feat: add frontend attribution data loading"
```

### Task 8: Replace `LeadAttributionPage` Mock Data With Real API States

**Files:**
- Modify: `D:\program\media_analyse_api_only\api\webui\src\pages\LeadAttributionPage.tsx`
- Test: manual UI verification and frontend build

- [ ] **Step 1: Replace summary cards and tables with props-driven data**

```tsx
export function LeadAttributionPage({
  summary,
  loading,
  error,
}: {
  summary: LeadAttributionSummary | null;
  loading?: boolean;
  error?: string | null;
}) {
  if (loading) {
    return <section className="la-page"><Card className="la-panel">Loading attribution data...</Card></section>;
  }
  if (error) {
    return <section className="la-page"><Card className="la-panel">{error}</Card></section>;
  }
  if (!summary) {
    return <section className="la-page"><Card className="la-panel">No attribution data yet. Import leads and conversion events first.</Card></section>;
  }
  return <section className="la-page">{/* render cards and tables from summary */}</section>;
}
```

- [ ] **Step 2: Keep scope tight**

```tsx
const metricCards = [
  { label: "线索数", value: String(summary.summary.lead_count) },
  { label: "有效线索", value: String(summary.summary.qualified_lead_count) },
  { label: "成交数", value: String(summary.summary.deal_count) },
  { label: "成交额", value: String(summary.summary.deal_amount) },
];
```

- [ ] **Step 3: Run frontend build**

Run: `npm.cmd run build`

Expected: PASS

- [ ] **Step 4: Manual verification**

Run the API server, open the WebUI, navigate to `线索归因`, and verify:

- Empty-state message appears before import.
- Summary cards update after importing test data.
- Platform/content/keyword sections render without mock rows.

- [ ] **Step 5: Commit**

```bash
git add api/webui/src/pages/LeadAttributionPage.tsx
git commit -m "feat: wire lead attribution page to real APIs"
```

### Task 9: Add Snapshot Refresh Job And Documentation

**Files:**
- Modify: `D:\program\media_analyse_api_only\research\lead_attribution.py`
- Modify: `D:\program\media_analyse_api_only\api\routers\reports.py`
- Modify: `D:\program\media_analyse_api_only\README_API_ONLY.md`
- Test: `D:\program\media_analyse_api_only\tests\test_lead_attribution_domain.py`

- [ ] **Step 1: Add snapshot builder**

```python
def build_daily_snapshot_payload(project_id: int, model: str, summary: dict, platform_rows: list[dict], keyword_rows: list[dict], content_rows: list[dict]) -> dict:
    return {
        "project_id": project_id,
        "snapshot_date": date.today(),
        "model": model,
        "funnel_json": summary.get("funnel") or {},
        "platform_metrics_json": platform_rows,
        "keyword_metrics_json": keyword_rows,
        "content_metrics_json": content_rows,
        "creator_metrics_json": [],
        "summary_json": summary.get("summary") or {},
    }
```

- [ ] **Step 2: Expose manual refresh route**

```python
@router.post("/lead-attribution/summary/refresh")
async def refresh_lead_attribution_summary(project_id: str, model: str = "last_touch"):
    ...
```

- [ ] **Step 3: Document the import-first workflow**

```md
## Lead Attribution V1

1. Create or reuse a growth project.
2. Import leads through `/api/research/growth-projects/{project_id}/leads/import`.
3. Import touchpoints and conversion events.
4. Read reports from `/api/reports/lead-attribution/*`.
```

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_lead_attribution_domain.py tests/test_lead_attribution_api.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add research/lead_attribution.py api/routers/reports.py README_API_ONLY.md tests/test_lead_attribution_domain.py tests/test_lead_attribution_api.py
git commit -m "docs: document lead attribution v1 workflow"
```

---

## Verification Checklist

- `pytest tests/test_lead_attribution_domain.py -v`
- `pytest tests/test_lead_attribution_api.py -v`
- `pytest tests/test_content_tracking_api.py -v`
- `npm.cmd run build`
- Manual import flow:
  - Create or reuse one growth project
  - Import one lead
  - Import two touchpoints
  - Import one `deal_closed` event
  - Verify `/api/reports/lead-attribution/summary`
  - Verify the `线索归因` page renders real data

## Scope Boundaries For V1

Included:
- `platform / keyword / content` attribution dimensions
- `first_touch / last_touch / linear` models
- Manual or CSV/API import for leads and conversion events
- Project-scoped reports and lead timeline drilldown

Explicitly excluded:
- Full CRM workflow
- Sales task assignment engine
- Cost ingestion and true ROI by channel
- Creator-level attribution in the UI
- Probabilistic cross-device identity resolution

## Risks And Guardrails

- Current codebase still carries non-commercial upstream inheritance risk in the crawler layer. Keep this work limited to internal or license-cleared environments until legal cleanup is complete.
- Attribution quality depends on external lead and conversion imports. Do not fabricate add-wechat or deal events from crawler data.
- Keep the first version deterministic and auditable. Every summary row must be traceable back to touchpoints and conversion events.

## Self-Review

- Spec coverage: model, import, report, detail, page wiring, snapshot refresh, and docs are all mapped to tasks.
- Placeholder scan: no `TODO`, `TBD`, or “write tests later” placeholders remain.
- Type consistency: model names, route prefixes, and dimensions are consistent across tasks.

Plan complete and saved to `docs/superpowers/plans/2026-05-24-lead-attribution-v1.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
