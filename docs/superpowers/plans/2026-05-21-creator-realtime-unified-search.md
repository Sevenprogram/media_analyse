# Creator Realtime Unified Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified creator search that optionally combines local database results with TikHub realtime Xiaohongshu/Douyin discovery, automatically persists realtime creators, labels result sources, and shows a progress bar in the UI.

**Architecture:** Keep `/api/creator-search/search` as the single endpoint. Add a focused realtime discovery service that normalizes TikHub content search results into creator rows, persists profiles/candidates, and returns diagnostics; then merge those rows with existing local search results in `research/creator_search.py`. The frontend adds an opt-in checkbox, staged progress state, source badges, and non-blocking realtime diagnostics.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy repository layer, existing TikHub client/endpoint registry/mappers, React, TypeScript, CSS, pytest, Vite build.

---

## File Structure

- Modify `research/schemas.py`: add `include_realtime` to `CreatorSearchRequest`.
- Create `research/realtime_creator_discovery.py`: TikHub-backed realtime discovery, normalization, scoring, persistence, diagnostics.
- Modify `research/creator_search.py`: source metadata helpers, local result labels, realtime invocation, merge/dedupe, top-level progress diagnostics.
- Modify `api/routers/creator_search.py`: pass the repository into unified search; no new endpoint.
- Modify `tests/test_creator_discovery_workflow_api.py`: API-level tests for unified search merge/failure behavior.
- Create `tests/test_realtime_creator_discovery.py`: unit tests for realtime normalization/scoring/persistence with fake TikHub client.
- Modify `api/webui/src/pages/ResearchModulePages.tsx`: checkbox, progress stages, source badges, realtime warning.
- Modify `api/webui/src/styles.css`: progress bar and badge styling.

---

### Task 1: Extend Search Schema And Preserve Local-Only Behavior

**Files:**
- Modify: `research/schemas.py`
- Modify: `research/creator_search.py`
- Test: `tests/test_creator_discovery_workflow_api.py`

- [ ] **Step 1: Write the failing API test for local-only source metadata**

Append this test to `tests/test_creator_discovery_workflow_api.py`:

```python
def test_creator_search_local_only_adds_database_source(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    import api.routers.creator_search as creator_search_router

    class FakeRepository:
        async def list_tag_definitions(self, vertical_id=None, enabled_only=True):
            return []

        async def list_verticals(self, enabled_only=True):
            return []

        async def list_creator_profiles(self, platforms=None, limit=None):
            return [
                {
                    "platform": "xhs",
                    "creator_id": "local-1",
                    "display_name": "Local Teacher",
                    "profile_url": "https://www.xiaohongshu.com/user/profile/local-1",
                    "follower_count": 1200,
                    "recent_post_count_30d": 4,
                    "avg_engagement_rate": None,
                    "hot_post_rate": None,
                    "tag_summary_json": {},
                }
            ]

        async def list_entity_tags(self, **kwargs):
            return []

        async def list_posts_by_creator(self, platform, creator_id, limit=30):
            return [
                {
                    "platform": platform,
                    "platform_post_id": "p1",
                    "title": "K12 education note",
                    "content": "single mom learning plan",
                    "publish_time": None,
                    "engagement_json": {"liked_count": 20},
                }
            ]

    monkeypatch.setattr(creator_search_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/creator-search/search",
        json={
            "raw_query": "K12",
            "platforms": ["xhs"],
            "include_realtime": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["realtime"]["status"] == "skipped"
    assert payload["progress"]["stage"] == "complete"
    assert payload["results"][0]["source_type"] == "local"
    assert payload["results"][0]["source_labels"] == ["Database"]
    assert payload["results"][0]["realtime_unverified"] is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/test_creator_discovery_workflow_api.py::test_creator_search_local_only_adds_database_source -v
```

Expected: FAIL because `include_realtime` is not accepted or source metadata is missing.

- [ ] **Step 3: Add the request field**

In `research/schemas.py`, update `CreatorSearchRequest`:

```python
class CreatorSearchRequest(BaseModel):
    raw_query: str = Field(default="", max_length=500)
    selected_vertical_id: int | None = Field(default=None, ge=1)
    required_tag_ids: list[int] = Field(default_factory=list)
    optional_tag_ids: list[int] = Field(default_factory=list)
    negative_tag_ids: list[int] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    follower_min: int | None = Field(default=None, ge=0)
    follower_max: int | None = Field(default=None, ge=0)
    recent_activity_min: int | None = Field(default=None, ge=0)
    engagement_rate_min: float | None = Field(default=None, ge=0)
    limit: int = Field(default=50, ge=1, le=200)
    include_realtime: bool = False
```

- [ ] **Step 4: Add source metadata helpers and local-only response diagnostics**

In `research/creator_search.py`, add these helpers near `_dedupe_creator_results`:

```python
def _with_source_metadata(
    item: dict[str, Any],
    *,
    source_type: str,
    labels: list[str],
    realtime_unverified: bool,
) -> dict[str, Any]:
    return {
        **item,
        "source_type": source_type,
        "source_labels": labels,
        "realtime_unverified": realtime_unverified,
    }


def _realtime_skipped_diagnostics() -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "skipped",
        "platforms": [],
        "unsupported_platforms": [],
        "created_profiles": 0,
        "created_candidates": 0,
        "error": None,
    }


def _complete_progress() -> dict[str, Any]:
    return {"stage": "complete", "label": "Complete", "percent": 100}
```

Then, before appending each local result in `search_creators`, wrap the result:

```python
        result_item = {
            "platform": profile["platform"],
            "creator_id": profile["creator_id"],
            "display_name": profile.get("display_name"),
            "profile_url": profile.get("profile_url"),
            "follower_count": profile.get("follower_count"),
            "total_like_count": _profile_metric(profile, "total_like_count"),
            "total_collect_count": _profile_metric(profile, "total_collect_count"),
            "interaction_count": _profile_metric(profile, "interaction_count"),
            "recent_post_count_30d": profile.get("recent_post_count_30d") or 0,
            "avg_engagement_rate": profile.get("avg_engagement_rate"),
            "hot_post_rate": profile.get("hot_post_rate"),
            "match_score": score,
            "matched_tags": tags or [
                {"source": "query_text_fallback", "term": term}
                for term in fallback["matched_terms"]
            ],
            "evidence": [tag.get("evidence_json") or {} for tag in tags] or fallback["evidence"],
            "representative_posts": fallback["evidence"],
        }
        results.append(
            _with_source_metadata(
                result_item,
                source_type="local",
                labels=["Database"],
                realtime_unverified=False,
            )
        )
```

Finally, in the `return` from `search_creators`, include:

```python
        "realtime": _realtime_skipped_diagnostics(),
        "progress": _complete_progress(),
```

- [ ] **Step 5: Run the local-only test**

Run:

```bash
pytest tests/test_creator_discovery_workflow_api.py::test_creator_search_local_only_adds_database_source -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add research/schemas.py research/creator_search.py tests/test_creator_discovery_workflow_api.py
git commit -m "feat: add creator search source metadata"
```

---

### Task 2: Add Realtime Discovery Service

**Files:**
- Create: `research/realtime_creator_discovery.py`
- Test: `tests/test_realtime_creator_discovery.py`

- [ ] **Step 1: Write failing realtime service tests**

Create `tests/test_realtime_creator_discovery.py`:

```python
import pytest

from research.realtime_creator_discovery import discover_realtime_creators


class FakeTikHubClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def request(self, method, path, *, params=None, json=None):
        self.calls.append({"method": method, "path": path, "params": params, "json": json})
        keyword = (params or json or {}).get("keyword")
        return self.responses.get(keyword, [])

    async def close(self):
        pass


class FakeRepository:
    def __init__(self):
        self.profiles = []
        self.candidates = []

    async def upsert_creator_profile(self, payload):
        self.profiles.append(payload)
        return {"id": len(self.profiles), **payload}

    async def upsert_creator_candidate(self, payload):
        self.candidates.append(payload)
        return {"id": len(self.candidates), **payload}


@pytest.mark.asyncio
async def test_discover_realtime_creators_persists_xhs_author():
    repository = FakeRepository()
    client = FakeTikHubClient(
        {
            "K12": [
                {
                    "note": {
                        "id": "note-1",
                        "title": "K12 learning",
                        "desc": "single mom study plan",
                        "user": {
                            "user_id": "xhs-u1",
                            "nickname": "Teacher X",
                            "desc": "K12 teacher",
                            "fans": 3300,
                            "notes_count": 42,
                        },
                        "interact_info": {
                            "liked_count": 100,
                            "comment_count": 12,
                            "collected_count": 8,
                        },
                    }
                }
            ]
        }
    )

    result = await discover_realtime_creators(
        repository,
        {
            "raw_query": "K12",
            "platforms": ["xhs"],
            "limit": 20,
            "selected_vertical_id": 7,
        },
        client_factory=lambda: client,
    )

    assert result["diagnostics"]["status"] == "ok"
    assert result["diagnostics"]["created_profiles"] == 1
    assert result["diagnostics"]["created_candidates"] == 1
    assert result["results"][0]["platform"] == "xhs"
    assert result["results"][0]["creator_id"] == "xhs-u1"
    assert result["results"][0]["display_name"] == "Teacher X"
    assert result["results"][0]["source_type"] == "realtime"
    assert result["results"][0]["source_labels"] == ["Realtime"]
    assert result["results"][0]["realtime_unverified"] is True
    assert repository.profiles[0]["profile_url"].endswith("/xhs-u1")
    assert repository.candidates[0]["pool_name"] == "realtime"
    assert repository.candidates[0]["vertical_id"] == 7


@pytest.mark.asyncio
async def test_discover_realtime_creators_reports_unsupported_platforms():
    repository = FakeRepository()
    client = FakeTikHubClient({"K12": []})

    result = await discover_realtime_creators(
        repository,
        {"raw_query": "K12", "platforms": ["bili"], "limit": 20},
        client_factory=lambda: client,
    )

    assert result["results"] == []
    assert result["diagnostics"]["status"] == "skipped"
    assert result["diagnostics"]["unsupported_platforms"] == ["bili"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_realtime_creator_discovery.py -v
```

Expected: FAIL because `research/realtime_creator_discovery.py` does not exist.

- [ ] **Step 3: Implement the realtime service**

Create `research/realtime_creator_discovery.py`:

```python
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from media_platform.tikhub.client import TikHubClient
from media_platform.tikhub.endpoints import Capability, get_endpoint
from media_platform.tikhub.mappers.base import author, nested, pick


REALTIME_PLATFORMS = {"xhs", "dy"}


async def discover_realtime_creators(
    repository,
    request: dict[str, Any],
    *,
    client_factory: Callable[[], Any] = TikHubClient,
) -> dict[str, Any]:
    platforms = [platform for platform in request.get("platforms") or [] if platform in REALTIME_PLATFORMS]
    unsupported = [platform for platform in request.get("platforms") or [] if platform not in REALTIME_PLATFORMS]
    keywords = _keywords_from_request(request)
    diagnostics = _diagnostics(enabled=True, platforms=platforms, unsupported_platforms=unsupported)
    if not platforms or not keywords:
        diagnostics["status"] = "skipped"
        return {"results": [], "diagnostics": diagnostics}

    client = client_factory()
    close = getattr(client, "close", None)
    creators: dict[tuple[str, str], dict[str, Any]] = {}
    malformed_count = 0
    failed_platforms: list[str] = []
    try:
        for platform in platforms:
            try:
                endpoint = get_endpoint(platform, Capability.SEARCH)
                for keyword in keywords:
                    payload = await _call_search(client, endpoint, keyword)
                    for item in _extract_items(payload):
                        normalized = _creator_from_content(platform, item, keyword)
                        if not normalized:
                            malformed_count += 1
                            continue
                        key = (normalized["platform"], normalized["creator_id"])
                        creators[key] = _merge_realtime_creator(creators.get(key), normalized)
            except Exception as exc:
                failed_platforms.append(platform)
                diagnostics["error"] = str(exc)
    finally:
        if close:
            await close()

    results = []
    for creator in creators.values():
        if not _passes_request_filters(creator, request):
            continue
        creator["match_score"] = _score_creator(creator, keywords)
        profile = await repository.upsert_creator_profile(_profile_payload(creator))
        candidate = await repository.upsert_creator_candidate(_candidate_payload(creator, request))
        diagnostics["created_profiles"] += 1 if profile else 0
        diagnostics["created_candidates"] += 1 if candidate else 0
        results.append(_result_payload(creator))

    results.sort(key=lambda item: item["match_score"], reverse=True)
    diagnostics["malformed_items"] = malformed_count
    diagnostics["failed_platforms"] = failed_platforms
    diagnostics["status"] = "partial" if failed_platforms and results else "failed" if failed_platforms else "ok"
    return {"results": results[: int(request.get("limit") or 50)], "diagnostics": diagnostics}


async def _call_search(client: Any, endpoint: Any, keyword: str) -> Any:
    payload = {**endpoint.default_params, endpoint.keyword_param: keyword}
    if endpoint.json_body:
        return await client.request(endpoint.method, endpoint.path, json=payload)
    return await client.request(endpoint.method, endpoint.path, params=payload)


def _keywords_from_request(request: dict[str, Any]) -> list[str]:
    raw = str(request.get("raw_query") or "").replace("+", " ")
    terms = [term.strip() for term in raw.replace(",", " ").split() if term.strip()]
    return terms or ([raw.strip()] if raw.strip() else [])


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "data", "list", "aweme_list", "notes"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested_items = _extract_items(value)
            if nested_items:
                return nested_items
    return []


def _creator_from_content(platform: str, item: dict[str, Any], keyword: str) -> dict[str, Any] | None:
    item = item.get("note") if platform == "xhs" and isinstance(item.get("note"), dict) else item
    item = item.get("aweme_info") if platform == "dy" and isinstance(item.get("aweme_info"), dict) else item
    user = author(item)
    if not isinstance(user, dict):
        return None
    creator_id = _creator_id(platform, user)
    if not creator_id:
        return None
    post = _representative_post(platform, item, keyword)
    return {
        "platform": platform,
        "creator_id": creator_id,
        "display_name": str(pick(user, "nickname", "nickName", "name", "unique_id", default=creator_id)),
        "profile_url": _profile_url(platform, creator_id),
        "bio": str(pick(user, "desc", "description", "bio", "signature", default="")),
        "follower_count": _to_int(pick(user, "fans", "fans_cnt", "followers_count", "follower_count", default=nested(user, "follow_info", "follower_count", default=None))),
        "following_count": _to_int(pick(user, "follows", "following_count", "favoriting_count", default=nested(user, "follow_info", "following_count", default=None))),
        "post_count": _to_int(pick(user, "notes_count", "note_count", "videos_count", "aweme_count", "posts_count", default=None)),
        "recent_post_count_30d": 1,
        "representative_posts": [post],
        "matched_keywords": [keyword],
        "engagement_total": _engagement_total(post["engagement"]),
    }


def _creator_id(platform: str, user: dict[str, Any]) -> str:
    if platform == "xhs":
        return str(pick(user, "user_id", "userId", "id", "userid", "red_id", default="")).strip()
    return str(pick(user, "sec_uid", "sec_user_id", "uid", "user_id", "id", default="")).strip()


def _representative_post(platform: str, item: dict[str, Any], keyword: str) -> dict[str, Any]:
    if platform == "xhs":
        engagement = {
            "liked_count": _to_int(nested(item, "interact_info", "liked_count", default=nested(item, "stats", "like_count", default=pick(item, "liked_count", "like_count", default=0)))),
            "comment_count": _to_int(nested(item, "interact_info", "comment_count", default=nested(item, "stats", "comment_count", default=pick(item, "comment_count", default=0)))),
            "collected_count": _to_int(nested(item, "interact_info", "collected_count", default=pick(item, "collected_count", "collect_count", default=0))),
            "share_count": _to_int(nested(item, "interact_info", "share_count", default=pick(item, "share_count", default=0))),
        }
        return {
            "platform_post_id": str(pick(item, "note_id", "noteId", "id", default="")),
            "title": str(pick(item, "title", "displayTitle", default="")),
            "content": str(pick(item, "desc", "content", "text", default="")),
            "url": str(pick(item, "note_url", "url", "share_url", default="")),
            "source_keyword": keyword,
            "engagement": engagement,
        }
    engagement = {
        "liked_count": _to_int(nested(item, "statistics", "digg_count", default=nested(item, "stats", "like_count", default=pick(item, "liked_count", "like_count", default=0)))),
        "comment_count": _to_int(nested(item, "statistics", "comment_count", default=pick(item, "comment_count", default=0))),
        "collected_count": _to_int(nested(item, "statistics", "collect_count", default=pick(item, "collect_count", default=0))),
        "share_count": _to_int(nested(item, "statistics", "share_count", default=pick(item, "share_count", default=0))),
    }
    return {
        "platform_post_id": str(pick(item, "aweme_id", "id", default="")),
        "title": str(pick(item, "desc", "title", "content", default="")),
        "content": str(pick(item, "desc", "title", "content", default="")),
        "url": str(pick(item, "share_url", "url", default="")),
        "source_keyword": keyword,
        "engagement": engagement,
    }


def _merge_realtime_creator(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if not existing:
        return incoming
    posts = existing["representative_posts"] + incoming["representative_posts"]
    keywords = sorted(set(existing["matched_keywords"] + incoming["matched_keywords"]))
    return {
        **existing,
        **{key: value for key, value in incoming.items() if value not in (None, "", 0, [])},
        "representative_posts": posts[:5],
        "matched_keywords": keywords,
        "recent_post_count_30d": min(30, int(existing.get("recent_post_count_30d") or 0) + 1),
        "engagement_total": int(existing.get("engagement_total") or 0) + int(incoming.get("engagement_total") or 0),
    }


def _score_creator(creator: dict[str, Any], keywords: list[str]) -> float:
    text = " ".join(
        [
            str(creator.get("display_name") or ""),
            str(creator.get("bio") or ""),
            *[str(post.get("title") or "") + " " + str(post.get("content") or "") for post in creator.get("representative_posts") or []],
        ]
    ).lower()
    matched = [keyword for keyword in keywords if keyword.lower() in text]
    keyword_score = min(65.0, 65.0 * len(matched) / max(1, len(keywords)))
    activity_score = min(20.0, 4.0 * len(creator.get("representative_posts") or []))
    engagement_score = min(15.0, float(creator.get("engagement_total") or 0) / 50.0)
    return round(min(100.0, keyword_score + activity_score + engagement_score), 4)


def _passes_request_filters(creator: dict[str, Any], request: dict[str, Any]) -> bool:
    follower_count = creator.get("follower_count")
    if request.get("follower_min") is not None and follower_count is not None and follower_count < int(request["follower_min"]):
        return False
    if request.get("follower_max") is not None and follower_count is not None and follower_count > int(request["follower_max"]):
        return False
    if request.get("recent_activity_min") is not None:
        if int(creator.get("recent_post_count_30d") or 0) < int(request["recent_activity_min"]):
            return False
    return True


def _profile_payload(creator: dict[str, Any]) -> dict[str, Any]:
    metrics = {
        "profile_metrics": {
            "interaction_count": creator.get("engagement_total") or 0,
        },
        "source": "tikhub_realtime",
    }
    return {
        "platform": creator["platform"],
        "creator_id": creator["creator_id"],
        "display_name": creator.get("display_name"),
        "profile_url": creator.get("profile_url"),
        "bio": creator.get("bio"),
        "follower_count": creator.get("follower_count"),
        "following_count": creator.get("following_count"),
        "post_count": creator.get("post_count"),
        "recent_post_count_30d": creator.get("recent_post_count_30d") or 0,
        "latest_snapshot_at": datetime.now(timezone.utc),
        "tag_summary_json": metrics,
    }


def _candidate_payload(creator: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": creator["platform"],
        "creator_id": creator["creator_id"],
        "pool_name": "realtime",
        "vertical_id": request.get("selected_vertical_id"),
        "match_score": creator.get("match_score"),
        "matched_tags_json": [
            {"source": "tikhub_realtime", "keyword": keyword}
            for keyword in creator.get("matched_keywords") or []
        ],
        "evidence_json": {
            "source": "tikhub_realtime",
            "raw_query": request.get("raw_query"),
            "representative_posts": creator.get("representative_posts") or [],
        },
        "notes": "Realtime discovery from TikHub search",
    }


def _result_payload(creator: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": creator["platform"],
        "creator_id": creator["creator_id"],
        "display_name": creator.get("display_name"),
        "profile_url": creator.get("profile_url"),
        "bio": creator.get("bio"),
        "follower_count": creator.get("follower_count"),
        "recent_post_count_30d": creator.get("recent_post_count_30d") or 0,
        "avg_engagement_rate": None,
        "hot_post_rate": None,
        "match_score": creator.get("match_score") or 0,
        "matched_tags": [
            {"source": "tikhub_realtime", "keyword": keyword}
            for keyword in creator.get("matched_keywords") or []
        ],
        "evidence": creator.get("representative_posts") or [],
        "representative_posts": creator.get("representative_posts") or [],
        "source_type": "realtime",
        "source_labels": ["Realtime"],
        "realtime_unverified": True,
    }


def _profile_url(platform: str, creator_id: str) -> str:
    if platform == "xhs":
        return f"https://www.xiaohongshu.com/user/profile/{creator_id}"
    return f"https://www.douyin.com/user/{creator_id}"


def _engagement_total(engagement: dict[str, Any]) -> int:
    return sum(_to_int(engagement.get(key)) for key in ("liked_count", "comment_count", "collected_count", "share_count"))


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _diagnostics(*, enabled: bool, platforms: list[str], unsupported_platforms: list[str]) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "status": "ok",
        "platforms": platforms,
        "unsupported_platforms": unsupported_platforms,
        "created_profiles": 0,
        "created_candidates": 0,
        "malformed_items": 0,
        "failed_platforms": [],
        "error": None,
    }
```

- [ ] **Step 4: Run realtime service tests**

Run:

```bash
pytest tests/test_realtime_creator_discovery.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add research/realtime_creator_discovery.py tests/test_realtime_creator_discovery.py
git commit -m "feat: add realtime creator discovery service"
```

---

### Task 3: Wire Realtime Search Into Unified Endpoint

**Files:**
- Modify: `research/creator_search.py`
- Test: `tests/test_creator_discovery_workflow_api.py`

- [ ] **Step 1: Write failing merge and failure tests**

Append these tests to `tests/test_creator_discovery_workflow_api.py`:

```python
def test_creator_search_include_realtime_merges_mixed_result(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    import api.routers.creator_search as creator_search_router
    import research.creator_search as creator_search_module

    class FakeRepository:
        async def list_tag_definitions(self, vertical_id=None, enabled_only=True):
            return []

        async def list_verticals(self, enabled_only=True):
            return []

        async def list_creator_profiles(self, platforms=None, limit=None):
            return [
                {
                    "platform": "xhs",
                    "creator_id": "same-1",
                    "display_name": "Database Name",
                    "profile_url": "https://www.xiaohongshu.com/user/profile/same-1",
                    "follower_count": None,
                    "recent_post_count_30d": 2,
                    "avg_engagement_rate": None,
                    "hot_post_rate": None,
                    "tag_summary_json": {},
                }
            ]

        async def list_entity_tags(self, **kwargs):
            return []

        async def list_posts_by_creator(self, platform, creator_id, limit=30):
            return [
                {
                    "platform": platform,
                    "platform_post_id": "p1",
                    "title": "K12 local",
                    "content": "K12 local evidence",
                    "publish_time": None,
                    "engagement_json": {"liked_count": 20},
                }
            ]

    async def fake_realtime(repository, request):
        return {
            "results": [
                {
                    "platform": "xhs",
                    "creator_id": "same-1",
                    "display_name": "Realtime Name",
                    "profile_url": "https://www.xiaohongshu.com/user/profile/same-1",
                    "follower_count": 5000,
                    "recent_post_count_30d": 6,
                    "match_score": 72,
                    "matched_tags": [{"source": "tikhub_realtime", "keyword": "K12"}],
                    "evidence": [],
                    "representative_posts": [{"title": "Realtime post"}],
                    "source_type": "realtime",
                    "source_labels": ["Realtime"],
                    "realtime_unverified": True,
                }
            ],
            "diagnostics": {
                "enabled": True,
                "status": "ok",
                "platforms": ["xhs"],
                "unsupported_platforms": [],
                "created_profiles": 1,
                "created_candidates": 1,
                "error": None,
            },
        }

    monkeypatch.setattr(creator_search_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(creator_search_module, "discover_realtime_creators", fake_realtime)
    client = TestClient(app)

    response = client.post(
        "/api/creator-search/search",
        json={"raw_query": "K12", "platforms": ["xhs"], "include_realtime": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["results"]) == 1
    row = payload["results"][0]
    assert row["source_type"] == "mixed"
    assert row["source_labels"] == ["Database", "Realtime"]
    assert row["follower_count"] == 5000
    assert row["realtime_unverified"] is False
    assert payload["realtime"]["status"] == "ok"


def test_creator_search_realtime_failure_returns_local_results(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    import api.routers.creator_search as creator_search_router
    import research.creator_search as creator_search_module

    class FakeRepository:
        async def list_tag_definitions(self, vertical_id=None, enabled_only=True):
            return []

        async def list_verticals(self, enabled_only=True):
            return []

        async def list_creator_profiles(self, platforms=None, limit=None):
            return [
                {
                    "platform": "xhs",
                    "creator_id": "local-1",
                    "display_name": "Local Teacher",
                    "profile_url": "https://www.xiaohongshu.com/user/profile/local-1",
                    "follower_count": 1000,
                    "recent_post_count_30d": 2,
                    "avg_engagement_rate": None,
                    "hot_post_rate": None,
                    "tag_summary_json": {},
                }
            ]

        async def list_entity_tags(self, **kwargs):
            return []

        async def list_posts_by_creator(self, platform, creator_id, limit=30):
            return [{"title": "K12", "content": "K12", "engagement_json": {}}]

    async def failing_realtime(repository, request):
        raise RuntimeError("TikHub unavailable")

    monkeypatch.setattr(creator_search_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(creator_search_module, "discover_realtime_creators", failing_realtime)
    client = TestClient(app)

    response = client.post(
        "/api/creator-search/search",
        json={"raw_query": "K12", "platforms": ["xhs"], "include_realtime": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["source_type"] == "local"
    assert payload["realtime"]["status"] == "failed"
    assert "TikHub unavailable" in payload["realtime"]["error"]
```

- [ ] **Step 2: Run the new API tests to verify they fail**

Run:

```bash
pytest tests/test_creator_discovery_workflow_api.py::test_creator_search_include_realtime_merges_mixed_result tests/test_creator_discovery_workflow_api.py::test_creator_search_realtime_failure_returns_local_results -v
```

Expected: FAIL because realtime service is not wired into `search_creators`.

- [ ] **Step 3: Import and call realtime service**

At the top of `research/creator_search.py`, add:

```python
from research.realtime_creator_discovery import discover_realtime_creators
```

At the end of `search_creators`, before the final `return`, replace the local-only final result handling with:

```python
    results.sort(key=lambda item: item["match_score"], reverse=True)
    results = _dedupe_creator_results(results)
    realtime_diagnostics = _realtime_skipped_diagnostics()
    if request.get("include_realtime"):
        try:
            realtime = await discover_realtime_creators(repository, request)
            realtime_diagnostics = realtime["diagnostics"]
            results = _merge_creator_result_sources(results, realtime.get("results") or [])
        except Exception as exc:
            realtime_diagnostics = {
                **_realtime_skipped_diagnostics(),
                "enabled": True,
                "status": "failed",
                "platforms": request.get("platforms") or [],
                "error": str(exc),
            }
    diagnostics["guidance"] = _creator_search_guidance(
        profile_count=diagnostics["profile_count"],
        result_count=len(results),
        matched_tag_count=diagnostics["matched_tag_count"],
        fallback_used=diagnostics["fallback_used"],
    )
    return {
        "intent": intent,
        "diagnostics": diagnostics,
        "realtime": realtime_diagnostics,
        "progress": _complete_progress(),
        "results": results[: int(request.get("limit") or 50)],
    }
```

- [ ] **Step 4: Add merge helper**

In `research/creator_search.py`, add:

```python
def _merge_creator_result_sources(
    local_results: list[dict[str, Any]],
    realtime_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    for item in local_results:
        key = _creator_identity_key(item)
        index[key] = item
        merged.append(item)
    for realtime in realtime_results:
        key = _creator_identity_key(realtime)
        local = index.get(key)
        if local is None:
            merged.append(realtime)
            index[key] = realtime
            continue
        local.update(_fill_missing_profile_fields(local, realtime))
        local["source_type"] = "mixed"
        local["source_labels"] = ["Database", "Realtime"]
        local["realtime_unverified"] = False
        if not local.get("representative_posts") and realtime.get("representative_posts"):
            local["representative_posts"] = realtime["representative_posts"]
        if realtime.get("matched_tags"):
            local["matched_tags"] = (local.get("matched_tags") or []) + realtime["matched_tags"]
    merged.sort(key=lambda item: float(item.get("match_score") or 0), reverse=True)
    return _dedupe_creator_results(merged)


def _creator_identity_key(item: dict[str, Any]) -> str:
    platform = str(item.get("platform") or "")
    creator_id = str(item.get("creator_id") or "")
    if platform and creator_id:
        return f"id:{platform}:{creator_id}"
    profile_url = str(item.get("profile_url") or "").strip()
    if profile_url:
        return f"url:{profile_url}"
    display_name = str(item.get("display_name") or "").strip()
    return f"name:{platform}:{display_name}"


def _fill_missing_profile_fields(local: dict[str, Any], realtime: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "display_name",
        "profile_url",
        "bio",
        "follower_count",
        "recent_post_count_30d",
        "avg_engagement_rate",
        "hot_post_rate",
    )
    return {
        field: realtime[field]
        for field in fields
        if local.get(field) in (None, "", 0) and realtime.get(field) not in (None, "", 0)
    }
```

- [ ] **Step 5: Run unified API tests**

Run:

```bash
pytest tests/test_creator_discovery_workflow_api.py::test_creator_search_local_only_adds_database_source tests/test_creator_discovery_workflow_api.py::test_creator_search_include_realtime_merges_mixed_result tests/test_creator_discovery_workflow_api.py::test_creator_search_realtime_failure_returns_local_results -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add research/creator_search.py tests/test_creator_discovery_workflow_api.py
git commit -m "feat: merge realtime creator search results"
```

---

### Task 4: Add Frontend Checkbox, Progress, And Badges

**Files:**
- Modify: `api/webui/src/pages/ResearchModulePages.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Add response and progress types**

In `api/webui/src/pages/ResearchModulePages.tsx`, replace `CreatorSearchResponse` with:

```ts
type CreatorSearchProgress = {
  stage: string;
  label: string;
  percent: number;
};

type CreatorSearchRealtimeDiagnostics = {
  enabled?: boolean;
  status?: string;
  platforms?: string[];
  unsupported_platforms?: string[];
  created_profiles?: number;
  created_candidates?: number;
  error?: string | null;
};

type CreatorSearchResponse = {
  intent?: UnknownRecord | null;
  diagnostics?: UnknownRecord;
  realtime?: CreatorSearchRealtimeDiagnostics;
  progress?: CreatorSearchProgress;
  results: UnknownRecord[];
};
```

- [ ] **Step 2: Add component state and staged progress helpers**

Inside `CreatorDiscoveryPage`, after `const [searching, setSearching] = React.useState(false);`, add:

```ts
  const [includeRealtime, setIncludeRealtime] = React.useState(false);
  const [searchProgress, setSearchProgress] = React.useState<CreatorSearchProgress | null>(null);
  const [resultsUpdating, setResultsUpdating] = React.useState(false);
```

Add helper functions near `creatorRowKey`:

```ts
function creatorSearchStage(stage: string): CreatorSearchProgress {
  const stages: Record<string, CreatorSearchProgress> = {
    database: { stage: "database", label: "Searching database", percent: 20 },
    realtime: { stage: "realtime", label: "Searching realtime platforms", percent: 50 },
    persistence: { stage: "persistence", label: "Saving creator profiles", percent: 75 },
    merging: { stage: "merging", label: "Merging results", percent: 90 },
    complete: { stage: "complete", label: "Complete", percent: 100 },
  };
  return stages[stage] || stages.database;
}

function creatorSourceLabels(row: UnknownRecord) {
  const labels = textArray(row.source_labels);
  if (labels.length) return labels;
  const source = text(row.source_type, "local");
  if (source === "realtime") return ["Realtime"];
  if (source === "mixed") return ["Database", "Realtime"];
  return ["Database"];
}
```

- [ ] **Step 3: Send include_realtime and update progress during search**

In `runCreatorSearch`, update the start and payload:

```ts
    setSearching(true);
    setResultsUpdating(Boolean(searchResult));
    setSearchProgress(includeRealtime ? creatorSearchStage("database") : null);
```

Before `const response = await api<CreatorSearchResponse>`, add:

```ts
      if (includeRealtime) {
        await sleepMs(150);
        setSearchProgress(creatorSearchStage("realtime"));
      }
```

In the request body, add:

```ts
          include_realtime: includeRealtime,
```

After receiving the response but before `setSearchResult(response);`, add:

```ts
      if (includeRealtime) {
        setSearchProgress(creatorSearchStage("persistence"));
        await sleepMs(100);
        setSearchProgress(creatorSearchStage("merging"));
        await sleepMs(100);
      }
      setSearchProgress(response.progress || creatorSearchStage("complete"));
```

In `finally`, add:

```ts
      setResultsUpdating(false);
```

- [ ] **Step 4: Add the checkbox and progress UI**

In the creator search form, inside the platform/filter controls before the buttons, add:

```tsx
          <label className="creator-realtime-toggle">
            <input
              type="checkbox"
              checked={includeRealtime}
              onChange={(event) => setIncludeRealtime(event.target.checked)}
              disabled={searching}
            />
            <span>实时搜索小红书/抖音</span>
          </label>
```

Below the button row, add:

```tsx
          {includeRealtime && (searching || searchProgress) && (
            <div className="creator-search-progress">
              <div>
                <span>{searchProgress?.label || "Preparing realtime search"}</span>
                <strong>{formatNumber(searchProgress?.percent || 0)}%</strong>
              </div>
              <div className="creator-search-progress-track">
                <i style={{ width: `${Math.min(100, Math.max(4, searchProgress?.percent || 4))}%` }} />
              </div>
            </div>
          )}
```

- [ ] **Step 5: Render badges and realtime warning**

Where candidate/result rows are rendered in `CreatorDiscoveryPage`, add badges near the row title:

```tsx
                <div className="creator-source-badges">
                  {creatorSourceLabels(item).map((label) => (
                    <Badge key={label} tone={label === "Realtime" ? "warning" : "success"}>{label === "Database" ? "数据库" : "实时"}</Badge>
                  ))}
                </div>
```

Add a warning after the form:

```tsx
        {searchResult?.realtime && ["failed", "partial"].includes(text(searchResult.realtime.status, "")) && (
          <div className="creator-realtime-warning">
            <AlertTriangle size={16} />
            <span>{text(searchResult.realtime.error, "实时搜索部分失败，已展示可用的数据库结果。")}</span>
          </div>
        )}
```

Add updating class to the result list wrapper:

```tsx
        <div className={`module-list ${resultsUpdating ? "is-updating" : ""}`}>
```

- [ ] **Step 6: Add styles**

In `api/webui/src/styles.css`, near `.creator-search-form` styles, add:

```css
.creator-realtime-toggle {
  align-items: center;
  display: inline-flex;
  gap: 8px;
  min-height: 36px;
}

.creator-realtime-toggle input {
  height: 16px;
  width: 16px;
}

.creator-search-progress {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  display: grid;
  gap: 8px;
  padding: 10px 12px;
}

.creator-search-progress > div:first-child {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

.creator-search-progress span,
.creator-search-progress strong {
  font-size: 13px;
}

.creator-search-progress-track {
  background: #e5e7eb;
  border-radius: 999px;
  height: 8px;
  overflow: hidden;
}

.creator-search-progress-track i {
  background: #04786f;
  display: block;
  height: 100%;
  transition: width 180ms ease;
}

.creator-source-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.creator-realtime-warning {
  align-items: center;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  color: #9a3412;
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding: 10px 12px;
}

.module-list.is-updating {
  opacity: 0.62;
}
```

- [ ] **Step 7: Run frontend build**

Run:

```bash
npm.cmd run build
```

Expected: PASS. If TypeScript fails on exact JSX placement, inspect `CreatorDiscoveryPage` and move the snippets into the existing result-card structure without changing behavior.

- [ ] **Step 8: Commit**

```bash
git add api/webui/src/pages/ResearchModulePages.tsx api/webui/src/styles.css
git commit -m "feat: add realtime creator search progress UI"
```

---

### Task 5: Final Verification

**Files:**
- Verify only unless tests reveal a defect.

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
pytest tests/test_realtime_creator_discovery.py tests/test_creator_discovery_workflow_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 3: Start the dev server**

Run:

```bash
npm.cmd run dev
```

Expected: Vite starts and prints a local URL, usually `http://127.0.0.1:5173/`.

- [ ] **Step 4: Browser smoke check**

Open the local URL in Browser, navigate to the Research Console creator discovery page, and verify:

- Checkbox is visible and off by default.
- Checking it and searching shows the progress bar.
- Result cards show `数据库`, `实时`, or both depending on API data.
- Partial/failed realtime diagnostics show a warning without hiding local results.

- [ ] **Step 5: Commit any verification fixes**

If Step 1-4 required code changes:

```bash
git add research api tests
git commit -m "fix: stabilize realtime creator search"
```

If no fixes were required, do not create an empty commit.
