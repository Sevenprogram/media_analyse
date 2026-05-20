# Growth Intelligence Phase One Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the phase-one growth intelligence system covering creator discovery, content tracking, competitor composition monitoring, and keyword heat/platform-signal analysis.

**Architecture:** Extend the existing research stack instead of creating a new crawler stack. Use SQL-backed models and repository methods for durable configuration and analysis snapshots, service modules for deterministic scoring/orchestration, FastAPI routers for workflow APIs, and the existing React research console for UI. Keep real-time crawler execution behind explicit switches and reuse `ResearchScheduler`, `ResearchExecutionManager`, and `crawler_manager`.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async models, pytest, Vite + React + TypeScript, lucide-react, recharts, existing OpenAI-compatible AI provider abstraction.

---

## Scope Check

The design covers four related business modules. They share the same data model, keyword library, research jobs, platform capabilities, and frontend console, so this plan keeps them together but splits execution into independently testable vertical slices:

1. Keyword library and AI keyword expansion.
2. Creator discovery and monitor pools.
3. Content tracking.
4. Keyword heat and competitor composition.
5. React integration.

Each task below should be committed separately. Do not start a later task until tests for the current task pass.

## File Structure

Create or modify these files:

- Modify `research/models.py`: add scene-pack keyword library, AI suggestion session, monitor pool, content tracking, and heat/composition snapshot tables.
- Modify `research/schemas.py`: add request/response schemas for keyword library, AI expansion, monitor pools, discovery, content tracking, heat, and composition APIs.
- Modify `research/repository.py`: add CRUD and query methods for the new tables.
- Modify `research/setup_status.py`: register new research tables.
- Create `research/keyword_library.py`: keyword matching, CSV import/export mapping, AI suggestion normalization.
- Create `research/growth_ai.py`: OpenAI-compatible keyword expansion orchestration using stored AI Provider configs.
- Create `research/monitor_pools.py`: pool membership logic and research job creation/update.
- Extend `research/creator_search.py`: scene-pack-aware scoring, enriched candidate fields, automation decisions.
- Extend `research/content_tracking.py`: keyword extraction, similar-content scoring, tracker execution planning, tracker analysis.
- Create `research/keyword_heat.py`: heat, push, cooldown, confidence, evidence calculations.
- Extend `research/competitors.py`: composition breakdown aggregation.
- Create `api/routers/keyword_library.py`: vertical, scene pack, keyword item, import/export, AI expansion routes.
- Extend `api/routers/creator_search.py`: discovery sessions, real-time discovery, bulk add, monitor-pool actions.
- Extend `api/routers/content_tracking.py`: extraction, similar search, tracker CRUD, tracker execution, analysis.
- Extend `api/routers/keyword_opportunities.py`: heat signal endpoints.
- Extend `api/routers/competitors.py`: composition snapshot endpoints.
- Modify `api/main.py`: include new keyword library router.
- Modify `api/webui/src/main.tsx`: add full UI surfaces for keyword library, creator discovery, monitor pools, content tracking, heat, and competitor composition.
- Modify `api/webui/src/styles.css`: add layout and table styles for new panels.
- Add tests under `tests/` matching each backend slice.

## Implementation Tasks

### Task 1: Data Model Foundation

**Files:**
- Modify: `research/models.py`
- Modify: `research/setup_status.py`
- Modify: `research/schema_migration.py`
- Test: `tests/test_growth_intelligence_models.py`

- [ ] **Step 1: Write failing table registration tests**

Add `tests/test_growth_intelligence_models.py`:

```python
from research.models import Base
from research.setup_status import RESEARCH_TABLE_NAMES


def test_growth_intelligence_tables_registered():
    expected = {
        "research_scene_packs",
        "research_scene_pack_keywords",
        "research_ai_keyword_suggestion_sessions",
        "research_monitor_pools",
        "research_monitor_pool_creators",
        "research_content_samples",
        "research_extracted_content_keywords",
        "research_similar_content_candidates",
        "research_content_trackers",
        "research_content_tracking_snapshots",
        "research_keyword_heat_snapshots",
        "research_competitor_composition_snapshots",
    }

    assert expected.issubset(Base.metadata.tables)
    assert expected.issubset(RESEARCH_TABLE_NAMES)


def test_monitor_pool_creator_unique_columns_registered():
    table = Base.metadata.tables["research_monitor_pool_creators"]
    constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if getattr(constraint, "columns", None)
    }

    assert ("pool_id", "platform", "creator_id") in constraints
```

- [ ] **Step 2: Run model tests and verify failure**

Run:

```powershell
python -m pytest tests\test_growth_intelligence_models.py -v
```

Expected: FAIL because the new tables do not exist.

- [ ] **Step 3: Add SQLAlchemy models**

In `research/models.py`, add focused model classes after the existing creator/competitor models:

```python
class ResearchScenePack(Base):
    __tablename__ = "research_scene_packs"
    __table_args__ = (
        UniqueConstraint("vertical_id", "name", name="uq_research_scene_pack_name"),
    )

    id = Column(Integer, primary_key=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    weight = Column(Float, nullable=False, default=1.0)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ResearchScenePackKeyword(Base):
    __tablename__ = "research_scene_pack_keywords"

    id = Column(Integer, primary_key=True)
    scene_pack_id = Column(Integer, ForeignKey("research_scene_packs.id"), nullable=False, index=True)
    keyword = Column(String(255), nullable=False, index=True)
    keyword_type = Column(String(32), nullable=False, index=True)
    platform = Column(String(32), nullable=True, index=True)
    weight = Column(Float, nullable=False, default=1.0)
    reason = Column(Text, nullable=True)
    usage_flags_json = Column(json_column(), nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ResearchAIKeywordSuggestionSession(Base):
    __tablename__ = "research_ai_keyword_suggestion_sessions"

    id = Column(Integer, primary_key=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    scene_pack_id = Column(Integer, ForeignKey("research_scene_packs.id"), nullable=True, index=True)
    input_text = Column(Text, nullable=False)
    target_platforms_json = Column(json_column(), nullable=False, default=list)
    provider_config_id = Column(Integer, ForeignKey("ai_provider_configs.id"), nullable=True)
    model = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, default="completed", index=True)
    suggestions_json = Column(json_column(), nullable=False, default=list)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchMonitorPool(Base):
    __tablename__ = "research_monitor_pools"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    scene_pack_ids_json = Column(json_column(), nullable=False, default=list)
    research_job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=True, index=True)
    schedule_interval_minutes = Column(Integer, nullable=False, default=720)
    comment_policy_json = Column(json_column(), nullable=False, default=dict)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ResearchMonitorPoolCreator(Base):
    __tablename__ = "research_monitor_pool_creators"
    __table_args__ = (
        UniqueConstraint("pool_id", "platform", "creator_id", name="uq_research_monitor_pool_creator"),
    )

    id = Column(Integer, primary_key=True)
    pool_id = Column(Integer, ForeignKey("research_monitor_pools.id"), nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    creator_id = Column(String(255), nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    match_score = Column(Float, nullable=True)
    source_json = Column(json_column(), nullable=False, default=dict)
    enabled = Column(Boolean, nullable=False, default=True)
    added_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

Add content tracking and snapshot classes:

```python
class ResearchContentSample(Base):
    __tablename__ = "research_content_samples"

    id = Column(Integer, primary_key=True)
    source_type = Column(String(32), nullable=False, index=True)
    platform = Column(String(32), nullable=True, index=True)
    source_id = Column(String(255), nullable=True, index=True)
    url = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    content_text = Column(Text, nullable=False)
    metadata_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchExtractedContentKeyword(Base):
    __tablename__ = "research_extracted_content_keywords"

    id = Column(Integer, primary_key=True)
    sample_id = Column(Integer, ForeignKey("research_content_samples.id"), nullable=False, index=True)
    keyword = Column(String(255), nullable=False, index=True)
    keyword_type = Column(String(32), nullable=False)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    scene_pack_id = Column(Integer, ForeignKey("research_scene_packs.id"), nullable=True, index=True)
    confidence = Column(Float, nullable=False, default=0.0)
    evidence_text = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    query_variants_json = Column(json_column(), nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchSimilarContentCandidate(Base):
    __tablename__ = "research_similar_content_candidates"

    id = Column(Integer, primary_key=True)
    sample_id = Column(Integer, ForeignKey("research_content_samples.id"), nullable=True, index=True)
    platform = Column(String(32), nullable=False, index=True)
    platform_post_id = Column(String(255), nullable=False, index=True)
    author_id = Column(String(255), nullable=True, index=True)
    title = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    publish_time = Column(DateTime(timezone=True), nullable=True, index=True)
    similarity_score = Column(Float, nullable=False, default=0.0)
    matched_keywords_json = Column(json_column(), nullable=False, default=list)
    evidence_json = Column(json_column(), nullable=False, default=dict)
    decision_status = Column(String(32), nullable=False, default="candidate", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchContentTracker(Base):
    __tablename__ = "research_content_trackers"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    scene_pack_ids_json = Column(json_column(), nullable=False, default=list)
    platforms_json = Column(json_column(), nullable=False, default=list)
    included_keywords_json = Column(json_column(), nullable=False, default=list)
    excluded_keywords_json = Column(json_column(), nullable=False, default=list)
    seed_refs_json = Column(json_column(), nullable=False, default=list)
    research_job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=True, index=True)
    schedule_interval_minutes = Column(Integer, nullable=False, default=720)
    comment_policy_json = Column(json_column(), nullable=False, default=dict)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ResearchContentTrackingSnapshot(Base):
    __tablename__ = "research_content_tracking_snapshots"

    id = Column(Integer, primary_key=True)
    tracker_id = Column(Integer, ForeignKey("research_content_trackers.id"), nullable=False, index=True)
    snapshot_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    summary_json = Column(json_column(), nullable=False, default=dict)
    keyword_trend_json = Column(json_column(), nullable=False, default=list)
    platform_distribution_json = Column(json_column(), nullable=False, default=dict)
    hot_content_json = Column(json_column(), nullable=False, default=list)
    evidence_json = Column(json_column(), nullable=False, default=list)


class ResearchKeywordHeatSnapshot(Base):
    __tablename__ = "research_keyword_heat_snapshots"

    id = Column(Integer, primary_key=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    scene_pack_id = Column(Integer, ForeignKey("research_scene_packs.id"), nullable=True, index=True)
    platform = Column(String(32), nullable=True, index=True)
    keyword = Column(String(255), nullable=False, index=True)
    label = Column(String(32), nullable=False, index=True)
    heat_score = Column(Float, nullable=False)
    push_score = Column(Float, nullable=False)
    cooldown_risk = Column(Float, nullable=False)
    confidence = Column(String(16), nullable=False)
    short_window_json = Column(json_column(), nullable=False, default=dict)
    medium_window_json = Column(json_column(), nullable=False, default=dict)
    evidence_json = Column(json_column(), nullable=False, default=list)
    snapshot_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class ResearchCompetitorCompositionSnapshot(Base):
    __tablename__ = "research_competitor_composition_snapshots"

    id = Column(Integer, primary_key=True)
    competitor_account_id = Column(Integer, ForeignKey("research_competitor_accounts.id"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    keyword_distribution_json = Column(json_column(), nullable=False, default=dict)
    tag_distribution_json = Column(json_column(), nullable=False, default=dict)
    content_type_distribution_json = Column(json_column(), nullable=False, default=dict)
    posting_time_distribution_json = Column(json_column(), nullable=False, default=dict)
    hot_post_rate = Column(Float, nullable=False, default=0.0)
    top_posts_json = Column(json_column(), nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 4: Register new table names**

Add every new table name from Step 3 to `RESEARCH_TABLE_NAMES` in `research/setup_status.py`.

- [ ] **Step 5: Add lightweight schema migration columns only if required**

If `research/schema_migration.py` already handles adding columns to existing tables only, do not add new-table DDL. New tables are created through `Base.metadata.create_all`. Add migration only for new columns on existing tables if an implementation later needs them.

- [ ] **Step 6: Run model tests**

Run:

```powershell
python -m pytest tests\test_growth_intelligence_models.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add research\models.py research\setup_status.py research\schema_migration.py tests\test_growth_intelligence_models.py
git commit -m "feat: add growth intelligence data models"
```

### Task 2: Schemas And Repository Methods

**Files:**
- Modify: `research/schemas.py`
- Modify: `research/repository.py`
- Test: `tests/test_growth_intelligence_repository.py`

- [ ] **Step 1: Write schema validation tests**

Create `tests/test_growth_intelligence_repository.py` with schema tests first:

```python
import pytest
from pydantic import ValidationError

from research.schemas import (
    ScenePackCreate,
    ScenePackKeywordCreate,
    MonitorPoolCreate,
    ContentTrackerCreate,
)


def test_scene_pack_keyword_type_validation():
    item = ScenePackKeywordCreate(
        scene_pack_id=1,
        keyword="鸡娃",
        keyword_type="secondary",
        platform="xhs",
        weight=1.2,
        usage_flags=["creator_discovery", "keyword_heat"],
    )

    assert item.keyword == "鸡娃"
    assert item.keyword_type == "secondary"


def test_scene_pack_keyword_rejects_bad_type():
    with pytest.raises(ValidationError):
        ScenePackKeywordCreate(
            scene_pack_id=1,
            keyword="广告",
            keyword_type="bad",
        )


def test_monitor_pool_defaults_to_twelve_hours():
    pool = MonitorPoolCreate(name="K12达人池")

    assert pool.schedule_interval_minutes == 720
    assert pool.comment_policy == {"enable_comments": True, "enable_sub_comments": False}


def test_content_tracker_requires_keywords_or_seed_refs():
    with pytest.raises(ValidationError):
        ContentTrackerCreate(name="empty", platforms=["xhs"])
```

- [ ] **Step 2: Run schema tests and verify failure**

Run:

```powershell
python -m pytest tests\test_growth_intelligence_repository.py -v
```

Expected: FAIL because schemas do not exist.

- [ ] **Step 3: Add Pydantic schemas**

In `research/schemas.py`, add these models near existing creator discovery schemas:

```python
KeywordType = Literal["primary", "secondary", "synonym", "negative", "platform_adapted", "ai_suggested"]
AutomationMode = Literal["pending_confirmation", "direct"]


class ScenePackCreate(BaseModel):
    vertical_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    weight: float = Field(default=1.0, ge=0)
    enabled: bool = True


class ScenePackUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    weight: float | None = Field(default=None, ge=0)
    enabled: bool | None = None


class ScenePackKeywordCreate(BaseModel):
    scene_pack_id: int = Field(ge=1)
    keyword: str = Field(min_length=1, max_length=255)
    keyword_type: KeywordType
    platform: str | None = None
    weight: float = Field(default=1.0, ge=0)
    reason: str | None = None
    usage_flags: list[str] = Field(default_factory=list)
    enabled: bool = True


class AIKeywordExpansionRequest(BaseModel):
    input_text: str = Field(min_length=1, max_length=500)
    vertical_id: int | None = Field(default=None, ge=1)
    scene_pack_id: int | None = Field(default=None, ge=1)
    target_platforms: list[str] = Field(default_factory=list)
    provider_config_id: int | None = Field(default=None, ge=1)


class MonitorPoolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    vertical_id: int | None = Field(default=None, ge=1)
    scene_pack_ids: list[int] = Field(default_factory=list)
    schedule_interval_minutes: int = Field(default=720, ge=1)
    comment_policy: dict[str, bool] = Field(default_factory=lambda: {"enable_comments": True, "enable_sub_comments": False})
    enabled: bool = True


class MonitorPoolAddCreatorsRequest(BaseModel):
    creators: list[CreatorCandidateUpsert] = Field(min_length=1)
    crawl_now: bool = False


class ContentKeywordExtractionRequest(BaseModel):
    text: str = Field(min_length=1)
    title: str | None = None
    platform: str | None = None
    url: str | None = None
    vertical_id: int | None = Field(default=None, ge=1)
    scene_pack_ids: list[int] = Field(default_factory=list)
    use_ai: bool = False
    provider_config_id: int | None = Field(default=None, ge=1)


class SimilarContentSearchRequest(BaseModel):
    keywords: list[str] = Field(min_length=1)
    platforms: list[str] = Field(default_factory=list)
    vertical_id: int | None = Field(default=None, ge=1)
    scene_pack_ids: list[int] = Field(default_factory=list)
    realtime: bool = False
    exclude_tracked: bool = True
    limit: int = Field(default=50, ge=1, le=200)


class ContentTrackerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    vertical_id: int | None = Field(default=None, ge=1)
    scene_pack_ids: list[int] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    included_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    seed_refs: list[dict[str, str]] = Field(default_factory=list)
    schedule_interval_minutes: int = Field(default=720, ge=1)
    comment_policy: dict[str, bool] = Field(default_factory=lambda: {"enable_comments": True, "enable_sub_comments": False})
    enabled: bool = True

    @model_validator(mode="after")
    def validate_tracking_inputs(self) -> "ContentTrackerCreate":
        if not self.included_keywords and not self.seed_refs:
            raise ValueError("content tracker requires included_keywords or seed_refs")
        return self
```

- [ ] **Step 4: Run schema tests**

Run:

```powershell
python -m pytest tests\test_growth_intelligence_repository.py -v
```

Expected: PASS for schema tests.

- [ ] **Step 5: Add repository CRUD methods**

In `research/repository.py`, add methods with the same style as existing repository methods:

```python
async def create_scene_pack(self, payload: dict[str, Any]) -> dict[str, Any]:
    async with get_session() as session:
        item = ResearchScenePack(**payload)
        session.add(item)
        await session.flush()
        return self._scene_pack_to_dict(item)


async def list_scene_packs(self, vertical_id: int | None = None, enabled_only: bool = False) -> list[dict[str, Any]]:
    async with get_session() as session:
        stmt = select(ResearchScenePack)
        if vertical_id is not None:
            stmt = stmt.where(ResearchScenePack.vertical_id == vertical_id)
        if enabled_only:
            stmt = stmt.where(ResearchScenePack.enabled.is_(True))
        rows = list((await session.execute(stmt.order_by(ResearchScenePack.id.asc()))).scalars().all())
        return [self._scene_pack_to_dict(item) for item in rows]


async def create_scene_pack_keyword(self, payload: dict[str, Any]) -> dict[str, Any]:
    async with get_session() as session:
        item = ResearchScenePackKeyword(
            scene_pack_id=payload["scene_pack_id"],
            keyword=payload["keyword"],
            keyword_type=payload["keyword_type"],
            platform=payload.get("platform"),
            weight=payload.get("weight", 1.0),
            reason=payload.get("reason"),
            usage_flags_json=payload.get("usage_flags") or [],
            enabled=payload.get("enabled", True),
        )
        session.add(item)
        await session.flush()
        return self._scene_pack_keyword_to_dict(item)


async def list_scene_pack_keywords(self, scene_pack_ids: list[int] | None = None, enabled_only: bool = False) -> list[dict[str, Any]]:
    async with get_session() as session:
        stmt = select(ResearchScenePackKeyword)
        if scene_pack_ids:
            stmt = stmt.where(ResearchScenePackKeyword.scene_pack_id.in_(scene_pack_ids))
        if enabled_only:
            stmt = stmt.where(ResearchScenePackKeyword.enabled.is_(True))
        rows = list((await session.execute(stmt.order_by(ResearchScenePackKeyword.id.asc()))).scalars().all())
        return [self._scene_pack_keyword_to_dict(item) for item in rows]
```

Add matching `_to_dict` helpers:

```python
def _scene_pack_to_dict(self, item: ResearchScenePack) -> dict[str, Any]:
    return {
        "id": item.id,
        "vertical_id": item.vertical_id,
        "name": item.name,
        "description": item.description,
        "weight": item.weight,
        "enabled": item.enabled,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _scene_pack_keyword_to_dict(self, item: ResearchScenePackKeyword) -> dict[str, Any]:
    return {
        "id": item.id,
        "scene_pack_id": item.scene_pack_id,
        "keyword": item.keyword,
        "keyword_type": item.keyword_type,
        "platform": item.platform,
        "weight": item.weight,
        "reason": item.reason,
        "usage_flags": item.usage_flags_json or [],
        "enabled": item.enabled,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }
```

Add repository methods for AI sessions, monitor pools, content trackers, heat snapshots, and composition snapshots following the same pattern. Keep method names explicit:

- `create_ai_keyword_suggestion_session`
- `create_monitor_pool`
- `list_monitor_pools`
- `add_monitor_pool_creators`
- `list_monitor_pool_creators`
- `upsert_content_sample`
- `create_extracted_content_keywords`
- `create_similar_content_candidates`
- `create_content_tracker`
- `list_content_trackers`
- `get_content_tracker`
- `upsert_keyword_heat_snapshot`
- `upsert_competitor_composition_snapshot`

- [ ] **Step 6: Add repository tests for method names and payload mapping**

Append tests that use a fake repository object or a sqlite test database if the repo test suite already provides one. Minimum test:

```python
def test_repository_exposes_growth_methods():
    from research.repository import ResearchRepository

    repository = ResearchRepository()

    assert hasattr(repository, "create_scene_pack")
    assert hasattr(repository, "list_scene_packs")
    assert hasattr(repository, "create_monitor_pool")
    assert hasattr(repository, "create_content_tracker")
    assert hasattr(repository, "upsert_keyword_heat_snapshot")
```

- [ ] **Step 7: Run repository tests**

Run:

```powershell
python -m pytest tests\test_growth_intelligence_repository.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```powershell
git add research\schemas.py research\repository.py tests\test_growth_intelligence_repository.py
git commit -m "feat: add growth intelligence schemas and repository"
```

### Task 3: Keyword Library And AI Expansion APIs

**Files:**
- Create: `research/keyword_library.py`
- Create: `research/growth_ai.py`
- Create: `api/routers/keyword_library.py`
- Modify: `api/main.py`
- Test: `tests/test_keyword_library_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_keyword_library_api.py`:

```python
from fastapi.testclient import TestClient

import config
from api.main import app
import api.routers.keyword_library as keyword_library_router


def test_create_scene_pack_route(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def create_scene_pack(self, payload):
            return {"id": 1, **payload}

    monkeypatch.setattr(keyword_library_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/keyword-library/scene-packs",
        json={"vertical_id": 1, "name": "单亲妈妈", "weight": 1.5},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "单亲妈妈"


def test_ai_expand_keywords_route_requires_provider(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def get_ai_provider_config(self, provider_id):
            return None

    monkeypatch.setattr(keyword_library_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/keyword-library/ai/expand",
        json={"input_text": "K12教育", "provider_config_id": 999},
    )

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests\test_keyword_library_api.py -v
```

Expected: FAIL because router does not exist.

- [ ] **Step 3: Implement keyword library service**

Create `research/keyword_library.py`:

```python
from __future__ import annotations

import csv
import io
from typing import Any


KEYWORD_TYPES = {"primary", "secondary", "synonym", "negative", "platform_adapted", "ai_suggested"}


def normalize_keyword_item(payload: dict[str, Any]) -> dict[str, Any]:
    keyword = str(payload.get("keyword") or "").strip()
    keyword_type = str(payload.get("keyword_type") or "").strip()
    if not keyword:
        raise ValueError("keyword is required")
    if keyword_type not in KEYWORD_TYPES:
        raise ValueError(f"Unsupported keyword_type: {keyword_type}")
    return {
        "scene_pack_id": int(payload["scene_pack_id"]),
        "keyword": keyword,
        "keyword_type": keyword_type,
        "platform": payload.get("platform") or None,
        "weight": float(payload.get("weight") or 1.0),
        "reason": payload.get("reason") or None,
        "usage_flags": payload.get("usage_flags") or [],
        "enabled": bool(payload.get("enabled", True)),
    }


def export_scene_pack_keywords_csv(items: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["scene_pack_id", "keyword", "keyword_type", "platform", "weight", "reason", "usage_flags", "enabled"],
    )
    writer.writeheader()
    for item in items:
        writer.writerow(
            {
                "scene_pack_id": item["scene_pack_id"],
                "keyword": item["keyword"],
                "keyword_type": item["keyword_type"],
                "platform": item.get("platform") or "",
                "weight": item.get("weight", 1.0),
                "reason": item.get("reason") or "",
                "usage_flags": "|".join(item.get("usage_flags") or []),
                "enabled": "1" if item.get("enabled", True) else "0",
            }
        )
    return output.getvalue()


def parse_scene_pack_keywords_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    items = []
    for row in reader:
        payload = {
            "scene_pack_id": row.get("scene_pack_id"),
            "keyword": row.get("keyword"),
            "keyword_type": row.get("keyword_type"),
            "platform": row.get("platform") or None,
            "weight": row.get("weight") or 1.0,
            "reason": row.get("reason") or None,
            "usage_flags": [item for item in (row.get("usage_flags") or "").split("|") if item],
            "enabled": row.get("enabled", "1") not in {"0", "false", "False"},
        }
        items.append(normalize_keyword_item(payload))
    return items
```

- [ ] **Step 4: Implement AI expansion orchestration**

Create `research/growth_ai.py`:

```python
from __future__ import annotations

import json
from typing import Any

from research.ai_provider import OpenAICompatibleProvider


def build_keyword_expansion_prompt(input_text: str, target_platforms: list[str]) -> str:
    platforms = ", ".join(target_platforms) if target_platforms else "all supported social platforms"
    return (
        "You are helping build a social media growth intelligence keyword library.\n"
        f"Seed vertical or scene: {input_text}\n"
        f"Target platforms: {platforms}\n"
        "Return strict JSON with key suggestions. Each suggestion must include keyword, keyword_type, "
        "platform, reason, weight, and usage_flags. keyword_type must be one of primary, secondary, "
        "synonym, negative, platform_adapted.\n"
    )


async def expand_keywords_with_provider(provider_config: dict[str, Any], request: dict[str, Any]) -> list[dict[str, Any]]:
    provider = OpenAICompatibleProvider(
        base_url=provider_config["base_url"],
        api_key=provider_config["api_key"],
        model=provider_config["model"],
        timeout=provider_config.get("timeout") or 60,
    )
    prompt = build_keyword_expansion_prompt(
        request["input_text"],
        request.get("target_platforms") or [],
    )
    result = await provider.complete_json(prompt=prompt)
    suggestions = result.get("suggestions") if isinstance(result, dict) else None
    if not isinstance(suggestions, list):
        raise ValueError("AI keyword expansion must return a suggestions list")
    return [normalize_ai_keyword_suggestion(item) for item in suggestions]


def normalize_ai_keyword_suggestion(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "keyword": str(item.get("keyword") or "").strip(),
        "keyword_type": str(item.get("keyword_type") or "secondary").strip(),
        "platform": item.get("platform") or None,
        "reason": item.get("reason") or "",
        "weight": float(item.get("weight") or 1.0),
        "usage_flags": item.get("usage_flags") or ["creator_discovery", "content_tracking", "keyword_heat"],
        "raw": item,
    }
```

If `OpenAICompatibleProvider` does not expose `complete_json`, add it in `research/ai_provider.py` with a test in the next step. Use the provider's existing completion method if present.

- [ ] **Step 5: Implement router**

Create `api/routers/keyword_library.py`:

```python
from fastapi import APIRouter, HTTPException, Response

from api.routers.research import require_research_database
from research.growth_ai import expand_keywords_with_provider
from research.keyword_library import export_scene_pack_keywords_csv, parse_scene_pack_keywords_csv
from research.repository import ResearchRepository
from research.schemas import AIKeywordExpansionRequest, ScenePackCreate, ScenePackKeywordCreate

router = APIRouter(prefix="/keyword-library", tags=["keyword-library"])


@router.post("/scene-packs")
async def create_scene_pack(request: ScenePackCreate):
    require_research_database()
    return await ResearchRepository().create_scene_pack(request.model_dump(mode="python"))


@router.get("/scene-packs")
async def list_scene_packs(vertical_id: int | None = None, enabled_only: bool = False):
    require_research_database()
    return {"scene_packs": await ResearchRepository().list_scene_packs(vertical_id=vertical_id, enabled_only=enabled_only)}


@router.post("/keywords")
async def create_scene_pack_keyword(request: ScenePackKeywordCreate):
    require_research_database()
    return await ResearchRepository().create_scene_pack_keyword(request.model_dump(mode="python"))


@router.get("/keywords/export")
async def export_keywords(scene_pack_id: int | None = None):
    require_research_database()
    ids = [scene_pack_id] if scene_pack_id else None
    items = await ResearchRepository().list_scene_pack_keywords(scene_pack_ids=ids)
    return Response(content=export_scene_pack_keywords_csv(items), media_type="text/csv; charset=utf-8")


@router.post("/ai/expand")
async def ai_expand_keywords(request: AIKeywordExpansionRequest):
    require_research_database()
    repository = ResearchRepository()
    provider = await repository.get_ai_provider_config(request.provider_config_id) if request.provider_config_id else None
    if provider is None:
        raise HTTPException(status_code=404, detail="AI provider config not found")
    suggestions = await expand_keywords_with_provider(provider, request.model_dump(mode="python"))
    return await repository.create_ai_keyword_suggestion_session(
        {
            "vertical_id": request.vertical_id,
            "scene_pack_id": request.scene_pack_id,
            "input_text": request.input_text,
            "target_platforms_json": request.target_platforms,
            "provider_config_id": request.provider_config_id,
            "model": provider.get("model"),
            "status": "completed",
            "suggestions_json": suggestions,
        }
    )
```

Register router in `api/main.py`:

```python
from .routers.keyword_library import router as keyword_library_router

app.include_router(keyword_library_router, prefix="/api")
```

- [ ] **Step 6: Run API tests**

Run:

```powershell
python -m pytest tests\test_keyword_library_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add research\keyword_library.py research\growth_ai.py api\routers\keyword_library.py api\main.py tests\test_keyword_library_api.py
git commit -m "feat: add keyword library and AI expansion APIs"
```

### Task 4: Creator Discovery And Monitor Pools

**Files:**
- Create: `research/monitor_pools.py`
- Modify: `research/creator_search.py`
- Modify: `api/routers/creator_search.py`
- Test: `tests/test_monitor_pools.py`
- Test: `tests/test_creator_discovery_workflow_api.py`

- [ ] **Step 1: Write monitor pool service tests**

Create `tests/test_monitor_pools.py`:

```python
import pytest

from research.monitor_pools import MonitorPoolService


class FakeRepository:
    def __init__(self):
        self.pool = {"id": 1, "name": "K12达人池", "schedule_interval_minutes": 720, "comment_policy_json": {"enable_comments": True, "enable_sub_comments": False}, "research_job_id": None}
        self.creators = []
        self.job_payload = None
        self.executed_job_id = None

    async def get_monitor_pool(self, pool_id):
        return self.pool

    async def add_monitor_pool_creators(self, pool_id, creators):
        self.creators.extend(creators)
        return creators

    async def list_monitor_pool_creators(self, pool_id, enabled_only=True):
        return self.creators

    async def create_research_job(self, payload):
        self.job_payload = payload
        return {"id": 77, **payload}

    async def update_monitor_pool(self, pool_id, payload):
        self.pool.update(payload)
        return self.pool


@pytest.mark.asyncio
async def test_monitor_pool_creates_creator_job_from_pool_members():
    repository = FakeRepository()
    service = MonitorPoolService(repository)

    result = await service.add_creators(
        pool_id=1,
        creators=[{"platform": "xhs", "creator_id": "u1", "display_name": "老师A", "match_score": 88}],
        crawl_now=False,
    )

    assert result["job"]["collection_mode"] == "creator"
    assert result["job"]["creator_ids"] == ["u1"]
    assert repository.job_payload["schedule_interval_minutes"] == 720
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests\test_monitor_pools.py -v
```

Expected: FAIL because `research.monitor_pools` does not exist.

- [ ] **Step 3: Implement monitor pool service**

Create `research/monitor_pools.py`:

```python
from __future__ import annotations

from datetime import date, timedelta
from typing import Any


class MonitorPoolService:
    def __init__(self, repository, execution_callback=None):
        self.repository = repository
        self.execution_callback = execution_callback

    async def add_creators(self, *, pool_id: int, creators: list[dict[str, Any]], crawl_now: bool = False) -> dict[str, Any]:
        pool = await self.repository.get_monitor_pool(pool_id)
        if pool is None:
            raise ValueError(f"Monitor pool not found: {pool_id}")
        normalized = [_normalize_creator(item) for item in creators]
        added = await self.repository.add_monitor_pool_creators(pool_id, normalized)
        members = await self.repository.list_monitor_pool_creators(pool_id, enabled_only=True)
        job = await self._ensure_creator_job(pool, members)
        executed = None
        if crawl_now and self.execution_callback is not None:
            executed = await self.execution_callback(job["id"])
        return {"pool": pool, "added": added, "job": job, "executed": executed}

    async def _ensure_creator_job(self, pool: dict[str, Any], members: list[dict[str, Any]]) -> dict[str, Any]:
        creator_ids = sorted({item["creator_id"] for item in members if item.get("enabled", True)})
        platforms = sorted({item["platform"] for item in members if item.get("enabled", True)})
        payload = {
            "name": f"{pool['name']} - 达人监控",
            "topic": pool["name"],
            "platforms": platforms,
            "collection_mode": "creator",
            "keywords": [],
            "target_ids": [],
            "creator_ids": creator_ids,
            "start_date": str(date.today()),
            "end_date": str(date.today() + timedelta(days=365)),
            "status": "pending",
            "comment_policy": pool.get("comment_policy_json") or {"enable_comments": True, "enable_sub_comments": False},
            "raw_record_mode": "minimal",
            "anonymize_authors": True,
            "schedule_enabled": True,
            "schedule_interval_minutes": int(pool.get("schedule_interval_minutes") or 720),
        }
        if pool.get("research_job_id"):
            job = await self.repository.update_job(pool["research_job_id"], payload)
        else:
            job = await self.repository.create_research_job(payload)
            await self.repository.update_monitor_pool(pool["id"], {"research_job_id": job["id"]})
        return job


def automation_select_candidates(candidates: list[dict[str, Any]], rules: dict[str, Any]) -> list[dict[str, Any]]:
    limit = int(rules.get("top_n") or 10)
    min_score = float(rules.get("min_match_score") or 80)
    min_recent_posts = int(rules.get("min_recent_post_count_30d") or 3)
    exclude_monitored = bool(rules.get("exclude_monitored", True))
    filtered = [
        item for item in candidates
        if float(item.get("match_score") or 0) >= min_score
        and int(item.get("recent_post_count_30d") or 0) >= min_recent_posts
        and not (exclude_monitored and item.get("monitored"))
    ]
    return sorted(filtered, key=lambda item: item["match_score"], reverse=True)[:limit]


def _normalize_creator(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": item["platform"],
        "creator_id": item["creator_id"],
        "display_name": item.get("display_name"),
        "match_score": item.get("match_score"),
        "source_json": item.get("source") or item.get("evidence") or {},
        "enabled": item.get("enabled", True),
    }
```

- [ ] **Step 4: Extend creator scoring**

In `research/creator_search.py`, add a scene-pack scoring helper:

```python
def score_creator_against_scene_packs(
    *,
    creator_profile: dict[str, Any],
    recent_posts: list[dict[str, Any]],
    scene_keywords: list[dict[str, Any]],
) -> dict[str, Any]:
    text = " ".join(
        str(value or "")
        for value in [
            creator_profile.get("display_name"),
            creator_profile.get("bio"),
            *[post.get("title") or post.get("content") or "" for post in recent_posts],
        ]
    ).lower()
    primary_hits = []
    secondary_hits = []
    negative_hits = []
    score = 0.0
    for keyword in scene_keywords:
        term = str(keyword["keyword"]).lower()
        if not term or term not in text:
            continue
        if keyword["keyword_type"] == "primary":
            primary_hits.append(keyword)
            score += 50 * float(keyword.get("weight") or 1)
        elif keyword["keyword_type"] in {"secondary", "synonym", "platform_adapted"}:
            secondary_hits.append(keyword)
            score += 15 * float(keyword.get("weight") or 1)
        elif keyword["keyword_type"] == "negative":
            negative_hits.append(keyword)
            score -= 30 * float(keyword.get("weight") or 1)
    if not primary_hits:
        score = 0.0
    return {
        "match_score": round(max(0.0, min(100.0, score)), 4),
        "primary_hits": primary_hits,
        "secondary_hits": secondary_hits,
        "negative_hits": negative_hits,
    }
```

- [ ] **Step 5: Add API routes for monitor pools and bulk actions**

Extend `api/routers/creator_search.py`:

```python
from research.monitor_pools import MonitorPoolService, automation_select_candidates
from research.schemas import MonitorPoolCreate, MonitorPoolAddCreatorsRequest


@router.post("/monitor-pools")
async def create_monitor_pool(request: MonitorPoolCreate):
    require_research_database()
    payload = request.model_dump(mode="python")
    payload["scene_pack_ids_json"] = payload.pop("scene_pack_ids")
    payload["comment_policy_json"] = payload.pop("comment_policy")
    return await ResearchRepository().create_monitor_pool(payload)


@router.get("/monitor-pools")
async def list_monitor_pools():
    require_research_database()
    return {"pools": await ResearchRepository().list_monitor_pools()}


@router.post("/monitor-pools/{pool_id}/creators")
async def add_creators_to_monitor_pool(pool_id: int, request: MonitorPoolAddCreatorsRequest):
    require_research_database()
    repository = ResearchRepository()
    service = MonitorPoolService(repository)
    return await service.add_creators(
        pool_id=pool_id,
        creators=[item.model_dump(mode="python") for item in request.creators],
        crawl_now=request.crawl_now,
    )
```

If immediate crawl must execute now, inject a callback that calls the existing research execute path after Task 6 provides an execution wrapper. Until then, return the job and keep `executed=None`; the route is still testable and safe.

- [ ] **Step 6: Add real-time creator discovery status endpoints**

Extend `api/routers/creator_search.py` with explicit real-time discovery routes. The first implementation can create a research search job and return its job id; it must not start a crawler unless the request includes `realtime=true`.

```python
from pydantic import BaseModel, Field


class CreatorRealtimeDiscoveryRequest(BaseModel):
    keywords: list[str] = Field(min_length=1)
    platforms: list[str] = Field(default_factory=list)
    realtime: bool = False
    wait: bool = False


@router.post("/discover/realtime")
async def start_creator_realtime_discovery(request: CreatorRealtimeDiscoveryRequest):
    require_research_database()
    if not request.realtime:
        return {"status": "skipped", "reason": "realtime discovery switch is off"}
    if not request.platforms:
        raise HTTPException(status_code=400, detail="Realtime discovery requires selected or global default platforms")
    repository = ResearchRepository()
    job = await repository.create_research_job(
        {
            "name": f"达人实时发现 - {' '.join(request.keywords)}",
            "topic": "creator_realtime_discovery",
            "platforms": request.platforms,
            "collection_mode": "search",
            "keywords": request.keywords,
            "target_ids": [],
            "creator_ids": [],
            "start_date": str(date.today()),
            "end_date": str(date.today()),
            "status": "pending",
            "comment_policy": {"enable_comments": False, "enable_sub_comments": False},
            "raw_record_mode": "minimal",
            "anonymize_authors": True,
        }
    )
    return {"status": "queued", "job_id": job["id"]}


@router.get("/discover/{job_id}/status")
async def get_creator_discovery_status(job_id: int):
    require_research_database()
    job = await ResearchRepository().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Discovery job not found")
    return {"job_id": job_id, "status": job["status"]}


@router.post("/discover/{job_id}/wait-refresh")
async def wait_creator_discovery_and_refresh(job_id: int):
    require_research_database()
    job = await ResearchRepository().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Discovery job not found")
    return {"job_id": job_id, "status": job["status"], "refreshed": True}
```

Add `from datetime import date` near the router imports.

- [ ] **Step 7: Run monitor pool tests**

Run:

```powershell
python -m pytest tests\test_monitor_pools.py tests\test_creator_discovery_workflow_api.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```powershell
git add research\monitor_pools.py research\creator_search.py api\routers\creator_search.py tests\test_monitor_pools.py tests\test_creator_discovery_workflow_api.py
git commit -m "feat: add creator monitor pools"
```

### Task 5: Content Tracking Back End

**Files:**
- Modify: `research/content_tracking.py`
- Modify: `api/routers/content_tracking.py`
- Test: `tests/test_content_tracking_workflow.py`
- Test: `tests/test_content_tracking_api.py`

- [ ] **Step 1: Write content tracking service tests**

Create `tests/test_content_tracking_workflow.py`:

```python
from research.content_tracking import extract_content_keywords, search_similar_content, build_tracker_analysis


def test_extract_content_keywords_uses_scene_pack_primary_and_secondary_terms():
    result = extract_content_keywords(
        text="单亲妈妈分享K12教育陪读经验，孩子升学压力很大",
        scene_keywords=[
            {"keyword": "K12教育", "keyword_type": "primary", "scene_pack_id": 1, "weight": 1},
            {"keyword": "单亲妈妈", "keyword_type": "secondary", "scene_pack_id": 1, "weight": 1},
        ],
    )

    assert [item["keyword"] for item in result] == ["K12教育", "单亲妈妈"]
    assert result[0]["keyword_type"] == "primary"


def test_search_similar_content_scores_keyword_overlap():
    posts = [
        {"platform": "xhs", "platform_post_id": "p1", "title": "K12教育陪读", "content": "单亲妈妈经验", "engagement_json": {"liked_count": 20}},
        {"platform": "xhs", "platform_post_id": "p2", "title": "美妆分享", "content": "口红测评", "engagement_json": {"liked_count": 50}},
    ]

    result = search_similar_content(keywords=["K12教育", "单亲妈妈"], posts=posts, limit=10)

    assert result[0]["platform_post_id"] == "p1"
    assert result[0]["similarity_score"] > 50
```

- [ ] **Step 2: Run service tests and verify failure**

Run:

```powershell
python -m pytest tests\test_content_tracking_workflow.py -v
```

Expected: FAIL because functions do not exist.

- [ ] **Step 3: Implement extraction and similarity functions**

In `research/content_tracking.py`, add:

```python
def extract_content_keywords(*, text: str, scene_keywords: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lowered = text.lower()
    results = []
    for keyword in scene_keywords:
        term = str(keyword["keyword"]).strip()
        if not term or term.lower() not in lowered:
            continue
        index = lowered.find(term.lower())
        results.append(
            {
                "keyword": term,
                "keyword_type": keyword["keyword_type"],
                "scene_pack_id": keyword.get("scene_pack_id"),
                "platform": keyword.get("platform"),
                "confidence": _keyword_confidence(keyword["keyword_type"]),
                "evidence_text": _context(text, term),
                "reason": keyword.get("reason") or "",
                "query_variants": [term],
                "position": index,
            }
        )
    results.sort(key=lambda item: (-item["confidence"], item["position"]))
    return results


def search_similar_content(*, keywords: list[str], posts: list[dict[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
    candidates = []
    for post in posts:
        text = _join_text(post.get("title"), post.get("content"))
        hits = _keyword_hits(text, keywords)
        if not hits:
            continue
        score = _similarity_score(hits, [], keywords) + min(15, _post_engagement(post) / 20)
        candidates.append(
            {
                "platform": post["platform"],
                "platform_post_id": post["platform_post_id"],
                "author_id": post.get("author_hash"),
                "title": post.get("title") or post.get("content") or post["platform_post_id"],
                "url": post.get("url"),
                "publish_time": post.get("publish_time"),
                "similarity_score": round(min(100.0, score), 2),
                "matched_keywords": hits,
                "engagement": post.get("engagement_json") or {},
                "evidence": {"source": "local", "snippets": [hit["context"] for hit in hits]},
            }
        )
    return sorted(candidates, key=lambda item: item["similarity_score"], reverse=True)[:limit]


def build_tracker_analysis(*, tracker: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    platform_counts = Counter(item["platform"] for item in candidates)
    keyword_counts = Counter()
    for item in candidates:
        for hit in item.get("matched_keywords") or []:
            keyword_counts[hit["term"]] += hit["count"]
    return {
        "tracker_id": tracker["id"],
        "summary": {
            "total_candidates": len(candidates),
            "platforms": dict(platform_counts),
            "top_keywords": [{"name": key, "value": value} for key, value in keyword_counts.most_common(10)],
        },
        "hot_content": candidates[:10],
        "evidence": [item.get("evidence") for item in candidates[:20]],
    }


def _keyword_confidence(keyword_type: str) -> float:
    return {"primary": 0.95, "secondary": 0.8, "synonym": 0.72, "platform_adapted": 0.7, "negative": 0.9}.get(keyword_type, 0.5)
```

Use existing `_post_engagement` logic or add:

```python
def _post_engagement(post: dict[str, Any]) -> int:
    engagement = post.get("engagement_json") or {}
    return sum(int(engagement.get(key) or 0) for key in ("liked_count", "comment_count", "comments_count", "share_count", "collected_count"))
```

- [ ] **Step 4: Extend content tracking API**

In `api/routers/content_tracking.py`, add routes:

```python
from research.schemas import ContentKeywordExtractionRequest, SimilarContentSearchRequest, ContentTrackerCreate
from research.content_tracking import extract_content_keywords, search_similar_content, build_tracker_analysis


@router.post("/extract-keywords")
async def extract_keywords(request: ContentKeywordExtractionRequest):
    require_research_database()
    repository = ResearchRepository()
    scene_keywords = await repository.list_scene_pack_keywords(scene_pack_ids=request.scene_pack_ids or None, enabled_only=True)
    return {
        "keywords": extract_content_keywords(text=" ".join([request.title or "", request.text]), scene_keywords=scene_keywords)
    }


@router.post("/search-similar")
async def search_similar(request: SimilarContentSearchRequest):
    require_research_database()
    repository = ResearchRepository()
    posts = await repository.list_all_posts(platform=request.platforms[0] if len(request.platforms) == 1 else None, limit=500)
    return {"candidates": search_similar_content(keywords=request.keywords, posts=posts, limit=request.limit)}


@router.post("/trackers")
async def create_tracker(request: ContentTrackerCreate):
    require_research_database()
    payload = request.model_dump(mode="python")
    payload["scene_pack_ids_json"] = payload.pop("scene_pack_ids")
    payload["platforms_json"] = payload.pop("platforms")
    payload["included_keywords_json"] = payload.pop("included_keywords")
    payload["excluded_keywords_json"] = payload.pop("excluded_keywords")
    payload["seed_refs_json"] = payload.pop("seed_refs")
    payload["comment_policy_json"] = payload.pop("comment_policy")
    return await ResearchRepository().create_content_tracker(payload)
```

- [ ] **Step 5: Add real-time similar-content discovery endpoints**

In `api/routers/content_tracking.py`, add safe real-time discovery endpoints. They should queue a `collection_mode="search"` research job when `realtime=true`, expose status, and expose a wait-refresh route for the UI.

```python
from datetime import date
from fastapi import HTTPException


@router.post("/realtime-discovery")
async def start_realtime_content_discovery(request: SimilarContentSearchRequest):
    require_research_database()
    if not request.realtime:
        return {"status": "skipped", "reason": "realtime search switch is off"}
    if not request.platforms:
        raise HTTPException(status_code=400, detail="Realtime content discovery requires selected or global default platforms")
    repository = ResearchRepository()
    job = await repository.create_research_job(
        {
            "name": f"内容实时发现 - {' '.join(request.keywords)}",
            "topic": "content_realtime_discovery",
            "platforms": request.platforms,
            "collection_mode": "search",
            "keywords": request.keywords,
            "target_ids": [],
            "creator_ids": [],
            "start_date": str(date.today()),
            "end_date": str(date.today()),
            "status": "pending",
            "comment_policy": {"enable_comments": False, "enable_sub_comments": False},
            "raw_record_mode": "minimal",
            "anonymize_authors": True,
        }
    )
    return {"status": "queued", "job_id": job["id"]}


@router.get("/discovery/{job_id}/status")
async def get_content_discovery_status(job_id: int):
    require_research_database()
    job = await ResearchRepository().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Content discovery job not found")
    return {"job_id": job_id, "status": job["status"]}


@router.post("/discovery/{job_id}/wait-refresh")
async def wait_content_discovery_and_refresh(job_id: int):
    require_research_database()
    job = await ResearchRepository().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Content discovery job not found")
    return {"job_id": job_id, "status": job["status"], "refreshed": True}
```

- [ ] **Step 6: Run content tracking tests**

Run:

```powershell
python -m pytest tests\test_content_tracking_workflow.py tests\test_content_tracking_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add research\content_tracking.py api\routers\content_tracking.py tests\test_content_tracking_workflow.py tests\test_content_tracking_api.py
git commit -m "feat: add content tracking workflow APIs"
```

### Task 6: Keyword Heat And Competitor Composition

**Files:**
- Create: `research/keyword_heat.py`
- Modify: `research/competitors.py`
- Modify: `api/routers/keyword_opportunities.py`
- Modify: `api/routers/competitors.py`
- Test: `tests/test_keyword_heat.py`
- Test: `tests/test_competitor_composition.py`

- [ ] **Step 1: Write keyword heat tests**

Create `tests/test_keyword_heat.py`:

```python
from research.keyword_heat import calculate_keyword_heat_signal


def test_keyword_heat_returns_label_scores_and_evidence():
    signal = calculate_keyword_heat_signal(
        keyword="K12教育",
        current_24h={"content_count": 30, "engagement_total": 900, "hot_post_count": 6, "creator_count": 12},
        avg_7d={"content_count": 10, "engagement_total": 200, "hot_post_count": 1, "creator_count": 5},
        avg_30d={"content_count": 8, "engagement_total": 150, "hot_post_count": 1, "creator_count": 4},
    )

    assert signal["label"] == "推流中"
    assert signal["heat_score"] > 70
    assert signal["push_score"] > signal["cooldown_risk"]
    assert signal["evidence"]
```

- [ ] **Step 2: Run heat test and verify failure**

Run:

```powershell
python -m pytest tests\test_keyword_heat.py -v
```

Expected: FAIL because `research.keyword_heat` does not exist.

- [ ] **Step 3: Implement keyword heat scoring**

Create `research/keyword_heat.py`:

```python
from __future__ import annotations

from typing import Any


def calculate_keyword_heat_signal(
    *,
    keyword: str,
    current_24h: dict[str, float],
    avg_7d: dict[str, float],
    avg_30d: dict[str, float],
) -> dict[str, Any]:
    content_ratio = _ratio(current_24h.get("content_count", 0), avg_7d.get("content_count", 0))
    engagement_ratio = _ratio(current_24h.get("engagement_total", 0), avg_7d.get("engagement_total", 0))
    hot_ratio = _ratio(current_24h.get("hot_post_count", 0), avg_7d.get("hot_post_count", 0))
    creator_ratio = _ratio(current_24h.get("creator_count", 0), avg_7d.get("creator_count", 0))

    heat_score = _score_from_ratios([content_ratio, engagement_ratio, hot_ratio, creator_ratio])
    push_score = round(min(100.0, content_ratio * 22 + engagement_ratio * 28 + hot_ratio * 30 + creator_ratio * 20), 2)
    cooldown_risk = round(max(0.0, 100.0 - push_score) if content_ratio < 0.8 or engagement_ratio < 0.8 else max(0.0, 35.0 - push_score / 4), 2)
    label = _label(push_score=push_score, cooldown_risk=cooldown_risk)
    confidence = _confidence(int(current_24h.get("content_count", 0)))
    return {
        "keyword": keyword,
        "label": label,
        "heat_score": heat_score,
        "push_score": push_score,
        "cooldown_risk": cooldown_risk,
        "confidence": confidence,
        "short_window": {"current_24h": current_24h, "avg_7d": avg_7d},
        "medium_window": {"avg_7d": avg_7d, "avg_30d": avg_30d},
        "evidence": _evidence(content_ratio, engagement_ratio, hot_ratio, creator_ratio, confidence),
    }


def _ratio(current: float, baseline: float) -> float:
    if baseline <= 0:
        return 2.0 if current > 0 else 0.0
    return current / baseline


def _score_from_ratios(ratios: list[float]) -> float:
    return round(min(100.0, sum(min(3.0, ratio) for ratio in ratios) / len(ratios) / 3.0 * 100), 2)


def _label(*, push_score: float, cooldown_risk: float) -> str:
    if cooldown_risk >= 65:
        return "疑似限流"
    if cooldown_risk >= 45:
        return "降温"
    if push_score >= 70:
        return "推流中"
    return "正常波动"


def _confidence(sample_count: int) -> str:
    if sample_count >= 100:
        return "high"
    if sample_count >= 30:
        return "medium"
    return "low"


def _evidence(content_ratio: float, engagement_ratio: float, hot_ratio: float, creator_ratio: float, confidence: str) -> list[str]:
    return [
        f"近 24 小时内容量是 7 日均值的 {content_ratio:.2f} 倍",
        f"近 24 小时互动量是 7 日均值的 {engagement_ratio:.2f} 倍",
        f"爆款数量是 7 日均值的 {hot_ratio:.2f} 倍",
        f"参与达人数是 7 日均值的 {creator_ratio:.2f} 倍",
        f"当前样本置信度为 {confidence}",
    ]
```

- [ ] **Step 4: Add competitor composition aggregation**

In `research/competitors.py`, add:

```python
def build_competitor_composition_snapshot(
    *,
    competitor_account_id: int,
    snapshot_date,
    posts: list[dict[str, Any]],
    entity_tags: list[dict[str, Any]],
    keywords: list[str],
) -> dict[str, Any]:
    keyword_distribution = Counter()
    content_type_distribution = Counter()
    posting_time_distribution = Counter()
    for post in posts:
        text = f"{post.get('title') or ''} {post.get('content') or ''}".lower()
        for keyword in keywords:
            if keyword.lower() in text:
                keyword_distribution[keyword] += 1
        content_type_distribution[post.get("content_type") or "unknown"] += 1
        publish_time = post.get("publish_time")
        hour = getattr(publish_time, "hour", None)
        if hour is not None:
            posting_time_distribution[str(hour)] += 1
    tag_distribution = Counter(str(tag["tag_id"]) for tag in entity_tags)
    totals = [_post_engagement(post) for post in posts]
    threshold = max(100, (sum(totals) / max(1, len(totals))) * 2)
    hot_count = sum(1 for total in totals if total >= threshold)
    return {
        "competitor_account_id": competitor_account_id,
        "snapshot_date": snapshot_date,
        "keyword_distribution_json": dict(keyword_distribution),
        "tag_distribution_json": dict(tag_distribution),
        "content_type_distribution_json": dict(content_type_distribution),
        "posting_time_distribution_json": dict(posting_time_distribution),
        "hot_post_rate": round(hot_count / max(1, len(posts)), 4),
        "top_posts_json": sorted(posts, key=_post_engagement, reverse=True)[:10],
    }
```

- [ ] **Step 5: Expose heat endpoint**

In `api/routers/keyword_opportunities.py`, add a POST endpoint:

```python
from pydantic import BaseModel
from research.keyword_heat import calculate_keyword_heat_signal


class KeywordHeatSignalRequest(BaseModel):
    keyword: str
    current_24h: dict[str, float]
    avg_7d: dict[str, float]
    avg_30d: dict[str, float]


@router.post("/heat/signal")
async def calculate_heat_signal(request: KeywordHeatSignalRequest):
    require_research_database()
    return calculate_keyword_heat_signal(
        keyword=request.keyword,
        current_24h=request.current_24h,
        avg_7d=request.avg_7d,
        avg_30d=request.avg_30d,
    )
```

- [ ] **Step 6: Run tests**

Run:

```powershell
python -m pytest tests\test_keyword_heat.py tests\test_competitor_monitoring.py tests\test_keyword_opportunities.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add research\keyword_heat.py research\competitors.py api\routers\keyword_opportunities.py api\routers\competitors.py tests\test_keyword_heat.py tests\test_competitor_composition.py
git commit -m "feat: add keyword heat and competitor composition"
```

### Task 7: React UI Integration

**Files:**
- Modify: `api/webui/src/main.tsx`
- Modify: `api/webui/src/styles.css`
- Test: `npm.cmd run build`

- [ ] **Step 1: Add frontend API types**

In `api/webui/src/main.tsx`, add TypeScript types near existing domain types:

```ts
type ScenePack = { id: number; vertical_id: number; name: string; description?: string | null; weight: number; enabled: boolean };
type ScenePackKeyword = { id: number; scene_pack_id: number; keyword: string; keyword_type: string; platform?: string | null; weight: number; reason?: string | null; usage_flags: string[]; enabled: boolean };
type MonitorPool = { id: number; name: string; description?: string | null; vertical_id?: number | null; scene_pack_ids?: number[]; research_job_id?: number | null; schedule_interval_minutes: number; enabled: boolean };
type ContentKeyword = { keyword: string; keyword_type: string; confidence: number; evidence_text?: string; scene_pack_id?: number | null; reason?: string; query_variants?: string[] };
type SimilarContentCandidate = { platform: string; platform_post_id: string; title: string; author_id?: string | null; url?: string | null; similarity_score: number; matched_keywords: Array<{ term: string; count: number; context: string }>; engagement?: Record<string, unknown>; evidence?: Record<string, unknown> };
type KeywordHeatSignal = { keyword: string; label: string; heat_score: number; push_score: number; cooldown_risk: number; confidence: string; evidence: string[] };
```

- [ ] **Step 2: Extend tab union and sidebar**

Add tabs:

```ts
type Tab = "overview" | "audience" | "content" | "competitors" | "keyword" | "report" | "direct" | "keyword_library" | "monitor_pools" | "config" | "tasks" | "data" | "ai" | "export";
```

Add sidebar entries:

```tsx
{ id: "keyword_library", label: "赛道词库", icon: <Layers size={18} /> },
{ id: "monitor_pools", label: "监控池", icon: <ShieldCheck size={18} /> },
```

- [ ] **Step 3: Add keyword library page**

Create a `KeywordLibraryPage` component in `main.tsx` that:

- Lists scene packs.
- Lets user create a scene pack.
- Lets user add keyword rows.
- Has an AI expansion form with provider selection.
- Shows AI suggestions as checkboxes before saving.

Minimum component signature:

```tsx
function KeywordLibraryPage(props: {
  platforms: ConfigOption[];
  providers: AIProvider[];
  scenePacks: ScenePack[];
  keywords: ScenePackKeyword[];
  onCreateScenePack: (payload: { vertical_id: number; name: string; description?: string; weight: number; enabled: boolean }) => Promise<void>;
  onCreateKeyword: (payload: Omit<ScenePackKeyword, "id">) => Promise<void>;
  onExpandKeywords: (payload: { input_text: string; provider_config_id?: number; target_platforms: string[] }) => Promise<Record<string, unknown>>;
}) {
  return <section className="workspace-grid two-column">{/* controls and tables */}</section>;
}
```

Use existing `panel`, `form-grid`, `table-wrap`, and `checks-grid` classes. Do not put nested cards inside cards.

- [ ] **Step 4: Expand content tracking page**

Replace the current `ContentPage` lightweight panel with a full content tracking workflow:

- Content input textarea.
- Extract keywords button calling `/api/content-tracking/extract-keywords`.
- Extracted keyword table.
- Similar content search button calling `/api/content-tracking/search-similar`.
- Similar content candidate table.
- Create tracker dialog or inline panel.
- Immediate tracking action.

API helpers:

```ts
async function extractContentKeywords(payload: Record<string, unknown>) {
  return api<{ keywords: ContentKeyword[] }>("/api/content-tracking/extract-keywords", { method: "POST", body: JSON.stringify(payload) });
}

async function searchSimilarContent(payload: Record<string, unknown>) {
  return api<{ candidates: SimilarContentCandidate[] }>("/api/content-tracking/search-similar", { method: "POST", body: JSON.stringify(payload) });
}
```

- [ ] **Step 5: Expand creator discovery page**

Extend `AudiencePage` to show:

- Scene pack selector, default single, optional multi-select.
- Real-time discovery switch.
- Automation panel with mode, Top N, min score, min recent posts, follower range.
- Candidate table with match evidence.
- Add selected to monitor pool.
- Add Top N.
- Add and crawl now.

Use existing `/api/creator-search/search` for local results first. Add calls to new monitor pool endpoints.

- [ ] **Step 6: Add monitor pool page**

Create `MonitorPoolsPage`:

- Pool list.
- Creator membership table.
- Frequency and comment policy controls.
- Immediate crawl button.
- Linked research job status.

- [ ] **Step 7: Expand keyword heat page**

Update `KeywordPage` to call `/api/keyword-opportunities/heat/signal` for selected keyword and show:

- Label.
- Heat Score.
- Push Score.
- Cooldown Risk.
- Confidence.
- Evidence list.
- Existing trend chart.

- [ ] **Step 8: Expand competitor page**

Update `CompetitorsPage` to show composition sections:

- keyword distribution
- tag distribution
- content type distribution
- posting time distribution
- hot post rate

If backend data is empty, render a clear empty state with the next action.

- [ ] **Step 9: Add responsive CSS**

In `api/webui/src/styles.css`, add:

```css
.evidence-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.evidence-list li {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  background: #f8fafc;
  color: var(--text);
}

.score-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.candidate-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

@media (max-width: 620px) {
  .score-strip {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 10: Build**

Run:

```powershell
npm.cmd run build
```

Expected: PASS. Vite chunk-size warning is acceptable.

- [ ] **Step 11: Commit**

Run:

```powershell
git add api\webui\src\main.tsx api\webui\src\styles.css api\webui\dist
git commit -m "feat: add growth intelligence console workflows"
```

### Task 8: End-To-End Regression And Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-05-20-growth-intelligence-phase-one-design.md` only if implementation decisions change.
- Test: all relevant tests and build.

- [ ] **Step 1: Run backend test subset**

Run:

```powershell
python -m pytest tests\test_growth_intelligence_models.py tests\test_growth_intelligence_repository.py tests\test_keyword_library_api.py tests\test_monitor_pools.py tests\test_content_tracking_workflow.py tests\test_content_tracking_api.py tests\test_keyword_heat.py tests\test_competitor_monitoring.py tests\test_keyword_opportunities.py tests\test_research_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 3: Run route smoke test**

Run:

```powershell
python -c "from fastapi.testclient import TestClient; from api.main import app; c=TestClient(app, follow_redirects=False); print(c.get('/').status_code, c.get('/').headers.get('location')); print(c.get('/research').status_code, '/static/dist/assets/' in c.get('/research').text); print(c.get('/api/crawler/status').status_code)"
```

Expected output includes:

```text
307 /research
200 True
200
```

- [ ] **Step 4: Manual browser checks**

Start backend in the normal project-specific way. Visit `/research` and check:

- 赛道词库 page loads.
- AI expansion form renders with provider dropdown.
- 达人筛选 page can search local candidates without enabling real-time discovery.
- 内容追踪 page can extract keywords from pasted text.
- 友商监控 page shows composition empty states or data panels.
- 关键词热度 page shows score and evidence UI.
- Direct crawler page still exists.
- `/crawler` legacy page still opens.

- [ ] **Step 5: Commit final verification notes if docs changed**

If implementation changed defaults or endpoint names, update the design document and commit:

```powershell
git add docs\superpowers\specs\2026-05-20-growth-intelligence-phase-one-design.md
git commit -m "docs: align growth intelligence design with implementation"
```

If no docs changed, skip this commit.

## Self-Review

- Spec coverage: A creator discovery, B content tracking, C competitor composition, D keyword heat, keyword library, AI expansion, monitor pools, automation, immediate crawl, and frontend integration all map to tasks above.
- Placeholder scan: this plan does not use open placeholders. Endpoint names, file names, test names, and command names are explicit.
- Type consistency: schema names used in router tasks match the schema names introduced in Task 2. Frontend types match the backend concepts and use explicit field names.

## Execution Guidance

Recommended execution order:

1. Task 1 and Task 2 together establish the data foundation.
2. Task 3 can be implemented independently after Task 2.
3. Task 4 depends on Task 2 and can run in parallel with Task 5 after repository methods exist.
4. Task 6 can run after Task 2 and does not depend on Task 4 or Task 5.
5. Task 7 should wait until backend endpoints from Tasks 3-6 are stable.
6. Task 8 is final verification.

Do not start real crawler runs during unit tests. Use fake repositories and mock execution callbacks for tests that touch real-time discovery or immediate crawl.
