# General Growth Intelligence Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the generic growth intelligence platform described in `docs/superpowers/specs/2026-05-20-general-growth-intelligence-platform-design.md`, with configurable verticals, scene packs, real TikHub collection, automatic research backfill, unified account profiles, creator discovery, content tracking, keyword heat, competitor snapshots, and boss-ready reports.

**Architecture:** Extend the existing research module instead of creating a parallel stack. Platform crawlers write platform tables, a new postprocess pipeline backfills normalized research tables, updates unified account profiles, scores business entities, and refreshes report-ready snapshots. React pages consume the same `/api/research/*`, `/api/creator-search/*`, `/api/content-tracking/*`, `/api/keyword-*`, `/api/competitors/*`, and `/api/reports/*` APIs.

**Tech Stack:** FastAPI, SQLAlchemy async sessions, existing SQLite/Postgres-compatible models, TikHub API, 4Router/OpenAI-compatible AI providers, Vite + React + TypeScript, Recharts, pytest.

---

## Scope Check

The design spans multiple subsystems. This plan keeps them in one ordered implementation because each task produces a testable vertical slice and the later boss report depends on all earlier slices. Do not start the frontend report work before the backend postprocess and account profile tasks pass their tests.

## File Structure

### Backend files

- Modify `media_platform/tikhub/endpoints.py`: keep TikHub endpoint specs current, including Douyin Search V1 POST JSON behavior.
- Modify `media_platform/tikhub/core.py`: support endpoint-level JSON body requests and emit collection completion metadata.
- Modify `research/models.py`: add AI keyword suggestion review fields if missing, add unified account profile tables if current creator profile tables are insufficient, add postprocess run tracking.
- Modify `research/repository.py`: add repository methods for global defaults, suggestions, account profiles, account roles, postprocess runs, creator scores, heat snapshots, competitor composition snapshots, and report reads.
- Create `research/postprocess_pipeline.py`: orchestrate platform backfill, account extraction, rule tagging, creator scoring, heat rebuild hooks, competitor snapshot hooks, and event logging.
- Create `research/account_profiles.py`: upsert unified account profiles and role assignments from normalized posts and creators.
- Create `research/creator_scoring.py`: compute creator candidate score, labels, and evidence from scene packs and research posts.
- Modify `research/keyword_library.py`: add AI suggestion queue approval and rejection flow.
- Modify `research/keyword_heat.py`: produce rule result, AI result slot, conflict flag, and evidence.
- Modify `research/competitors.py`: generate composition snapshots from account role and research posts.
- Modify `research/reporting.py`: generate vertical and scene-pack reports from real snapshots.
- Modify `api/routers/research.py`: expose postprocess and wait-refresh endpoints, trigger postprocess after execution when requested.
- Modify `api/routers/keyword_library.py`: expose AI suggestion queue review endpoints.
- Create `api/routers/accounts.py`: unified account profile APIs.
- Modify `api/routers/creator_search.py`: return score evidence and use account roles for monitor pool membership.
- Modify `api/routers/content_tracking.py`: use postprocess-backed research posts for similar content and snapshots.
- Modify `api/routers/keyword_opportunities.py`: return dual-track heat judgments.
- Modify `api/routers/competitors.py`: return composition snapshots and account role state.
- Modify `api/routers/reports.py`: return boss report payloads for vertical and scene-pack views.
- Modify `api/main.py`: include `accounts` router.

### Frontend files

- Modify `api/webui/src/main.tsx`: wire new API calls and page states.
- Modify `api/webui/src/styles.css`: add layouts for review queue, account profile chips, score evidence, heat dual-track panels, report cards.
- Prefer extracting new frontend modules if `main.tsx` becomes hard to read:
  - Create `api/webui/src/types.ts`
  - Create `api/webui/src/api.ts`
  - Create `api/webui/src/pages/KeywordLibraryPage.tsx`
  - Create `api/webui/src/pages/AudiencePage.tsx`
  - Create `api/webui/src/pages/ReportPage.tsx`

### Test files

- Modify `tests/test_tikhub_endpoints.py`
- Modify `tests/test_tikhub_crawler_flow.py`
- Create `tests/test_postprocess_pipeline.py`
- Create `tests/test_account_profiles.py`
- Modify `tests/test_keyword_library_api.py`
- Modify `tests/test_creator_discovery_scoring.py`
- Create `tests/test_keyword_heat_dual_track.py`
- Modify `tests/test_competitor_composition.py`
- Modify `tests/test_reports_api.py`
- Add focused frontend build verification through `npm.cmd run build`.

---

### Task 1: Stabilize TikHub Collection and Automatic Postprocess Trigger

**Files:**
- Modify: `media_platform/tikhub/endpoints.py`
- Modify: `media_platform/tikhub/core.py`
- Modify: `api/routers/research.py`
- Create: `research/postprocess_pipeline.py`
- Test: `tests/test_tikhub_endpoints.py`
- Test: `tests/test_postprocess_pipeline.py`

- [ ] **Step 1: Write endpoint tests for Douyin Search V1**

Add to `tests/test_tikhub_endpoints.py`:

```python
def test_douyin_search_uses_json_post_endpoint():
    endpoint = get_endpoint("dy", Capability.SEARCH)

    assert endpoint.method == "POST"
    assert endpoint.path == "/api/v1/douyin/search/fetch_general_search_v1"
    assert endpoint.json_body is True
    assert endpoint.default_params == {
        "cursor": 0,
        "sort_type": "0",
        "publish_time": "0",
        "filter_duration": "0",
        "content_type": "0",
        "search_id": "",
        "backtrace": "",
    }
```

- [ ] **Step 2: Run endpoint test and verify current behavior**

Run:

```powershell
python -m pytest tests\test_tikhub_endpoints.py::test_douyin_search_uses_json_post_endpoint -q
```

Expected: PASS if the previous TikHub fix is present, FAIL if the repo has not received that fix yet.

- [ ] **Step 3: Ensure endpoint spec supports JSON body**

In `media_platform/tikhub/endpoints.py`, ensure `EndpointSpec` includes:

```python
json_body: bool = False
```

Ensure Douyin search spec is:

```python
Capability.SEARCH: EndpointSpec(
    "POST",
    "/api/v1/douyin/search/fetch_general_search_v1",
    keyword_param="keyword",
    cursor_param="cursor",
    page_param="",
    default_params={
        "cursor": 0,
        "sort_type": "0",
        "publish_time": "0",
        "filter_duration": "0",
        "content_type": "0",
        "search_id": "",
        "backtrace": "",
    },
    json_body=True,
),
```

- [ ] **Step 4: Ensure TikHub crawler sends JSON for JSON endpoints**

In `media_platform/tikhub/core.py`, the search request must use:

```python
data = await self.client.request(
    endpoint.method,
    endpoint.path,
    json=params if endpoint.json_body else None,
    params=None if endpoint.json_body else params,
)
```

And `_search_params` must not write an empty page parameter:

```python
if endpoint.cursor_param and cursor:
    params[endpoint.cursor_param] = cursor
elif endpoint.cursor_param:
    params.setdefault(endpoint.cursor_param, 0)
elif endpoint.page_param:
    params[endpoint.page_param] = page
```

- [ ] **Step 5: Add postprocess pipeline skeleton**

Create `research/postprocess_pipeline.py`:

```python
from dataclasses import dataclass
from typing import Any

from research.backfill import ExistingPlatformBackfill
from research.repository import ResearchRepository


@dataclass(frozen=True)
class PostprocessResult:
    job_id: int
    backfill: dict[str, dict[str, int]]
    account_profiles: dict[str, int]
    creator_candidates: dict[str, int]
    heat_snapshots: dict[str, int]
    competitor_snapshots: dict[str, int]


class ResearchPostprocessPipeline:
    def __init__(self, repository: ResearchRepository, *, author_hash_salt: str):
        self.repository = repository
        self.backfill = ExistingPlatformBackfill(
            repository, author_hash_salt=author_hash_salt
        )

    async def run_for_job(
        self,
        job_id: int,
        *,
        platforms: list[str],
        keywords: list[str] | None = None,
        limit: int | None = 1000,
    ) -> PostprocessResult:
        backfill_result: dict[str, dict[str, int]] = {}
        for platform in platforms:
            backfill_result[platform] = await self.backfill.backfill_platform(
                platform,
                job_id=job_id,
                keywords=keywords,
                limit=limit,
            )
        return PostprocessResult(
            job_id=job_id,
            backfill=backfill_result,
            account_profiles={},
            creator_candidates={},
            heat_snapshots={},
            competitor_snapshots={},
        )

    @staticmethod
    def to_dict(result: PostprocessResult) -> dict[str, Any]:
        return {
            "job_id": result.job_id,
            "backfill": result.backfill,
            "account_profiles": result.account_profiles,
            "creator_candidates": result.creator_candidates,
            "heat_snapshots": result.heat_snapshots,
            "competitor_snapshots": result.competitor_snapshots,
        }
```

- [ ] **Step 6: Add postprocess test with fake backfill**

Create `tests/test_postprocess_pipeline.py`:

```python
import pytest

from research.postprocess_pipeline import ResearchPostprocessPipeline


class FakeBackfill:
    def __init__(self):
        self.calls = []

    async def backfill_platform(self, platform, *, job_id, keywords=None, limit=1000):
        self.calls.append((platform, job_id, keywords, limit))
        return {"posts": 2, "comments": 0, "authors": 1, "raw_records": 2}


@pytest.mark.asyncio
async def test_postprocess_runs_backfill_for_each_platform():
    pipeline = ResearchPostprocessPipeline.__new__(ResearchPostprocessPipeline)
    pipeline.repository = object()
    pipeline.backfill = FakeBackfill()

    result = await pipeline.run_for_job(
        7, platforms=["xhs", "dy"], keywords=["K12教育"], limit=50
    )

    assert result.job_id == 7
    assert result.backfill["xhs"]["posts"] == 2
    assert result.backfill["dy"]["authors"] == 1
    assert pipeline.backfill.calls == [
        ("xhs", 7, ["K12教育"], 50),
        ("dy", 7, ["K12教育"], 50),
    ]
```

- [ ] **Step 7: Expose postprocess endpoint**

In `api/routers/research.py`, add:

```python
@router.post("/jobs/{job_id}/postprocess")
async def postprocess_research_job(job_id: int):
    salt = os.getenv("RESEARCH_AUTHOR_HASH_SALT") or "local-dev-salt"
    require_research_database()
    repository = ResearchRepository()
    job = await repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")
    pipeline = ResearchPostprocessPipeline(repository, author_hash_salt=salt)
    result = await pipeline.run_for_job(
        job_id,
        platforms=job["platforms"],
        keywords=job.get("keywords") or None,
    )
    return ResearchPostprocessPipeline.to_dict(result)
```

Import `ResearchPostprocessPipeline`.

- [ ] **Step 8: Run tests**

Run:

```powershell
python -m pytest tests\test_tikhub_endpoints.py tests\test_postprocess_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add media_platform/tikhub/endpoints.py media_platform/tikhub/core.py research/postprocess_pipeline.py api/routers/research.py tests/test_tikhub_endpoints.py tests/test_postprocess_pipeline.py
git commit -m "feat: add research postprocess pipeline"
```

---

### Task 2: Add AI Keyword Suggestion Review Queue

**Files:**
- Modify: `research/models.py`
- Modify: `research/repository.py`
- Modify: `research/keyword_library.py`
- Modify: `api/routers/keyword_library.py`
- Test: `tests/test_keyword_library_api.py`

- [ ] **Step 1: Write repository test for suggestion lifecycle**

Add to `tests/test_keyword_library_api.py`:

```python
@pytest.mark.asyncio
async def test_ai_keyword_suggestion_requires_approval(client, research_db):
    create_pack = await client.post(
        "/api/keyword-library/scene-packs",
        json={
            "vertical_id": 1,
            "name": "K12 education",
            "description": "education test pack",
            "audience": "parents",
            "scenario": "homework",
            "business_goal": "creator discovery",
            "platforms": ["xhs", "dy"],
            "match_mode": "single",
            "primary_required": True,
            "enabled": True,
        },
    )
    assert create_pack.status_code in (200, 201)

    response = await client.post(
        "/api/keyword-library/ai/suggestions",
        json={
            "vertical_id": 1,
            "scene_pack_id": create_pack.json()["id"],
            "input_text": "K12教育",
            "suggestion_type": "new_keyword",
            "suggested_payload": {
                "keyword": "单亲妈妈陪读",
                "keyword_type": "secondary",
                "weight": 0.8,
                "usage_flags": ["creator_discovery"],
            },
            "confidence": 0.91,
            "reason": "Matches parent audience and education scenario",
        },
    )

    assert response.status_code in (200, 201)
    assert response.json()["status"] == "pending"

    keywords = await client.get("/api/keyword-library/keywords")
    assert "单亲妈妈陪读" not in {
        item["keyword"] for item in keywords.json()["keywords"]
    }

    approve = await client.post(
        f"/api/keyword-library/ai/suggestions/{response.json()['id']}/approve"
    )

    assert approve.status_code == 200
    keywords = await client.get("/api/keyword-library/keywords")
    assert "单亲妈妈陪读" in {
        item["keyword"] for item in keywords.json()["keywords"]
    }
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```powershell
python -m pytest tests\test_keyword_library_api.py::test_ai_keyword_suggestion_requires_approval -q
```

Expected: FAIL because suggestion endpoints or repository methods are missing.

- [ ] **Step 3: Add repository methods**

In `research/repository.py`, add methods:

```python
async def create_ai_keyword_suggestion(self, payload: dict[str, Any]) -> dict[str, Any]:
    async with get_session() as session:
        item = ResearchAIKeywordSuggestionSession(
            vertical_id=payload.get("vertical_id"),
            scene_pack_id=payload.get("scene_pack_id"),
            input_text=payload["input_text"],
            seed_keywords_json=[],
            suggestions_json=[payload["suggested_payload"]],
            selected_keywords_json=[],
            status="pending",
            provider_config_id=payload.get("provider_config_id"),
            metadata_json={
                "suggestion_type": payload["suggestion_type"],
                "confidence": payload.get("confidence", 0),
                "reason": payload.get("reason", ""),
            },
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return self._ai_keyword_suggestion_session_to_dict(item)

async def approve_ai_keyword_suggestion(self, suggestion_id: int) -> dict[str, Any]:
    async with get_session() as session:
        item = await session.get(ResearchAIKeywordSuggestionSession, suggestion_id)
        if item is None:
            raise KeyError(suggestion_id)
        suggestion = (item.suggestions_json or [])[0]
        keyword_payload = {
            "scene_pack_id": item.scene_pack_id,
            "keyword": suggestion["keyword"],
            "keyword_type": suggestion.get("keyword_type", "secondary"),
            "platform": suggestion.get("platform"),
            "weight": suggestion.get("weight", 1.0),
            "reason": suggestion.get("reason") or (item.metadata_json or {}).get("reason"),
            "usage_flags": suggestion.get("usage_flags") or ["creator_discovery"],
            "enabled": True,
        }
        keyword = ResearchScenePackKeyword(**keyword_payload)
        session.add(keyword)
        item.status = "approved"
        item.selected_keywords_json = [suggestion]
        await session.commit()
        await session.refresh(item)
        return self._ai_keyword_suggestion_session_to_dict(item)

async def reject_ai_keyword_suggestion(self, suggestion_id: int) -> dict[str, Any]:
    async with get_session() as session:
        item = await session.get(ResearchAIKeywordSuggestionSession, suggestion_id)
        if item is None:
            raise KeyError(suggestion_id)
        item.status = "rejected"
        await session.commit()
        await session.refresh(item)
        return self._ai_keyword_suggestion_session_to_dict(item)
```

Adjust field names to match the existing `ResearchAIKeywordSuggestionSession` model if they already differ.

- [ ] **Step 4: Add API routes**

In `api/routers/keyword_library.py`, add:

```python
@router.post("/ai/suggestions")
async def create_ai_keyword_suggestion(payload: dict[str, Any]):
    return await ResearchRepository().create_ai_keyword_suggestion(payload)


@router.get("/ai/suggestions")
async def list_ai_keyword_suggestions(status: str | None = None):
    return {
        "suggestions": await ResearchRepository().list_ai_keyword_suggestion_sessions(
            status=status
        )
    }


@router.post("/ai/suggestions/{suggestion_id}/approve")
async def approve_ai_keyword_suggestion(suggestion_id: int):
    try:
        return await ResearchRepository().approve_ai_keyword_suggestion(suggestion_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="AI keyword suggestion not found")


@router.post("/ai/suggestions/{suggestion_id}/reject")
async def reject_ai_keyword_suggestion(suggestion_id: int):
    try:
        return await ResearchRepository().reject_ai_keyword_suggestion(suggestion_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="AI keyword suggestion not found")
```

- [ ] **Step 5: Run lifecycle test**

Run:

```powershell
python -m pytest tests\test_keyword_library_api.py::test_ai_keyword_suggestion_requires_approval -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add research/repository.py api/routers/keyword_library.py tests/test_keyword_library_api.py
git commit -m "feat: add keyword suggestion review queue"
```

---

### Task 3: Build Unified Account Profiles and Roles

**Files:**
- Modify: `research/models.py`
- Modify: `research/repository.py`
- Create: `research/account_profiles.py`
- Create: `api/routers/accounts.py`
- Modify: `api/main.py`
- Test: `tests/test_account_profiles.py`

- [ ] **Step 1: Write account profile test**

Create `tests/test_account_profiles.py`:

```python
import pytest

from research.account_profiles import AccountProfileService


class FakeRepository:
    def __init__(self):
        self.profiles = {}
        self.roles = []

    async def upsert_account_profile(self, payload):
        key = (payload["platform"], payload["account_id"])
        self.profiles[key] = {**payload, "id": len(self.profiles) + 1}
        return self.profiles[key]

    async def upsert_account_role(self, payload):
        self.roles.append(payload)
        return {**payload, "id": len(self.roles)}


@pytest.mark.asyncio
async def test_account_profile_reuses_same_account_for_roles():
    repo = FakeRepository()
    service = AccountProfileService(repo)

    profile = await service.upsert_from_post_author(
        {
            "platform": "xhs",
            "author_id": "u1",
            "display_name": "Teacher A",
            "bio": "K12 education creator",
        },
        vertical_id=1,
        scene_pack_id=2,
        role="candidate_creator",
    )
    competitor = await service.upsert_from_post_author(
        {
            "platform": "xhs",
            "author_id": "u1",
            "display_name": "Teacher A",
            "bio": "K12 education creator",
        },
        vertical_id=1,
        scene_pack_id=2,
        role="competitor",
    )

    assert profile["id"] == competitor["id"]
    assert len(repo.profiles) == 1
    assert [item["role"] for item in repo.roles] == [
        "candidate_creator",
        "competitor",
    ]
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests\test_account_profiles.py -q
```

Expected: FAIL because `research.account_profiles` is missing.

- [ ] **Step 3: Add service**

Create `research/account_profiles.py`:

```python
from typing import Protocol, Any


class AccountProfileRepository(Protocol):
    async def upsert_account_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def upsert_account_role(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class AccountProfileService:
    def __init__(self, repository: AccountProfileRepository):
        self.repository = repository

    async def upsert_from_post_author(
        self,
        author: dict[str, Any],
        *,
        vertical_id: int | None,
        scene_pack_id: int | None,
        role: str,
        monitor_pool_id: int | None = None,
    ) -> dict[str, Any]:
        account_id = str(author.get("author_id") or author.get("user_id") or author["account_id"])
        profile = await self.repository.upsert_account_profile(
            {
                "platform": author["platform"],
                "account_id": account_id,
                "sec_account_id": author.get("sec_account_id"),
                "display_name": author.get("display_name") or author.get("nickname"),
                "avatar_url": author.get("avatar_url") or author.get("avatar"),
                "profile_url": author.get("profile_url"),
                "bio": author.get("bio") or author.get("signature"),
                "verified": bool(author.get("verified", False)),
                "region": author.get("region"),
                "follower_count": author.get("follower_count"),
                "following_count": author.get("following_count"),
                "post_count": author.get("post_count"),
                "tag_summary_json": author.get("tag_summary") or {},
            }
        )
        await self.repository.upsert_account_role(
            {
                "account_profile_id": profile["id"],
                "role": role,
                "vertical_id": vertical_id,
                "scene_pack_id": scene_pack_id,
                "monitor_pool_id": monitor_pool_id,
                "source": author.get("source", "postprocess"),
                "status": "active",
            }
        )
        return profile
```

- [ ] **Step 4: Add SQLAlchemy models if missing**

In `research/models.py`, add if no equivalent tables exist:

```python
class ResearchAccountProfile(Base):
    __tablename__ = "research_account_profiles"
    __table_args__ = (
        UniqueConstraint("platform", "account_id", name="uq_research_account_profile"),
    )

    id = Column(Integer, primary_key=True)
    platform = Column(String(32), nullable=False, index=True)
    account_id = Column(String(255), nullable=False, index=True)
    sec_account_id = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=True)
    avatar_url = Column(Text, nullable=True)
    profile_url = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)
    verified = Column(Boolean, nullable=False, default=False)
    region = Column(String(128), nullable=True)
    follower_count = Column(Integer, nullable=True)
    following_count = Column(Integer, nullable=True)
    post_count = Column(Integer, nullable=True)
    avg_engagement_rate = Column(Float, nullable=True)
    hot_post_rate = Column(Float, nullable=True)
    recent_post_count_30d = Column(Integer, nullable=True)
    latest_post_time = Column(DateTime(timezone=True), nullable=True)
    contact_clues = Column(json_column(), nullable=False, default=list)
    tag_summary_json = Column(json_column(), nullable=False, default=dict)
    last_crawled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ResearchAccountRole(Base):
    __tablename__ = "research_account_roles"
    __table_args__ = (
        UniqueConstraint(
            "account_profile_id",
            "role",
            "vertical_id",
            "scene_pack_id",
            "monitor_pool_id",
            name="uq_research_account_role_scope",
        ),
    )

    id = Column(Integer, primary_key=True)
    account_profile_id = Column(Integer, ForeignKey("research_account_profiles.id"), nullable=False, index=True)
    role = Column(String(64), nullable=False, index=True)
    vertical_id = Column(Integer, nullable=True, index=True)
    scene_pack_id = Column(Integer, nullable=True, index=True)
    monitor_pool_id = Column(Integer, nullable=True, index=True)
    source = Column(String(64), nullable=False, default="manual")
    status = Column(String(32), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 5: Add repository methods**

Add to `research/repository.py`:

```python
async def upsert_account_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
    async with get_session() as session:
        stmt = select(ResearchAccountProfile).where(
            ResearchAccountProfile.platform == payload["platform"],
            ResearchAccountProfile.account_id == payload["account_id"],
        )
        item = (await session.execute(stmt)).scalar_one_or_none()
        if item is None:
            item = ResearchAccountProfile(**payload)
            session.add(item)
        else:
            for key, value in payload.items():
                if value not in (None, "", [], {}):
                    setattr(item, key, value)
        await session.commit()
        await session.refresh(item)
        return self._account_profile_to_dict(item)

async def upsert_account_role(self, payload: dict[str, Any]) -> dict[str, Any]:
    async with get_session() as session:
        stmt = select(ResearchAccountRole).where(
            ResearchAccountRole.account_profile_id == payload["account_profile_id"],
            ResearchAccountRole.role == payload["role"],
            ResearchAccountRole.vertical_id == payload.get("vertical_id"),
            ResearchAccountRole.scene_pack_id == payload.get("scene_pack_id"),
            ResearchAccountRole.monitor_pool_id == payload.get("monitor_pool_id"),
        )
        item = (await session.execute(stmt)).scalar_one_or_none()
        if item is None:
            item = ResearchAccountRole(**payload)
            session.add(item)
        else:
            item.status = payload.get("status", item.status)
            item.source = payload.get("source", item.source)
        await session.commit()
        await session.refresh(item)
        return self._account_role_to_dict(item)
```

Add `_account_profile_to_dict` and `_account_role_to_dict` beside existing serializer methods.

- [ ] **Step 6: Add accounts router**

Create `api/routers/accounts.py`:

```python
from fastapi import APIRouter

from research.repository import ResearchRepository

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("/profiles")
async def list_account_profiles(
    platform: str | None = None,
    role: str | None = None,
    vertical_id: int | None = None,
    scene_pack_id: int | None = None,
):
    return {
        "profiles": await ResearchRepository().list_account_profiles(
            platform=platform,
            role=role,
            vertical_id=vertical_id,
            scene_pack_id=scene_pack_id,
        )
    }


@router.post("/profiles/{profile_id}/roles")
async def add_account_role(profile_id: int, payload: dict):
    payload["account_profile_id"] = profile_id
    return await ResearchRepository().upsert_account_role(payload)
```

Include it in `api/main.py` with:

```python
from api.routers import accounts
app.include_router(accounts.router)
```

- [ ] **Step 7: Run account tests**

Run:

```powershell
python -m pytest tests\test_account_profiles.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add research/models.py research/repository.py research/account_profiles.py api/routers/accounts.py api/main.py tests/test_account_profiles.py
git commit -m "feat: add unified account profiles"
```

---

### Task 4: Extend Postprocess Pipeline to Update Account Profiles

**Files:**
- Modify: `research/postprocess_pipeline.py`
- Modify: `research/account_profiles.py`
- Modify: `research/repository.py`
- Test: `tests/test_postprocess_pipeline.py`

- [ ] **Step 1: Write postprocess account extraction test**

Add to `tests/test_postprocess_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_postprocess_updates_account_profiles_from_posts():
    class Repo:
        async def list_posts(self, job_id, limit=None):
            return [
                {
                    "platform": "xhs",
                    "author_hash": "hash-1",
                    "engagement_json": {
                        "author_id": "u1",
                        "nickname": "Creator One",
                        "source_keyword": "K12教育",
                    },
                }
            ]

        async def upsert_account_profile(self, payload):
            return {**payload, "id": 1}

        async def upsert_account_role(self, payload):
            return {**payload, "id": 1}

    pipeline = ResearchPostprocessPipeline.__new__(ResearchPostprocessPipeline)
    pipeline.repository = Repo()
    pipeline.backfill = FakeBackfill()

    result = await pipeline.run_for_job(
        7,
        platforms=["xhs"],
        keywords=["K12教育"],
        limit=50,
        vertical_id=1,
        scene_pack_ids=[2],
    )

    assert result.account_profiles["upserted"] == 1
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests\test_postprocess_pipeline.py::test_postprocess_updates_account_profiles_from_posts -q
```

Expected: FAIL because `run_for_job` does not accept vertical and scene-pack arguments yet.

- [ ] **Step 3: Add account extraction to pipeline**

In `research/postprocess_pipeline.py`, update `run_for_job` signature:

```python
async def run_for_job(
    self,
    job_id: int,
    *,
    platforms: list[str],
    keywords: list[str] | None = None,
    limit: int | None = 1000,
    vertical_id: int | None = None,
    scene_pack_ids: list[int] | None = None,
) -> PostprocessResult:
```

After backfill loop, add:

```python
account_stats = await self._update_account_profiles(
    job_id=job_id,
    vertical_id=vertical_id,
    scene_pack_ids=scene_pack_ids or [],
)
```

Return `account_profiles=account_stats`.

Add helper:

```python
async def _update_account_profiles(
    self,
    *,
    job_id: int,
    vertical_id: int | None,
    scene_pack_ids: list[int],
) -> dict[str, int]:
    from research.account_profiles import AccountProfileService

    service = AccountProfileService(self.repository)
    posts = await self.repository.list_posts(job_id, limit=5000)
    upserted = 0
    for post in posts:
        engagement = post.get("engagement_json") or {}
        author_id = engagement.get("author_id") or engagement.get("user_id")
        if not author_id:
            continue
        for scene_pack_id in scene_pack_ids or [None]:
            await service.upsert_from_post_author(
                {
                    "platform": post["platform"],
                    "author_id": str(author_id),
                    "display_name": engagement.get("nickname"),
                    "bio": engagement.get("signature"),
                    "source": "postprocess",
                },
                vertical_id=vertical_id,
                scene_pack_id=scene_pack_id,
                role="candidate_creator",
            )
            upserted += 1
    return {"upserted": upserted}
```

- [ ] **Step 4: Ensure normalizers preserve author evidence**

In `research/normalizer.py`, update XHS and Douyin `engagement_json` to include author fields when present:

```python
"author_id": item.get("user_id"),
"nickname": item.get("nickname"),
"signature": item.get("user_signature") or item.get("desc"),
```

For XHS:

```python
"author_id": item.get("user_id"),
"nickname": item.get("nickname"),
```

- [ ] **Step 5: Run postprocess tests**

Run:

```powershell
python -m pytest tests\test_postprocess_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add research/postprocess_pipeline.py research/normalizer.py tests/test_postprocess_pipeline.py
git commit -m "feat: update account profiles during postprocess"
```

---

### Task 5: Creator Scoring With Tags, Score, and Evidence

**Files:**
- Create: `research/creator_scoring.py`
- Modify: `research/repository.py`
- Modify: `api/routers/creator_search.py`
- Test: `tests/test_creator_discovery_scoring.py`

- [ ] **Step 1: Write scoring test**

Add to `tests/test_creator_discovery_scoring.py`:

```python
from research.creator_scoring import score_creator_candidate


def test_score_creator_requires_primary_and_explains_evidence():
    profile = {
        "platform": "xhs",
        "account_id": "u1",
        "display_name": "K12 Mom",
        "recent_post_count_30d": 5,
        "avg_engagement_rate": 0.08,
    }
    posts = [
        {
            "platform_post_id": "p1",
            "title": "K12教育陪读经验",
            "content": "单亲妈妈如何做作业辅导",
            "engagement_json": {"liked_count": 100, "comment_count": 20},
            "url": "https://example.test/p1",
        }
    ]
    keywords = [
        {"keyword": "K12教育", "keyword_type": "primary", "weight": 1.0},
        {"keyword": "单亲妈妈", "keyword_type": "secondary", "weight": 0.8},
        {"keyword": "作业辅导", "keyword_type": "secondary", "weight": 0.6},
        {"keyword": "成人教育", "keyword_type": "negative", "weight": 1.0},
    ]

    result = score_creator_candidate(profile, posts, keywords)

    assert result["eligible"] is True
    assert result["score"] >= 70
    assert "K12教育" in result["matched_keywords"]["primary"]
    assert result["evidence"][0]["post_id"] == "p1"
```

- [ ] **Step 2: Run scoring test and verify failure**

Run:

```powershell
python -m pytest tests\test_creator_discovery_scoring.py::test_score_creator_requires_primary_and_explains_evidence -q
```

Expected: FAIL because the scoring module is missing.

- [ ] **Step 3: Implement scoring function**

Create `research/creator_scoring.py`:

```python
from typing import Any


def score_creator_candidate(
    profile: dict[str, Any],
    posts: list[dict[str, Any]],
    keywords: list[dict[str, Any]],
) -> dict[str, Any]:
    text_blocks = [
        {
            "post_id": post.get("platform_post_id"),
            "url": post.get("url"),
            "text": f"{post.get('title') or ''}\n{post.get('content') or ''}",
            "engagement": post.get("engagement_json") or {},
        }
        for post in posts
    ]
    matched = {"primary": [], "secondary": [], "platform_adapted": [], "negative": []}
    evidence = []

    for keyword in keywords:
        term = keyword["keyword"]
        key_type = keyword.get("keyword_type", "secondary")
        for block in text_blocks:
            if term and term.lower() in block["text"].lower():
                matched.setdefault(key_type, []).append(term)
                evidence.append(
                    {
                        "keyword": term,
                        "keyword_type": key_type,
                        "post_id": block["post_id"],
                        "url": block["url"],
                        "context": block["text"][:160],
                        "engagement": block["engagement"],
                    }
                )
                break

    if not matched["primary"]:
        return {
            "eligible": False,
            "score": 0,
            "labels": ["主词未命中"],
            "matched_keywords": matched,
            "evidence": evidence,
        }

    score = 30
    score += min(len(set(matched["secondary"])) * 10, 20)
    score += min(len(set(matched["platform_adapted"])) * 5, 10)
    score += min(int(profile.get("recent_post_count_30d") or 0) * 2, 10)
    score += min(float(profile.get("avg_engagement_rate") or 0) * 100, 15)
    score -= min(len(set(matched["negative"])) * 15, 30)
    score = max(0, min(100, round(score, 2)))

    labels = []
    if score >= 80:
        labels.append("高匹配")
    elif score >= 60:
        labels.append("可跟进")
    else:
        labels.append("低优先级")
    if matched["negative"]:
        labels.append("存在排除词风险")

    return {
        "eligible": score >= 60 and not matched["negative"],
        "score": score,
        "labels": labels,
        "matched_keywords": {key: sorted(set(value)) for key, value in matched.items()},
        "evidence": evidence,
    }
```

- [ ] **Step 4: Add repository method to score candidates**

Add `ResearchRepository.score_creator_candidates_for_scene_pack(scene_pack_id, platform=None, limit=100)` that:

1. Loads enabled scene pack keywords.
2. Loads account profiles with `candidate_creator` role for the scene pack.
3. Loads recent research posts for each account where author evidence matches the profile account id.
4. Calls `score_creator_candidate`.
5. Upserts or returns candidate rows with `match_score`, `labels`, and `evidence`.

Use this shape for returned items:

```python
{
    "account_profile": profile,
    "score": score["score"],
    "labels": score["labels"],
    "eligible": score["eligible"],
    "matched_keywords": score["matched_keywords"],
    "evidence": score["evidence"],
}
```

- [ ] **Step 5: Add API route**

In `api/routers/creator_search.py`, add:

```python
@router.post("/scene-packs/{scene_pack_id}/score-candidates")
async def score_scene_pack_candidates(scene_pack_id: int, platform: str | None = None):
    return {
        "candidates": await ResearchRepository().score_creator_candidates_for_scene_pack(
            scene_pack_id=scene_pack_id,
            platform=platform,
        )
    }
```

- [ ] **Step 6: Run scoring tests**

Run:

```powershell
python -m pytest tests\test_creator_discovery_scoring.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add research/creator_scoring.py research/repository.py api/routers/creator_search.py tests/test_creator_discovery_scoring.py
git commit -m "feat: score creator candidates with evidence"
```

---

### Task 6: Monitor Pool Uses Unified Account Roles

**Files:**
- Modify: `research/monitor_pools.py`
- Modify: `research/repository.py`
- Modify: `api/routers/creator_search.py`
- Test: `tests/test_monitor_pools.py`

- [ ] **Step 1: Write monitor pool role test**

Add to `tests/test_monitor_pools.py`:

```python
@pytest.mark.asyncio
async def test_add_creator_to_monitor_pool_adds_monitored_role(repository):
    pool = await repository.create_monitor_pool(
        {
            "name": "K12 pool",
            "vertical_id": 1,
            "scene_pack_ids_json": [2],
            "platforms_json": ["xhs"],
            "frequency_minutes": 720,
            "comment_policy": "none",
            "enabled": True,
        }
    )
    profile = await repository.upsert_account_profile(
        {
            "platform": "xhs",
            "account_id": "u1",
            "display_name": "Creator One",
            "tag_summary_json": {},
            "verified": False,
        }
    )

    result = await repository.add_account_profile_to_monitor_pool(
        pool["id"],
        profile["id"],
        crawl_now=False,
    )

    assert result["role"] == "monitored_creator"
    roles = await repository.list_account_roles(profile_id=profile["id"])
    assert any(item["monitor_pool_id"] == pool["id"] for item in roles)
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests\test_monitor_pools.py::test_add_creator_to_monitor_pool_adds_monitored_role -q
```

Expected: FAIL because pool role method is missing.

- [ ] **Step 3: Add repository monitor pool role method**

Add to `research/repository.py`:

```python
async def add_account_profile_to_monitor_pool(
    self,
    pool_id: int,
    profile_id: int,
    *,
    crawl_now: bool = False,
) -> dict[str, Any]:
    pool = await self.get_monitor_pool(pool_id)
    if not pool:
        raise KeyError(pool_id)
    role = await self.upsert_account_role(
        {
            "account_profile_id": profile_id,
            "role": "monitored_creator",
            "vertical_id": pool.get("vertical_id"),
            "scene_pack_id": (pool.get("scene_pack_ids") or [None])[0],
            "monitor_pool_id": pool_id,
            "source": "manual",
            "status": "active",
        }
    )
    return {**role, "crawl_now": crawl_now}
```

- [ ] **Step 4: Update monitor pool service**

In `research/monitor_pools.py`, when adding creators, resolve or create account profiles and call `add_account_profile_to_monitor_pool`. Keep existing creator-mode job behavior:

```python
await self.repository.add_account_profile_to_monitor_pool(
    pool_id,
    profile["id"],
    crawl_now=crawl_now,
)
```

- [ ] **Step 5: Update API payload support**

In `api/routers/creator_search.py`, allow add-to-pool payloads to include `account_profile_ids` as well as existing platform creator identifiers:

```python
account_profile_ids = payload.get("account_profile_ids") or []
for profile_id in account_profile_ids:
    await repository.add_account_profile_to_monitor_pool(
        pool_id,
        int(profile_id),
        crawl_now=bool(payload.get("crawl_now")),
    )
```

- [ ] **Step 6: Run monitor pool tests**

Run:

```powershell
python -m pytest tests\test_monitor_pools.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add research/monitor_pools.py research/repository.py api/routers/creator_search.py tests/test_monitor_pools.py
git commit -m "feat: connect monitor pools to account roles"
```

---

### Task 7: Keyword Heat Dual-Track Rule and AI Result Shape

**Files:**
- Modify: `research/keyword_heat.py`
- Modify: `api/routers/keyword_opportunities.py`
- Test: `tests/test_keyword_heat_dual_track.py`

- [ ] **Step 1: Write heat dual-track test**

Create `tests/test_keyword_heat_dual_track.py`:

```python
from research.keyword_heat import build_keyword_heat_signal


def test_keyword_heat_returns_rule_ai_and_conflict():
    result = build_keyword_heat_signal(
        keyword="K12教育",
        platform="dy",
        metrics={
            "volume_24h": 30,
            "volume_7d_avg": 10,
            "volume_30d_avg": 8,
            "engagement_24h": 5000,
            "hot_post_rate": 0.4,
            "creator_participation": 12,
            "platform_coverage": 2,
        },
        ai_judgment={"label": "normal", "confidence": 0.7, "explanation": "AI sees stable topic"},
    )

    assert result["rule"]["label"] == "boosting"
    assert result["ai"]["label"] == "normal"
    assert result["conflict"] is True
    assert result["evidence"]
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests\test_keyword_heat_dual_track.py -q
```

Expected: FAIL because `build_keyword_heat_signal` does not return dual-track output yet.

- [ ] **Step 3: Implement dual-track heat builder**

In `research/keyword_heat.py`, add:

```python
def build_keyword_heat_signal(
    *,
    keyword: str,
    platform: str,
    metrics: dict[str, float],
    ai_judgment: dict[str, object] | None = None,
) -> dict[str, object]:
    volume_24h = float(metrics.get("volume_24h") or 0)
    volume_7d_avg = float(metrics.get("volume_7d_avg") or 0)
    hot_post_rate = float(metrics.get("hot_post_rate") or 0)
    engagement_24h = float(metrics.get("engagement_24h") or 0)

    if volume_24h < 3 and engagement_24h < 100:
        label = "insufficient_data"
        score = 0
    else:
        growth_ratio = volume_24h / max(volume_7d_avg, 1)
        score = min(100, round(growth_ratio * 35 + hot_post_rate * 40 + min(engagement_24h / 1000, 25), 2))
        if growth_ratio >= 1.8 and hot_post_rate >= 0.2:
            label = "boosting"
        elif growth_ratio <= 0.5:
            label = "cooling"
        else:
            label = "normal"

    evidence = [
        f"24小时新增 {int(volume_24h)}，7日均值 {round(volume_7d_avg, 2)}",
        f"爆款率 {round(hot_post_rate * 100, 2)}%",
        f"24小时互动量 {int(engagement_24h)}",
    ]
    ai = ai_judgment or {
        "label": "insufficient_data",
        "confidence": 0,
        "explanation": "未配置 AI 判断或样本不足",
    }
    return {
        "keyword": keyword,
        "platform": platform,
        "rule": {"label": label, "score": score, "metrics": metrics},
        "ai": ai,
        "conflict": bool(ai.get("label") and ai.get("label") != label),
        "evidence": evidence,
    }
```

- [ ] **Step 4: Update API response**

In `api/routers/keyword_opportunities.py`, make `/heat/signal` return:

```python
{
    "keyword": keyword,
    "platform": platform,
    "rule": {"label": "...", "score": 0, "metrics": {...}},
    "ai": {"label": "...", "confidence": 0, "explanation": "..."},
    "conflict": False,
    "evidence": [...],
}
```

Keep legacy fields such as `label` and `heat_score` for current frontend compatibility:

```python
payload["label"] = payload["rule"]["label"]
payload["heat_score"] = payload["rule"]["score"]
```

- [ ] **Step 5: Run heat tests**

Run:

```powershell
python -m pytest tests\test_keyword_heat.py tests\test_keyword_heat_dual_track.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add research/keyword_heat.py api/routers/keyword_opportunities.py tests/test_keyword_heat_dual_track.py tests/test_keyword_heat.py
git commit -m "feat: add dual-track keyword heat signals"
```

---

### Task 8: Competitor Composition From Unified Account Profiles

**Files:**
- Modify: `research/competitors.py`
- Modify: `research/repository.py`
- Modify: `api/routers/competitors.py`
- Test: `tests/test_competitor_composition.py`

- [ ] **Step 1: Write competitor composition test**

Add to `tests/test_competitor_composition.py`:

```python
from research.competitors import build_competitor_composition


def test_competitor_composition_splits_content_patterns():
    posts = [
        {
            "platform": "dy",
            "title": "K12教育怎么获客",
            "content": "教培机构线上招生",
            "publish_time": "2026-05-20T09:00:00+00:00",
            "engagement_json": {
                "source_keyword": "K12教育",
                "liked_count": 100,
                "comment_count": 20,
                "share_count": 5,
                "aweme_type": 0,
            },
        },
        {
            "platform": "dy",
            "title": "家庭教育焦虑",
            "content": "家长如何陪伴学习",
            "publish_time": "2026-05-20T21:00:00+00:00",
            "engagement_json": {
                "source_keyword": "家庭教育",
                "liked_count": 10,
                "comment_count": 1,
                "share_count": 1,
                "aweme_type": 0,
            },
        },
    ]

    result = build_competitor_composition(posts, hot_threshold=80)

    assert result["new_post_count"] == 2
    assert result["keyword_distribution"]["K12教育"] == 1
    assert result["hot_post_rate"] == 0.5
    assert result["publish_time_distribution"]["morning"] == 1
    assert result["publish_time_distribution"]["night"] == 1
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests\test_competitor_composition.py::test_competitor_composition_splits_content_patterns -q
```

Expected: FAIL if composition builder is not present or does not return these fields.

- [ ] **Step 3: Implement composition builder**

In `research/competitors.py`, add or update:

```python
from collections import Counter
from datetime import datetime
from typing import Any


def build_competitor_composition(
    posts: list[dict[str, Any]], *, hot_threshold: int = 100
) -> dict[str, Any]:
    keyword_counts = Counter()
    content_type_counts = Counter()
    publish_time_counts = Counter()
    total_interaction = 0
    hot_posts = []

    for post in posts:
        engagement = post.get("engagement_json") or {}
        keyword = engagement.get("source_keyword") or "未标注"
        keyword_counts[str(keyword)] += 1
        content_type_counts[str(engagement.get("aweme_type") or engagement.get("type") or "unknown")] += 1

        interaction = int(engagement.get("liked_count") or 0) + int(engagement.get("comment_count") or 0) + int(engagement.get("share_count") or 0)
        total_interaction += interaction
        if interaction >= hot_threshold:
            hot_posts.append(post)

        publish_time = post.get("publish_time")
        if isinstance(publish_time, str):
            try:
                publish_time = datetime.fromisoformat(publish_time)
            except ValueError:
                publish_time = None
        hour = publish_time.hour if isinstance(publish_time, datetime) else -1
        if 6 <= hour < 12:
            publish_time_counts["morning"] += 1
        elif 12 <= hour < 18:
            publish_time_counts["afternoon"] += 1
        elif 18 <= hour < 24:
            publish_time_counts["night"] += 1
        else:
            publish_time_counts["unknown"] += 1

    total = len(posts)
    return {
        "new_post_count": total,
        "total_interaction": total_interaction,
        "keyword_distribution": dict(keyword_counts),
        "tag_distribution": {},
        "content_type_distribution": dict(content_type_counts),
        "publish_time_distribution": dict(publish_time_counts),
        "hot_post_rate": round(len(hot_posts) / total, 4) if total else 0,
        "interaction_structure": {
            "liked_count": sum(int((p.get("engagement_json") or {}).get("liked_count") or 0) for p in posts),
            "comment_count": sum(int((p.get("engagement_json") or {}).get("comment_count") or 0) for p in posts),
            "share_count": sum(int((p.get("engagement_json") or {}).get("share_count") or 0) for p in posts),
        },
        "top_posts": hot_posts[:10],
        "evidence": [
            {"title": post.get("title"), "platform": post.get("platform")}
            for post in hot_posts[:5]
        ],
    }
```

- [ ] **Step 4: Hook composition rebuild API**

In `api/routers/competitors.py`, update `/composition/rebuild` to:

1. Resolve competitor account role.
2. Load related research posts.
3. Call `build_competitor_composition`.
4. Upsert `research_competitor_composition_snapshots`.
5. Return the saved snapshot.

The response must include:

```python
{
    "competitor_id": competitor_id,
    "snapshot": snapshot,
    "composition": snapshot["composition_json"],
}
```

- [ ] **Step 5: Run competitor tests**

Run:

```powershell
python -m pytest tests\test_competitor_composition.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add research/competitors.py research/repository.py api/routers/competitors.py tests/test_competitor_composition.py
git commit -m "feat: build competitor composition snapshots"
```

---

### Task 9: Boss Reports for Vertical and Scene Pack Views

**Files:**
- Modify: `research/reporting.py`
- Modify: `api/routers/reports.py`
- Test: `tests/test_reports_api.py`

- [ ] **Step 1: Write report builder test**

Add to `tests/test_reports_api.py`:

```python
from research.reporting import build_boss_report


def test_boss_report_uses_real_sections_and_evidence():
    report = build_boss_report(
        scope={"type": "scene_pack", "id": 2, "name": "K12教育 + 单亲妈妈"},
        keyword_signals=[
            {
                "keyword": "K12教育",
                "rule": {"label": "boosting", "score": 88},
                "ai": {"label": "boosting", "explanation": "讨论明显增加"},
                "conflict": False,
                "evidence": ["24小时新增高于7日均值"],
            }
        ],
        creator_candidates=[
            {
                "display_name": "Creator A",
                "score": 91,
                "labels": ["高匹配"],
                "evidence": [{"url": "https://example.test/post"}],
            }
        ],
        competitor_snapshots=[],
        content_snapshots=[],
    )

    assert report["summary"]
    assert report["recommended_actions"]
    assert report["top_creators"][0]["score"] == 91
    assert report["keyword_signals"][0]["keyword"] == "K12教育"
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests\test_reports_api.py::test_boss_report_uses_real_sections_and_evidence -q
```

Expected: FAIL if `build_boss_report` does not exist or has a different shape.

- [ ] **Step 3: Implement report builder**

In `research/reporting.py`, add:

```python
from typing import Any


def build_boss_report(
    *,
    scope: dict[str, Any],
    keyword_signals: list[dict[str, Any]],
    creator_candidates: list[dict[str, Any]],
    competitor_snapshots: list[dict[str, Any]],
    content_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = []
    if keyword_signals:
        top_keyword = keyword_signals[0]
        summary.append(
            f"{top_keyword['keyword']} 当前信号为 {top_keyword['rule']['label']}，规则分 {top_keyword['rule']['score']}。"
        )
    if creator_candidates:
        summary.append(f"发现 {len(creator_candidates)} 个候选达人，可优先跟进 Top 10。")
    if competitor_snapshots:
        summary.append(f"已生成 {len(competitor_snapshots)} 个友商组成快照。")
    if not summary:
        summary.append("当前样本不足，建议先完成采集、回填和分析。")

    recommended_actions = []
    if creator_candidates:
        recommended_actions.append("优先联系高匹配达人，并加入监控池持续观察。")
    if keyword_signals:
        recommended_actions.append("围绕高热关键词扩展平台适配词，并观察 24 小时变化。")
    if competitor_snapshots:
        recommended_actions.append("复盘友商爆款内容的发布时间、内容类型和关键词组合。")

    return {
        "scope": scope,
        "summary": summary,
        "keyword_signals": keyword_signals,
        "top_creators": creator_candidates[:10],
        "competitor_changes": competitor_snapshots,
        "content_tracking": content_snapshots,
        "recommended_actions": recommended_actions,
        "evidence": {
            "keywords": [item.get("evidence", []) for item in keyword_signals],
            "creators": [item.get("evidence", []) for item in creator_candidates[:10]],
        },
    }
```

- [ ] **Step 4: Add report APIs**

In `api/routers/reports.py`, add:

```python
@router.get("/vertical/{vertical_id}")
async def get_vertical_report(vertical_id: int):
    repository = ResearchRepository()
    report = await repository.build_vertical_report_payload(vertical_id)
    return report


@router.get("/scene-pack/{scene_pack_id}")
async def get_scene_pack_report(scene_pack_id: int):
    repository = ResearchRepository()
    report = await repository.build_scene_pack_report_payload(scene_pack_id)
    return report
```

Implement `build_vertical_report_payload` and `build_scene_pack_report_payload` in `research/repository.py` by loading:

- keyword heat snapshots for scope
- creator candidates for scope
- competitor composition snapshots for scope
- content tracking snapshots for scope

Then call `build_boss_report`.

- [ ] **Step 5: Run report tests**

Run:

```powershell
python -m pytest tests\test_reports_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add research/reporting.py research/repository.py api/routers/reports.py tests/test_reports_api.py
git commit -m "feat: build boss reports"
```

---

### Task 10: Frontend Types and API Layer

**Files:**
- Create: `api/webui/src/types.ts`
- Create: `api/webui/src/api.ts`
- Modify: `api/webui/src/main.tsx`
- Test: `npm.cmd run build`

- [ ] **Step 1: Extract shared types**

Create `api/webui/src/types.ts`:

```typescript
export type PlatformCode = "xhs" | "dy" | "wb" | "bili" | "zhihu" | "tieba" | "ks";

export type AccountProfile = {
  id: number;
  platform: string;
  account_id: string;
  display_name?: string | null;
  avatar_url?: string | null;
  bio?: string | null;
  verified: boolean;
  follower_count?: number | null;
  post_count?: number | null;
  avg_engagement_rate?: number | null;
  hot_post_rate?: number | null;
  recent_post_count_30d?: number | null;
};

export type CreatorCandidateScore = {
  account_profile: AccountProfile;
  score: number;
  labels: string[];
  eligible: boolean;
  matched_keywords: Record<string, string[]>;
  evidence: Array<{
    keyword: string;
    keyword_type: string;
    post_id?: string | null;
    url?: string | null;
    context: string;
    engagement?: Record<string, unknown>;
  }>;
};

export type HeatSignal = {
  keyword: string;
  platform: string;
  rule: { label: string; score: number; metrics: Record<string, number> };
  ai: { label: string; confidence: number; explanation: string };
  conflict: boolean;
  evidence: string[];
};

export type BossReport = {
  scope: { type: string; id: number; name: string };
  summary: string[];
  keyword_signals: HeatSignal[];
  top_creators: CreatorCandidateScore[];
  competitor_changes: unknown[];
  content_tracking: unknown[];
  recommended_actions: string[];
  evidence: Record<string, unknown>;
};
```

- [ ] **Step 2: Extract API helper**

Create `api/webui/src/api.ts`:

```typescript
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}
```

- [ ] **Step 3: Update main imports**

In `api/webui/src/main.tsx`, import:

```typescript
import { api } from "./api";
import type { BossReport, CreatorCandidateScore, HeatSignal } from "./types";
```

Remove any duplicate local `api` helper only after verifying every existing caller still compiles.

- [ ] **Step 4: Run frontend build**

Run:

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add api/webui/src/types.ts api/webui/src/api.ts api/webui/src/main.tsx
git commit -m "refactor: extract research frontend api types"
```

---

### Task 11: Frontend Review Queue and Candidate Evidence UI

**Files:**
- Modify: `api/webui/src/main.tsx`
- Modify: `api/webui/src/styles.css`
- Test: `npm.cmd run build`

- [ ] **Step 1: Add review queue state**

In `main.tsx`, add state near keyword library state:

```typescript
const [keywordSuggestions, setKeywordSuggestions] = React.useState<Array<Record<string, unknown>>>([]);
```

Add loader:

```typescript
async function loadKeywordSuggestions() {
  const data = await api<{ suggestions: Array<Record<string, unknown>> }>("/api/keyword-library/ai/suggestions?status=pending");
  setKeywordSuggestions(data.suggestions || []);
}
```

Call it in the same initialization block as `loadKeywordLibrary`.

- [ ] **Step 2: Add approve/reject actions**

In `main.tsx`, add:

```typescript
async function approveKeywordSuggestion(id: number) {
  await api(`/api/keyword-library/ai/suggestions/${id}/approve`, { method: "POST" });
  await Promise.all([loadKeywordLibrary(), loadKeywordSuggestions()]);
}

async function rejectKeywordSuggestion(id: number) {
  await api(`/api/keyword-library/ai/suggestions/${id}/reject`, { method: "POST" });
  await loadKeywordSuggestions();
}
```

- [ ] **Step 3: Render review queue in keyword library page**

Pass `keywordSuggestions`, `onApproveSuggestion`, and `onRejectSuggestion` into `KeywordLibraryPage`.

Render:

```tsx
<section className="panel">
  <div className="panel-head">
    <div>
      <h2>AI 建议审核</h2>
      <p>AI 自动发现的新词和权重变化默认进入待审核队列。</p>
    </div>
    <span>{keywordSuggestions.length} 条</span>
  </div>
  <div className="review-list">
    {keywordSuggestions.map((item) => (
      <div className="review-row" key={String(item.id)}>
        <strong>{JSON.stringify(item.suggestions || item.suggested_payload)}</strong>
        <span>{String(item.status || "pending")}</span>
        <button type="button" onClick={() => onApproveSuggestion(Number(item.id))}>通过</button>
        <button type="button" onClick={() => onRejectSuggestion(Number(item.id))}>拒绝</button>
      </div>
    ))}
  </div>
</section>
```

- [ ] **Step 4: Render candidate score evidence**

In `AudiencePage`, after candidate results load, display:

```tsx
<div className="candidate-grid">
  {candidates.map((candidate) => (
    <article className="candidate-card" key={candidate.account_profile.id}>
      <div>
        <strong>{candidate.account_profile.display_name || candidate.account_profile.account_id}</strong>
        <span>{labelPlatform(candidate.account_profile.platform)}</span>
      </div>
      <div className="score-ring">{candidate.score}</div>
      <div className="chips">{candidate.labels.map((label) => <span key={label}>{label}</span>)}</div>
      <ul className="evidence-list">
        {candidate.evidence.slice(0, 3).map((item, index) => (
          <li key={index}>
            <strong>{item.keyword}</strong>
            <span>{item.context}</span>
          </li>
        ))}
      </ul>
    </article>
  ))}
</div>
```

- [ ] **Step 5: Add CSS**

In `styles.css`, add:

```css
.review-list,
.candidate-grid {
  display: grid;
  gap: 12px;
}

.review-row,
.candidate-card {
  border: 1px solid #dfe7e5;
  border-radius: 8px;
  padding: 14px;
  background: #fff;
}

.candidate-card {
  display: grid;
  gap: 10px;
}

.score-ring {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #04786f;
  border: 4px solid #9bddcf;
  font-weight: 700;
}

.evidence-list {
  margin: 0;
  padding-left: 18px;
  color: #52615f;
}
```

- [ ] **Step 6: Run frontend build**

Run:

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add api/webui/src/main.tsx api/webui/src/styles.css
git commit -m "feat: show keyword review and creator evidence"
```

---

### Task 12: Frontend Heat Dual-Track and Boss Report Pages

**Files:**
- Modify: `api/webui/src/main.tsx`
- Modify: `api/webui/src/styles.css`
- Test: `npm.cmd run build`

- [ ] **Step 1: Add report state and loaders**

In `main.tsx`, add:

```typescript
const [bossReport, setBossReport] = React.useState<BossReport | null>(null);

async function loadScenePackReport(scenePackId: number) {
  const data = await api<BossReport>(`/api/reports/scene-pack/${scenePackId}`);
  setBossReport(data);
}

async function loadVerticalReport(verticalId: number) {
  const data = await api<BossReport>(`/api/reports/vertical/${verticalId}`);
  setBossReport(data);
}
```

- [ ] **Step 2: Render heat dual-track**

In `KeywordPage`, display heat results with:

```tsx
{heatSignal && (
  <div className="dual-track">
    <div className="track-card">
      <span>规则判断</span>
      <strong>{heatSignal.rule.label}</strong>
      <em>{heatSignal.rule.score}</em>
    </div>
    <div className="track-card">
      <span>AI 判断</span>
      <strong>{heatSignal.ai.label}</strong>
      <p>{heatSignal.ai.explanation}</p>
    </div>
    {heatSignal.conflict && <div className="conflict-banner">规则与 AI 判断不一致，需要人工复核。</div>}
    <ul className="evidence-list">
      {heatSignal.evidence.map((item) => <li key={item}>{item}</li>)}
    </ul>
  </div>
)}
```

- [ ] **Step 3: Render report page**

In `ReportPage`, render:

```tsx
{bossReport ? (
  <section className="report-layout">
    <div className="panel">
      <div className="panel-head">
        <h2>{bossReport.scope.name}</h2>
        <span>{bossReport.scope.type}</span>
      </div>
      <div className="insight-list">
        {bossReport.summary.map((item) => (
          <div key={item}><strong>摘要</strong><span>{item}</span></div>
        ))}
      </div>
    </div>
    <div className="panel">
      <div className="panel-head"><h2>建议动作</h2></div>
      <ul className="evidence-list">
        {bossReport.recommended_actions.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
    <div className="panel">
      <div className="panel-head"><h2>推荐达人</h2></div>
      <div className="candidate-grid">
        {bossReport.top_creators.map((item) => (
          <article className="candidate-card" key={item.account_profile.id}>
            <strong>{item.account_profile.display_name || item.account_profile.account_id}</strong>
            <span>匹配分 {item.score}</span>
          </article>
        ))}
      </div>
    </div>
  </section>
) : (
  <EmptyState title="请选择赛道或场景包" body="生成报告后，这里会展示老板可读的摘要、机会和建议动作。" />
)}
```

- [ ] **Step 4: Add report CSS**

In `styles.css`, add:

```css
.dual-track,
.report-layout {
  display: grid;
  gap: 16px;
}

.track-card {
  border: 1px solid #dfe7e5;
  border-radius: 8px;
  padding: 16px;
  background: #fff;
}

.track-card strong {
  display: block;
  font-size: 24px;
  margin-top: 4px;
}

.conflict-banner {
  border: 1px solid #ffb86b;
  background: #fff7ed;
  color: #9a4d00;
  border-radius: 8px;
  padding: 12px;
}
```

- [ ] **Step 5: Run frontend build**

Run:

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add api/webui/src/main.tsx api/webui/src/styles.css
git commit -m "feat: show heat signals and boss reports"
```

---

### Task 13: End-to-End Local Validation With Real TikHub Data

**Files:**
- Create: `docs/real_collection_validation.md`
- No production code changes unless validation exposes a defect.

- [ ] **Step 1: Configure temporary environment variables**

Use a local shell only. Do not write the TikHub key to files.

```powershell
$env:ENABLE_TIKHUB='true'
$env:TIKHUB_API_KEY='<temporary-test-key>'
$env:RESEARCH_AUTHOR_HASH_SALT='local-test-salt'
```

- [ ] **Step 2: Run XHS TikHub collection**

```powershell
python main.py --platform xhs --lt qrcode --type search --save_data_option sqlite --keywords "K12教育" --get_comment false --get_sub_comment false --headless true
```

Expected: command exits 0 and logs several `[store.xhs.update_xhs_note]` rows.

- [ ] **Step 3: Run Douyin TikHub collection**

```powershell
python main.py --platform dy --lt qrcode --type search --save_data_option sqlite --keywords "K12教育" --get_comment false --get_sub_comment false --headless true
```

Expected: command exits 0 and logs several `[store.douyin.update_douyin_aweme]` rows. Raw fallback warnings for non-video search cards are acceptable when valid video rows are also saved.

- [ ] **Step 4: Create or select validation research job**

Use existing APIs or a short local script to create a search job:

```python
{
    "name": "K12 TikHub validation",
    "topic": "education K12",
    "platforms": ["xhs", "dy"],
    "keywords": ["K12教育"],
    "collection_mode": "search",
    "status": "completed",
    "comment_policy": {"level": "none"},
    "raw_record_mode": "none",
    "anonymize_authors": True,
    "schedule_enabled": False,
    "start_date": "2024-01-01",
    "end_date": "2026-12-31"
}
```

- [ ] **Step 5: Run postprocess**

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/research/jobs/<job_id>/postprocess
```

Expected JSON contains:

```json
{
  "backfill": {
    "xhs": {"posts": 1},
    "dy": {"posts": 1}
  }
}
```

Counts can be greater than 1.

- [ ] **Step 6: Verify research table counts**

Run:

```powershell
@'
import sqlite3
con = sqlite3.connect("database/sqlite_tables.db")
cur = con.cursor()
print(cur.execute("select platform,count(*) from research_posts group by platform").fetchall())
print(cur.execute("select count(*) from raw_records").fetchone()[0])
con.close()
'@ | python -
```

Expected: `research_posts` includes both `xhs` and `dy`; `raw_records` is greater than 0.

- [ ] **Step 7: Verify frontend build**

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 8: Write validation notes**

Create `docs/real_collection_validation.md` with:

```markdown
# Real Collection Validation

Date: 2026-05-20

## Environment

- TikHub key was provided through a temporary process environment variable.
- The key was not written to source files.

## Commands

- XHS search command
- Douyin search command
- Postprocess endpoint call

## Results

- XHS rows saved:
- Douyin rows saved:
- Research posts by platform:
- Raw records:
- Frontend build:

## Known Limits

- Comments were disabled for this validation.
- AI analysis was not required for collection validation.
- Non-video Douyin search cards can be stored through raw fallback or skipped by normalized video logic.
```

- [ ] **Step 9: Commit validation note**

```powershell
git add docs/real_collection_validation.md
git commit -m "docs: record real collection validation"
```

---

## Final Verification

- [ ] Run backend focused tests:

```powershell
python -m pytest tests\test_tikhub_endpoints.py tests\test_postprocess_pipeline.py tests\test_account_profiles.py tests\test_keyword_library_api.py tests\test_creator_discovery_scoring.py tests\test_keyword_heat_dual_track.py tests\test_competitor_composition.py tests\test_reports_api.py -q
```

Expected: PASS.

- [ ] Run frontend build:

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] Run full backend suite if local Redis is available:

```powershell
python -m pytest -q
```

Expected: PASS except documented local Redis-dependent tests when Redis is not running.

- [ ] Open `/research` and verify:

1. Config center shows global default platforms and provider status.
2. Keyword library shows verticals, scene packs, and pending AI suggestions.
3. Audience page shows candidate scores and evidence.
4. Keyword heat page shows rule + AI dual-track results.
5. Competitor page shows composition snapshots.
6. Report page shows a vertical or scene-pack report with summary and evidence.

## Self-Review

Spec coverage:

- Real TikHub collection and automatic backfill: Task 1 and Task 13.
- AI suggestion queue with manual approval: Task 2 and Task 11.
- Unified account profile and roles: Task 3 and Task 6.
- Creator discovery score, labels, and evidence: Task 5 and Task 11.
- Monitor pool role reuse: Task 6.
- Keyword heat rule + AI dual-track: Task 7 and Task 12.
- Competitor composition snapshots: Task 8.
- Boss reports for vertical and scene-pack scopes: Task 9 and Task 12.
- Frontend pages and build validation: Tasks 10, 11, 12, and Task 13.

Placeholder scan:

- This plan contains no placeholder implementation steps.
- Test commands include expected results.
- Secrets are represented only as `<temporary-test-key>` in validation instructions and must be supplied through process environment variables.

