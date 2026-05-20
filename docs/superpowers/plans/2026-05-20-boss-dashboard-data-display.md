# Boss Dashboard Data Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `/research` from a feature-entry console into a mixed boss dashboard with decision summary, monitoring cards, balanced opportunity board, detail drawer, and lightweight execution confirmation.

**Architecture:** Add a backend dashboard aggregation layer that converts existing research jobs, creator candidates, keyword heat snapshots, competitor composition snapshots, and content tracking snapshots into a single report payload. The React homepage consumes this payload and renders decision summary, action suggestions, monitoring cards, opportunity board, detail drawer, and confirmation modal while reusing existing execution APIs.

**Tech Stack:** FastAPI, Pydantic-compatible dict responses, SQLAlchemy async repository methods, pytest, Vite + React + TypeScript, Recharts, lucide-react.

---

## Scope Check

This plan is one coherent vertical slice: boss dashboard data display. It touches backend aggregation, one new API endpoint, the React overview page, and focused tests. It does not implement a full BI builder, permission system, export redesign, or production crawler orchestration.

## File Structure

- Create `research/dashboard.py`
  - Owns dashboard payload construction.
  - Defines pure functions for decision summary, action suggestions, monitoring cards, opportunity scoring, detail payloads, and sample-state copy.
  - Keeps scoring deterministic and easy to unit test.

- Modify `research/repository.py`
  - Add read methods only if needed by the dashboard endpoint.
  - Reuse existing list methods whenever available.

- Modify `api/routers/reports.py`
  - Add `GET /api/reports/dashboard-summary`.
  - Keep existing report endpoints unchanged.

- Create `tests/test_dashboard_summary.py`
  - Unit tests for `research.dashboard`.

- Modify `tests/test_content_tracking_api.py` or create `tests/test_dashboard_api.py`
  - API test for `/api/reports/dashboard-summary`.
  - Prefer a new focused file if monkeypatching becomes noisy.

- Modify `api/webui/src/main.tsx`
  - Add TypeScript types for dashboard payload.
  - Add dashboard loader state in `App`.
  - Replace `GrowthOverviewPage` internals with the new mixed dashboard.
  - Add detail drawer and confirmation modal components in the same file for now, because this app currently uses a single-file frontend.

- Modify `api/webui/src/styles.css`
  - Add styles for decision cards, opportunity board, drawer, confirmation modal, confidence chips, and responsive layout.

## Data Contracts

Backend endpoint:

```text
GET /api/reports/dashboard-summary?vertical_id=&scene_pack_id=&platform=
```

Response shape:

```json
{
  "decision": {
    "headline": "当前样本不足，建议先执行一次实时发现形成首批样本。",
    "confidence": "low",
    "sample_status": "insufficient",
    "sample_summary": "24h 内容 0 条，7d 趋势样本不足。",
    "risk_notes": ["样本不足，暂不输出确定性推流判断。"],
    "evidence_count": 0
  },
  "actions": {
    "do_now": [
      {
        "title": "执行一次实时发现",
        "reason": "当前样本不足，需要先采集关键词和达人基础数据。",
        "target_type": "keyword",
        "action": "search_now",
        "payload": {"keywords": ["K12教育", "单亲妈妈"]}
      }
    ],
    "watch_today": [],
    "defer": []
  },
  "monitoring": {
    "running_jobs": 0,
    "today_collected": 0,
    "errors": 0,
    "monitor_pools": 0,
    "realtime_jobs": 0,
    "last_updated_at": null
  },
  "opportunities": []
}
```

Opportunity item shape:

```json
{
  "id": "keyword:xhs:K12教育",
  "type": "keyword",
  "name": "K12教育",
  "platform": "xhs",
  "score": 86.5,
  "change_24h": 18.2,
  "trend_7d": 9.4,
  "confidence": "medium",
  "reason": "24h 内容量高于 7d 均值，互动增长同步上升。",
  "evidence_count": 6,
  "actions": ["view_detail", "monitor", "crawl_now"],
  "payload": {
    "keyword": "K12教育",
    "platform": "xhs"
  },
  "detail": {
    "summary": ["24h 内容量高于 7d 均值。"],
    "trend_30d": [],
    "evidence": []
  }
}
```

## Task 1: Backend Dashboard Builder

**Files:**
- Create: `research/dashboard.py`
- Test: `tests/test_dashboard_summary.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_dashboard_summary.py`:

```python
from research.dashboard import build_dashboard_summary


def test_dashboard_summary_returns_conservative_empty_state():
    summary = build_dashboard_summary(
        jobs=[],
        creator_candidates=[],
        keyword_heat_snapshots=[],
        competitor_compositions=[],
        content_snapshots=[],
        monitor_pools=[],
        platform=None,
    )

    assert summary["decision"]["sample_status"] == "insufficient"
    assert summary["decision"]["confidence"] == "low"
    assert "样本不足" in summary["decision"]["headline"]
    assert summary["actions"]["do_now"][0]["action"] == "search_now"
    assert summary["opportunities"] == []


def test_dashboard_summary_ranks_balanced_opportunities():
    summary = build_dashboard_summary(
        jobs=[{"id": 1, "status": "running"}],
        creator_candidates=[
            {
                "platform": "xhs",
                "creator_id": "creator-1",
                "display_name": "K12妈妈号",
                "match_score": 92,
                "recent_post_count_30d": 12,
                "hot_post_rate": 0.3,
                "evidence": [{"text": "主词命中"}],
            }
        ],
        keyword_heat_snapshots=[
            {
                "keyword": "K12教育",
                "platform": "xhs",
                "heat_score": 88,
                "growth_score": 20,
                "platform_signal": "boosting",
                "evidence": {"items": ["24h 内容量上升"]},
            }
        ],
        competitor_compositions=[
            {
                "competitor_id": 2,
                "platform": "xhs",
                "total_flow_count": 5000,
                "hot_post_rate": 0.4,
                "keyword_distribution": {"升学规划": 6},
                "evidence": {"top_posts": [{"title": "升学规划爆款"}]},
            }
        ],
        content_snapshots=[
            {
                "tracker_id": 3,
                "platform": "xhs",
                "total_content_count": 30,
                "hot_post_rate": 0.25,
                "keyword_distribution": {"单亲妈妈": 8},
                "evidence": {"top_posts": [{"title": "陪读焦虑"}]},
            }
        ],
        monitor_pools=[{"id": 1, "name": "K12达人池"}],
        platform="xhs",
    )

    assert summary["decision"]["sample_status"] == "enough"
    assert summary["monitoring"]["running_jobs"] == 1
    assert summary["monitoring"]["monitor_pools"] == 1
    assert len(summary["opportunities"]) == 4
    assert summary["opportunities"][0]["score"] >= summary["opportunities"][-1]["score"]
    assert all(item["reason"] for item in summary["opportunities"])
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m pytest tests\test_dashboard_summary.py -q
```

Expected:

```text
FAILED tests/test_dashboard_summary.py
ModuleNotFoundError: No module named 'research.dashboard'
```

- [ ] **Step 3: Implement the dashboard builder**

Create `research/dashboard.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_dashboard_summary(
    *,
    jobs: list[dict[str, Any]],
    creator_candidates: list[dict[str, Any]],
    keyword_heat_snapshots: list[dict[str, Any]],
    competitor_compositions: list[dict[str, Any]],
    content_snapshots: list[dict[str, Any]],
    monitor_pools: list[dict[str, Any]],
    platform: str | None,
) -> dict[str, Any]:
    opportunities = _build_opportunities(
        creator_candidates=creator_candidates,
        keyword_heat_snapshots=keyword_heat_snapshots,
        competitor_compositions=competitor_compositions,
        content_snapshots=content_snapshots,
    )
    monitoring = _build_monitoring(
        jobs=jobs,
        monitor_pools=monitor_pools,
        keyword_heat_snapshots=keyword_heat_snapshots,
        competitor_compositions=competitor_compositions,
        content_snapshots=content_snapshots,
    )
    decision = _build_decision(
        opportunities=opportunities,
        monitoring=monitoring,
        platform=platform,
    )
    return {
        "decision": decision,
        "actions": _build_actions(opportunities=opportunities, decision=decision),
        "monitoring": monitoring,
        "opportunities": opportunities,
    }


def _build_monitoring(
    *,
    jobs: list[dict[str, Any]],
    monitor_pools: list[dict[str, Any]],
    keyword_heat_snapshots: list[dict[str, Any]],
    competitor_compositions: list[dict[str, Any]],
    content_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    running_jobs = sum(1 for item in jobs if item.get("status") == "running")
    errors = sum(1 for item in jobs if item.get("status") in {"failed", "error"})
    today_collected = sum(int(item.get("total_content_count") or 0) for item in content_snapshots)
    today_collected += sum(int(item.get("total_flow_count") or 0) for item in competitor_compositions)
    realtime_jobs = sum(1 for item in jobs if item.get("collection_mode") == "search" and item.get("status") == "running")
    last_updated_at = _latest_timestamp(
        keyword_heat_snapshots + competitor_compositions + content_snapshots
    )
    return {
        "running_jobs": running_jobs,
        "today_collected": today_collected,
        "errors": errors,
        "monitor_pools": len(monitor_pools),
        "realtime_jobs": realtime_jobs,
        "last_updated_at": last_updated_at,
    }


def _build_decision(
    *,
    opportunities: list[dict[str, Any]],
    monitoring: dict[str, Any],
    platform: str | None,
) -> dict[str, Any]:
    evidence_count = sum(int(item.get("evidence_count") or 0) for item in opportunities)
    if not opportunities:
        return {
            "headline": "当前样本不足，建议先执行一次实时发现形成首批样本。",
            "confidence": "low",
            "sample_status": "insufficient",
            "sample_summary": "24h 与 7d 样本不足，暂不输出确定性判断。",
            "risk_notes": ["样本不足，暂不输出确定性推流判断。"],
            "evidence_count": 0,
        }

    top = opportunities[0]
    sample_status = "enough" if evidence_count >= 3 else "limited"
    confidence = "high" if top["score"] >= 85 and evidence_count >= 6 else "medium"
    platform_text = f"{platform} 平台" if platform else "当前平台"
    return {
        "headline": f"{platform_text}今日优先关注「{top['name']}」，{top['reason']}",
        "confidence": confidence,
        "sample_status": sample_status,
        "sample_summary": f"已形成 {len(opportunities)} 条机会线索，证据 {evidence_count} 条。",
        "risk_notes": [] if sample_status == "enough" else ["证据数量有限，执行前建议查看详情。"],
        "evidence_count": evidence_count,
    }


def _build_actions(
    *,
    opportunities: list[dict[str, Any]],
    decision: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    if not opportunities:
        return {
            "do_now": [
                {
                    "title": "执行一次实时发现",
                    "reason": "当前样本不足，需要先采集关键词和达人基础数据。",
                    "target_type": "keyword",
                    "action": "search_now",
                    "payload": {"keywords": ["K12教育", "单亲妈妈"]},
                }
            ],
            "watch_today": [],
            "defer": [
                {
                    "title": "暂缓确定性投放判断",
                    "reason": decision["sample_summary"],
                    "target_type": "report",
                    "action": "view_detail",
                    "payload": {},
                }
            ],
        }

    do_now = [
        {
            "title": f"处理 {item['name']}",
            "reason": item["reason"],
            "target_type": item["type"],
            "action": item["actions"][-1],
            "payload": item["payload"],
        }
        for item in opportunities[:2]
    ]
    watch_today = [
        {
            "title": f"观察 {item['name']}",
            "reason": item["reason"],
            "target_type": item["type"],
            "action": "view_detail",
            "payload": item["payload"],
        }
        for item in opportunities[2:5]
    ]
    return {"do_now": do_now, "watch_today": watch_today, "defer": []}


def _build_opportunities(
    *,
    creator_candidates: list[dict[str, Any]],
    keyword_heat_snapshots: list[dict[str, Any]],
    competitor_compositions: list[dict[str, Any]],
    content_snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items = []
    items.extend(_creator_opportunity(item) for item in creator_candidates)
    items.extend(_keyword_opportunity(item) for item in keyword_heat_snapshots)
    items.extend(_competitor_opportunity(item) for item in competitor_compositions)
    items.extend(_content_opportunity(item) for item in content_snapshots)
    items.sort(key=lambda item: item["score"], reverse=True)
    return items[:20]


def _creator_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    score = min(100.0, float(item.get("match_score") or 0) * 0.7 + float(item.get("recent_post_count_30d") or 0) * 1.0 + float(item.get("hot_post_rate") or 0) * 40)
    name = item.get("display_name") or item.get("creator_id") or "未命名达人"
    platform = item.get("platform")
    return {
        "id": f"creator:{platform}:{item.get('creator_id')}",
        "type": "creator",
        "name": name,
        "platform": platform,
        "score": round(score, 2),
        "change_24h": 0.0,
        "trend_7d": float(item.get("recent_post_count_30d") or 0),
        "confidence": _confidence(score, len(item.get("evidence") or [])),
        "reason": "主词匹配较高且近期持续发帖，适合优先复核并加入监控。",
        "evidence_count": len(item.get("evidence") or []),
        "actions": ["view_detail", "monitor", "crawl_now"],
        "payload": {
            "platform": platform,
            "creator_id": item.get("creator_id"),
            "display_name": name,
        },
        "detail": {
            "summary": [f"匹配分 {item.get('match_score', 0)}。"],
            "trend_30d": [],
            "evidence": item.get("evidence") or [],
        },
    }


def _keyword_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    score = min(100.0, float(item.get("heat_score") or 0) * 0.75 + float(item.get("growth_score") or 0) * 0.25)
    keyword = item.get("keyword") or item.get("tag_name") or str(item.get("tag_id") or "关键词")
    evidence = item.get("evidence") or {}
    evidence_count = len(evidence.get("items") or evidence.get("evidence") or evidence) if isinstance(evidence, dict) else 0
    return {
        "id": f"keyword:{item.get('platform')}:{keyword}",
        "type": "keyword",
        "name": keyword,
        "platform": item.get("platform"),
        "score": round(score, 2),
        "change_24h": float(item.get("growth_score") or 0),
        "trend_7d": float(item.get("heat_score") or 0),
        "confidence": _confidence(score, evidence_count),
        "reason": f"热度分 {round(float(item.get('heat_score') or 0), 1)}，平台信号为 {item.get('platform_signal') or 'normal'}。",
        "evidence_count": evidence_count,
        "actions": ["view_detail", "monitor", "crawl_now"],
        "payload": {
            "platform": item.get("platform"),
            "keyword": keyword,
        },
        "detail": {
            "summary": [f"平台信号：{item.get('platform_signal') or 'normal'}。"],
            "trend_30d": [],
            "evidence": evidence,
        },
    }


def _competitor_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    score = min(100.0, float(item.get("total_flow_count") or 0) / 80 + float(item.get("hot_post_rate") or 0) * 45)
    name = f"友商 #{item.get('competitor_id')}"
    evidence = item.get("evidence") or {}
    top_posts = evidence.get("top_posts") or []
    return {
        "id": f"competitor:{item.get('platform')}:{item.get('competitor_id')}",
        "type": "competitor",
        "name": name,
        "platform": item.get("platform"),
        "score": round(score, 2),
        "change_24h": float(item.get("total_flow_count") or 0),
        "trend_7d": float(item.get("hot_post_rate") or 0) * 100,
        "confidence": _confidence(score, len(top_posts)),
        "reason": "友商流量组成出现可复盘样本，建议查看关键词和爆款内容结构。",
        "evidence_count": len(top_posts),
        "actions": ["view_detail", "monitor", "crawl_now"],
        "payload": {
            "platform": item.get("platform"),
            "competitor_id": item.get("competitor_id"),
        },
        "detail": {
            "summary": [f"总互动 {item.get('total_flow_count', 0)}，爆款率 {item.get('hot_post_rate', 0)}。"],
            "trend_30d": [],
            "evidence": evidence,
        },
    }


def _content_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    score = min(100.0, float(item.get("total_content_count") or 0) * 1.5 + float(item.get("hot_post_rate") or 0) * 50)
    name = f"内容追踪 #{item.get('tracker_id')}"
    evidence = item.get("evidence") or {}
    top_posts = evidence.get("top_posts") or []
    return {
        "id": f"content:{item.get('platform')}:{item.get('tracker_id')}",
        "type": "content",
        "name": name,
        "platform": item.get("platform"),
        "score": round(score, 2),
        "change_24h": float(item.get("total_content_count") or 0),
        "trend_7d": float(item.get("hot_post_rate") or 0) * 100,
        "confidence": _confidence(score, len(top_posts)),
        "reason": "同类内容已有可观察样本，适合继续追踪关键词命中和爆款结构。",
        "evidence_count": len(top_posts),
        "actions": ["view_detail", "monitor", "crawl_now"],
        "payload": {
            "platform": item.get("platform"),
            "tracker_id": item.get("tracker_id"),
        },
        "detail": {
            "summary": [f"匹配内容 {item.get('total_content_count', 0)} 条。"],
            "trend_30d": [],
            "evidence": evidence,
        },
    }


def _confidence(score: float, evidence_count: int) -> str:
    if score >= 85 and evidence_count >= 3:
        return "high"
    if score >= 60 or evidence_count >= 1:
        return "medium"
    return "low"


def _latest_timestamp(items: list[dict[str, Any]]) -> str | None:
    values = [
        item.get("created_at") or item.get("snapshot_date")
        for item in items
        if item.get("created_at") or item.get("snapshot_date")
    ]
    if not values:
        return None
    latest = max(str(value) for value in values)
    return latest or datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Run unit tests**

Run:

```bash
python -m pytest tests\test_dashboard_summary.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add research/dashboard.py tests/test_dashboard_summary.py
git commit -m "feat: build boss dashboard summary payload"
```

## Task 2: Dashboard Summary API

**Files:**
- Modify: `api/routers/reports.py`
- Test: `tests/test_dashboard_api.py`

- [ ] **Step 1: Write API test**

Create `tests/test_dashboard_api.py`:

```python
from fastapi.testclient import TestClient

import config
from api.main import app


def test_dashboard_summary_api_returns_payload(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_jobs(self):
            return [{"id": 1, "status": "running", "collection_mode": "search"}]

        async def list_creator_candidates(self, vertical_id=None, platform=None, pool_name=None):
            return [{"platform": "xhs", "creator_id": "a1", "display_name": "K12妈妈号", "match_score": 90, "evidence": [{"text": "命中"}]}]

        async def list_keyword_heat_snapshots(self, vertical_id=None, scene_pack_id=None, platform=None, limit=None):
            return [{"keyword": "K12教育", "platform": "xhs", "heat_score": 85, "growth_score": 20, "platform_signal": "boosting", "evidence": {"items": ["增长"]}}]

        async def list_competitor_composition_snapshots(self, competitor_id=None, platform=None, limit=None):
            return [{"competitor_id": 1, "platform": "xhs", "total_flow_count": 3000, "hot_post_rate": 0.2, "evidence": {"top_posts": [{"title": "爆款"}]}}]

        async def list_content_tracking_snapshots(self, tracker_id=None, platform=None, limit=None):
            return [{"tracker_id": 1, "platform": "xhs", "total_content_count": 12, "hot_post_rate": 0.1, "evidence": {"top_posts": [{"title": "同类"}]}}]

        async def list_monitor_pools(self, enabled_only=False):
            return [{"id": 1, "name": "K12池"}]

    import api.routers.reports as reports_router

    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/reports/dashboard-summary?platform=xhs")

    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["sample_status"] == "enough"
    assert body["monitoring"]["running_jobs"] == 1
    assert body["opportunities"][0]["reason"]
```

- [ ] **Step 2: Run API test and verify failure**

Run:

```bash
python -m pytest tests\test_dashboard_api.py -q
```

Expected:

```text
FAILED
assert 404 == 200
```

- [ ] **Step 3: Add the API route**

Modify `api/routers/reports.py`:

```python
from research.dashboard import build_dashboard_summary
```

Add this route below `get_boss_summary_report`:

```python
@router.get("/dashboard-summary")
async def get_dashboard_summary(
    vertical_id: int | None = None,
    scene_pack_id: int | None = None,
    platform: str | None = None,
):
    require_research_database()
    repository = ResearchRepository()
    return build_dashboard_summary(
        jobs=await _maybe_call(repository, "list_jobs", default=[]),
        creator_candidates=await repository.list_creator_candidates(
            vertical_id=vertical_id,
            platform=platform,
        ),
        keyword_heat_snapshots=await _maybe_call(
            repository,
            "list_keyword_heat_snapshots",
            vertical_id=vertical_id,
            scene_pack_id=scene_pack_id,
            platform=platform,
            limit=50,
            default=[],
        ),
        competitor_compositions=await _maybe_call(
            repository,
            "list_competitor_composition_snapshots",
            platform=platform,
            limit=50,
            default=[],
        ),
        content_snapshots=await _maybe_call(
            repository,
            "list_content_tracking_snapshots",
            platform=platform,
            limit=50,
            default=[],
        ),
        monitor_pools=await _maybe_call(
            repository,
            "list_monitor_pools",
            enabled_only=True,
            default=[],
        ),
        platform=platform,
    )
```

- [ ] **Step 4: Run API test**

Run:

```bash
python -m pytest tests\test_dashboard_api.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Run report regressions**

Run:

```bash
python -m pytest tests\test_content_tracking_api.py tests\test_dashboard_api.py tests\test_dashboard_summary.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add api/routers/reports.py tests/test_dashboard_api.py
git commit -m "feat: expose boss dashboard summary api"
```

## Task 3: Frontend Dashboard Types and Loader

**Files:**
- Modify: `api/webui/src/main.tsx`

- [ ] **Step 1: Add dashboard types**

In `api/webui/src/main.tsx`, near the existing `GrowthReport` type, add:

```ts
type DashboardConfidence = "low" | "medium" | "high";
type DashboardSampleStatus = "insufficient" | "limited" | "enough";
type DashboardAction = {
  title: string;
  reason: string;
  target_type: string;
  action: string;
  payload: Record<string, unknown>;
};
type DashboardOpportunity = {
  id: string;
  type: "creator" | "keyword" | "competitor" | "content";
  name: string;
  platform?: string | null;
  score: number;
  change_24h: number;
  trend_7d: number;
  confidence: DashboardConfidence;
  reason: string;
  evidence_count: number;
  actions: string[];
  payload: Record<string, unknown>;
  detail: {
    summary: string[];
    trend_30d: Array<Record<string, unknown>>;
    evidence: unknown;
  };
};
type DashboardSummary = {
  decision: {
    headline: string;
    confidence: DashboardConfidence;
    sample_status: DashboardSampleStatus;
    sample_summary: string;
    risk_notes: string[];
    evidence_count: number;
  };
  actions: {
    do_now: DashboardAction[];
    watch_today: DashboardAction[];
    defer: DashboardAction[];
  };
  monitoring: {
    running_jobs: number;
    today_collected: number;
    errors: number;
    monitor_pools: number;
    realtime_jobs: number;
    last_updated_at?: string | null;
  };
  opportunities: DashboardOpportunity[];
};
type PendingExecution = {
  title: string;
  action: string;
  targetType: string;
  platform?: string | null;
  payload: Record<string, unknown>;
};
```

- [ ] **Step 2: Add App state**

Inside `App`, near report and data state:

```ts
const [dashboard, setDashboard] = React.useState<DashboardSummary | null>(null);
const [selectedOpportunity, setSelectedOpportunity] = React.useState<DashboardOpportunity | null>(null);
const [pendingExecution, setPendingExecution] = React.useState<PendingExecution | null>(null);
```

- [ ] **Step 3: Add dashboard loader**

Inside `App`, near other loader functions:

```ts
async function loadDashboardSummary() {
  const data = await api<DashboardSummary>("/api/reports/dashboard-summary");
  setDashboard(data);
}
```

Update the initial load function to call it with the other settled requests:

```ts
const [setupResult, configResult, jobsResult, dashboardResult] = await Promise.allSettled([
  api<SetupStatus>("/api/research/setup/status"),
  api<{ platforms: ConfigOption[]; collection_modes: ConfigOption[] }>("/api/research/config/options"),
  api<{ jobs: ResearchJob[] }>("/api/research/jobs"),
  api<DashboardSummary>("/api/reports/dashboard-summary"),
]);
```

After existing result handling:

```ts
if (dashboardResult.status === "fulfilled") {
  setDashboard(dashboardResult.value);
}
```

- [ ] **Step 4: Pass dashboard props to the overview**

Where `GrowthOverviewPage` is rendered, pass:

```tsx
<GrowthOverviewPage
  stats={stats}
  charts={charts}
  jobs={jobs}
  setTab={setTab}
  dashboard={dashboard}
  onRefreshDashboard={loadDashboardSummary}
  onViewOpportunity={setSelectedOpportunity}
  onRequestExecution={(opportunity) => setPendingExecution({
    title: opportunity.name,
    action: opportunity.actions.includes("crawl_now") ? "crawl_now" : "search_now",
    targetType: opportunity.type,
    platform: opportunity.platform,
    payload: opportunity.payload,
  })}
/>
```

- [ ] **Step 5: Run TypeScript build and verify failure**

Run:

```bash
npm.cmd run build
```

Expected:

```text
TypeScript errors because GrowthOverviewPage props have not been updated yet.
```

Do not commit this task until Task 4 updates the component.

## Task 4: Mixed Dashboard Homepage

**Files:**
- Modify: `api/webui/src/main.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Update `GrowthOverviewPage` signature**

Replace the current function signature with:

```ts
function GrowthOverviewPage({
  stats,
  charts,
  jobs,
  setTab,
  dashboard,
  onRefreshDashboard,
  onViewOpportunity,
  onRequestExecution,
}: {
  stats: JobStats | null;
  charts: ChartSummary | null;
  jobs: ResearchJob[];
  setTab: (tab: Tab) => void;
  dashboard: DashboardSummary | null;
  onRefreshDashboard: () => Promise<void>;
  onViewOpportunity: (opportunity: DashboardOpportunity) => void;
  onRequestExecution: (opportunity: DashboardOpportunity) => void;
}) {
```

- [ ] **Step 2: Replace the component body**

Use this body:

```tsx
  const keywordData = charts?.keyword_ranking?.slice(0, 8).map((item) => ({ name: item.keyword, value: item.count })) || [];
  const fallbackDashboard: DashboardSummary = {
    decision: {
      headline: "正在等待数据形成增长判断。",
      confidence: "low",
      sample_status: "insufficient",
      sample_summary: "暂无足够样本。",
      risk_notes: ["请先执行实时发现或导入采集数据。"],
      evidence_count: 0,
    },
    actions: { do_now: [], watch_today: [], defer: [] },
    monitoring: {
      running_jobs: jobs.filter((job) => job.status === "running").length,
      today_collected: (stats?.posts || 0) + (stats?.comments || 0),
      errors: 0,
      monitor_pools: 0,
      realtime_jobs: 0,
      last_updated_at: null,
    },
    opportunities: [],
  };
  const model = dashboard || fallbackDashboard;
  return (
    <section className="growth-workspace">
      <div className="boss-dashboard-grid">
        <DecisionSummaryPanel decision={model.decision} onRefresh={onRefreshDashboard} />
        <ActionSuggestionPanel actions={model.actions} setTab={setTab} />
      </div>
      <MonitoringCards monitoring={model.monitoring} jobs={jobs} stats={stats} />
      <div className="boss-dashboard-grid wide-main">
        <OpportunityBoard
          opportunities={model.opportunities}
          onView={onViewOpportunity}
          onExecute={onRequestExecution}
        />
        <ChartCard title="关键词样本分布" subtitle="真实采集数据" empty={!keywordData.length}>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={keywordData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="value" fill="#04786f" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Add panel components below `GrowthOverviewPage`**

Add:

```tsx
function DecisionSummaryPanel({ decision, onRefresh }: { decision: DashboardSummary["decision"]; onRefresh: () => Promise<void> }) {
  return (
    <section className="panel decision-panel">
      <div className="panel-head">
        <div>
          <h2>今日增长判断</h2>
          <p>{decision.sample_summary}</p>
        </div>
        <button type="button" onClick={onRefresh}><RefreshCw size={16} />刷新</button>
      </div>
      <h3>{decision.headline}</h3>
      <div className="decision-meta">
        <span className={`confidence-chip ${decision.confidence}`}>置信度：{labelConfidence(decision.confidence)}</span>
        <span className={`sample-chip ${decision.sample_status}`}>样本：{labelSampleStatus(decision.sample_status)}</span>
        <span>证据 {decision.evidence_count} 条</span>
      </div>
      {decision.risk_notes.length > 0 && (
        <ul className="risk-list">
          {decision.risk_notes.map((item) => <li key={item}>{item}</li>)}
        </ul>
      )}
    </section>
  );
}

function ActionSuggestionPanel({ actions, setTab }: { actions: DashboardSummary["actions"]; setTab: (tab: Tab) => void }) {
  const groups = [
    { title: "立刻执行", items: actions.do_now, empty: "暂无必须立即执行的动作。" },
    { title: "今天观察", items: actions.watch_today, empty: "暂无需要重点观察的对象。" },
    { title: "暂缓动作", items: actions.defer, empty: "暂无暂缓项。" },
  ];
  return (
    <section className="panel action-panel">
      <div className="panel-head">
        <div>
          <h2>今日行动建议</h2>
          <p>结论转成运营可以执行的动作。</p>
        </div>
        <button type="button" onClick={() => setTab("report")}><FileText size={16} />报告中心</button>
      </div>
      <div className="action-groups">
        {groups.map((group) => (
          <div className="action-group" key={group.title}>
            <strong>{group.title}</strong>
            {(group.items.length ? group.items : [{ title: group.empty, reason: "", action: "view_detail", target_type: "empty", payload: {} }]).map((item) => (
              <div className="action-row" key={`${group.title}:${item.title}`}>
                <span>{item.title}</span>
                {item.reason && <small>{item.reason}</small>}
              </div>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

function MonitoringCards({ monitoring, jobs, stats }: { monitoring: DashboardSummary["monitoring"]; jobs: ResearchJob[]; stats: JobStats | null }) {
  const cards = [
    { label: "运行任务", value: monitoring.running_jobs || jobs.filter((job) => job.status === "running").length },
    { label: "今日采集", value: monitoring.today_collected || ((stats?.posts || 0) + (stats?.comments || 0)) },
    { label: "异常数", value: monitoring.errors },
    { label: "监控池", value: monitoring.monitor_pools },
  ];
  return (
    <section className="monitoring-cards">
      {cards.map((item) => (
        <div className="metric-card compact" key={item.label}>
          <span>{item.label}</span>
          <strong>{formatNumber(Number(item.value || 0))}</strong>
        </div>
      ))}
    </section>
  );
}

function OpportunityBoard({ opportunities, onView, onExecute }: { opportunities: DashboardOpportunity[]; onView: (item: DashboardOpportunity) => void; onExecute: (item: DashboardOpportunity) => void }) {
  return (
    <section className="panel opportunity-panel">
      <div className="panel-head">
        <div>
          <h2>综合机会榜</h2>
          <p>达人、关键词、友商和内容按综合机会分排序。</p>
        </div>
        <span>{opportunities.length} 条</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>类型</th>
              <th>名称</th>
              <th>总分</th>
              <th>24h</th>
              <th>7d</th>
              <th>原因</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {opportunities.map((item) => (
              <tr key={item.id}>
                <td><span className="type-chip">{labelOpportunityType(item.type)}</span></td>
                <td><strong>{item.name}</strong><small>{labelPlatform(item.platform || undefined)}</small></td>
                <td><strong>{Math.round(item.score)}</strong></td>
                <td>{formatSigned(item.change_24h)}</td>
                <td>{formatSigned(item.trend_7d)}</td>
                <td>{item.reason}</td>
                <td>
                  <div className="table-actions">
                    <button type="button" onClick={() => onView(item)}>详情</button>
                    <button type="button" onClick={() => onExecute(item)}>立即执行</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!opportunities.length && <EmptyState title="暂无机会榜数据" body="先完成实时发现、关键词热度或友商组成快照。" />}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Add label helpers**

Near existing helper functions:

```ts
const labelConfidence = (value: DashboardConfidence) => ({ low: "低", medium: "中", high: "高" }[value]);
const labelSampleStatus = (value: DashboardSampleStatus) => ({ insufficient: "不足", limited: "有限", enough: "充足" }[value]);
const labelOpportunityType = (value: DashboardOpportunity["type"]) => ({ creator: "达人", keyword: "关键词", competitor: "友商", content: "内容" }[value]);
const formatSigned = (value: number) => `${value > 0 ? "+" : ""}${Number(value || 0).toFixed(1)}`;
```

- [ ] **Step 5: Add CSS**

Append to `api/webui/src/styles.css`:

```css
.boss-dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 16px;
}

.boss-dashboard-grid.wide-main {
  grid-template-columns: minmax(0, 1.45fr) minmax(340px, 0.55fr);
}

.decision-panel h3 {
  margin: 12px 0;
  font-size: 22px;
  line-height: 1.35;
}

.decision-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  color: #52615f;
}

.confidence-chip,
.sample-chip,
.type-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 4px 9px;
  background: #eef5f3;
  color: #04786f;
  font-size: 12px;
  font-weight: 700;
}

.confidence-chip.low,
.sample-chip.insufficient {
  background: #fff2df;
  color: #b45309;
}

.confidence-chip.high,
.sample-chip.enough {
  background: #d7f0ec;
  color: #04786f;
}

.risk-list {
  margin: 14px 0 0;
  padding-left: 18px;
  color: #7c4a03;
}

.action-groups {
  display: grid;
  gap: 12px;
}

.action-group {
  border: 1px solid #e2e8e5;
  border-radius: 8px;
  padding: 10px;
}

.action-row {
  display: grid;
  gap: 3px;
  margin-top: 8px;
  color: #253331;
}

.action-row small {
  color: #64716f;
}

.monitoring-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.metric-card.compact {
  min-height: 92px;
}

.opportunity-panel td {
  vertical-align: top;
}

@media (max-width: 1120px) {
  .boss-dashboard-grid,
  .boss-dashboard-grid.wide-main,
  .monitoring-cards {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 6: Run frontend build**

Run:

```bash
npm.cmd run build
```

Expected:

```text
✓ built
```

- [ ] **Step 7: Commit Tasks 3 and 4**

Run:

```bash
git add api/webui/src/main.tsx api/webui/src/styles.css
git commit -m "feat: render boss dashboard overview"
```

## Task 5: Opportunity Detail Drawer

**Files:**
- Modify: `api/webui/src/main.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Render drawer from `App`**

Near the bottom of `App` render, before the job drawer, add:

```tsx
{selectedOpportunity && (
  <OpportunityDetailDrawer
    opportunity={selectedOpportunity}
    onClose={() => setSelectedOpportunity(null)}
    onExecute={(item) => setPendingExecution({
      title: item.name,
      action: item.actions.includes("crawl_now") ? "crawl_now" : "search_now",
      targetType: item.type,
      platform: item.platform,
      payload: item.payload,
    })}
  />
)}
```

- [ ] **Step 2: Add drawer component**

Add below `OpportunityBoard`:

```tsx
function OpportunityDetailDrawer({ opportunity, onClose, onExecute }: { opportunity: DashboardOpportunity; onClose: () => void; onExecute: (item: DashboardOpportunity) => void }) {
  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside className="opportunity-drawer" role="dialog" aria-modal="true" aria-label="机会详情" onClick={(event) => event.stopPropagation()}>
        <div className="drawer-head">
          <div>
            <span className="type-chip">{labelOpportunityType(opportunity.type)}</span>
            <h2>{opportunity.name}</h2>
            <p>{labelPlatform(opportunity.platform || undefined)} / 综合分 {Math.round(opportunity.score)}</p>
          </div>
          <button type="button" onClick={onClose}><X size={18} /></button>
        </div>
        <section className="drawer-section">
          <h3>核心原因</h3>
          <p>{opportunity.reason}</p>
        </section>
        <section className="drawer-section">
          <h3>24h / 7d / 30d</h3>
          <div className="drawer-metrics">
            <MiniStat value={Number(opportunity.change_24h).toFixed(1)} label="24h 变化" />
            <MiniStat value={Number(opportunity.trend_7d).toFixed(1)} label="7d 趋势" />
            <MiniStat value={opportunity.detail.trend_30d.length} label="30d 样本" />
          </div>
        </section>
        <section className="drawer-section">
          <h3>证据摘要</h3>
          {(opportunity.detail.summary || []).map((item) => <p key={item}>{item}</p>)}
          <pre className="console-output">{JSON.stringify(opportunity.detail.evidence || {}, null, 2)}</pre>
        </section>
        <div className="drawer-actions">
          <button type="button" onClick={onClose}>关闭</button>
          <button className="primary" type="button" onClick={() => onExecute(opportunity)}><Play size={16} />立即执行</button>
        </div>
      </aside>
    </div>
  );
}
```

- [ ] **Step 3: Add drawer CSS**

Append:

```css
.drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: rgba(8, 18, 24, 0.28);
  display: flex;
  justify-content: flex-end;
}

.opportunity-drawer {
  width: min(520px, 100vw);
  height: 100%;
  background: #ffffff;
  box-shadow: -24px 0 50px rgba(15, 23, 42, 0.18);
  padding: 22px;
  overflow: auto;
}

.drawer-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  border-bottom: 1px solid #e2e8e5;
  padding-bottom: 16px;
}

.drawer-head h2 {
  margin: 10px 0 4px;
}

.drawer-section {
  padding: 16px 0;
  border-bottom: 1px solid #edf2ef;
}

.drawer-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.drawer-actions {
  position: sticky;
  bottom: 0;
  background: #ffffff;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 16px;
}
```

- [ ] **Step 4: Run frontend build**

Run:

```bash
npm.cmd run build
```

Expected:

```text
✓ built
```

- [ ] **Step 5: Commit Task 5**

Run:

```bash
git add api/webui/src/main.tsx api/webui/src/styles.css
git commit -m "feat: add opportunity detail drawer"
```

## Task 6: Lightweight Execution Confirmation Modal

**Files:**
- Modify: `api/webui/src/main.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Add execution handler**

Inside `App`, add:

```ts
async function confirmDashboardExecution() {
  if (!pendingExecution) return;
  if (pendingExecution.targetType === "keyword") {
    const keyword = String(pendingExecution.payload.keyword || "");
    const platform = pendingExecution.platform ? [pendingExecution.platform] : [];
    const data = await api<Record<string, unknown>>("/api/content-tracking/realtime-discovery", {
      method: "POST",
      body: JSON.stringify({ keywords: [keyword].filter(Boolean), platforms: platform, realtime: true }),
    });
    setActivityOutput(JSON.stringify(data, null, 2));
  } else if (pendingExecution.targetType === "creator") {
    const pool = monitorPools[0];
    if (!pool) {
      setActivityOutput("请先创建监控池，再从首页加入达人并立即爬取。");
      setPendingExecution(null);
      return;
    }
    await addCreatorsToMonitorPool(pool.id, {
      crawl_now: true,
      creators: [{
        platform: pendingExecution.platform,
        creator_id: pendingExecution.payload.creator_id,
        display_name: pendingExecution.payload.display_name,
        source: "dashboard",
      }],
    });
  } else if (pendingExecution.targetType === "competitor") {
    const competitorId = pendingExecution.payload.competitor_id;
    const data = await api<Record<string, unknown>>(`/api/competitors/${competitorId}/composition/rebuild`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    setActivityOutput(JSON.stringify(data, null, 2));
  } else if (pendingExecution.targetType === "content") {
    const data = await api<Record<string, unknown>>("/api/content-tracking/realtime-discovery", {
      method: "POST",
      body: JSON.stringify({ keywords: [], platforms: pendingExecution.platform ? [pendingExecution.platform] : [], realtime: true }),
    });
    setActivityOutput(JSON.stringify(data, null, 2));
  }
  setPendingExecution(null);
  await loadDashboardSummary();
}
```

- [ ] **Step 2: Render modal from `App`**

Near the drawer render:

```tsx
{pendingExecution && (
  <ConfirmExecutionModal
    execution={pendingExecution}
    onCancel={() => setPendingExecution(null)}
    onConfirm={confirmDashboardExecution}
  />
)}
```

- [ ] **Step 3: Add modal component**

Add below `OpportunityDetailDrawer`:

```tsx
function ConfirmExecutionModal({ execution, onCancel, onConfirm }: { execution: PendingExecution; onCancel: () => void; onConfirm: () => Promise<void> }) {
  const [busy, setBusy] = React.useState(false);
  async function submit() {
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="confirm-modal" role="dialog" aria-modal="true" aria-label="确认执行">
        <div className="panel-head">
          <div>
            <h2>确认执行外部采集</h2>
            <p>真实平台搜索或主页采集可能消耗额度，并受平台风控影响。</p>
          </div>
          <button type="button" onClick={onCancel}><X size={18} /></button>
        </div>
        <div className="confirm-grid">
          <span>对象</span><strong>{execution.title}</strong>
          <span>类型</span><strong>{labelOpportunityType(execution.targetType as DashboardOpportunity["type"])}</strong>
          <span>平台</span><strong>{labelPlatform(execution.platform || undefined)}</strong>
          <span>动作</span><strong>{execution.action === "crawl_now" ? "立即爬取" : "立即搜索"}</strong>
        </div>
        <pre className="console-output">{JSON.stringify(execution.payload, null, 2)}</pre>
        <div className="button-row right">
          <button type="button" onClick={onCancel} disabled={busy}>取消</button>
          <button className="primary" type="button" onClick={submit} disabled={busy}>
            {busy ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
            确认执行
          </button>
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Add modal CSS**

Append:

```css
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  background: rgba(8, 18, 24, 0.32);
  padding: 20px;
}

.confirm-modal {
  width: min(560px, 100%);
  background: #ffffff;
  border-radius: 10px;
  padding: 18px;
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.2);
}

.confirm-grid {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 10px 14px;
  margin: 14px 0;
}

.confirm-grid span {
  color: #64716f;
}

.button-row.right {
  justify-content: flex-end;
}

.spin {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
```

- [ ] **Step 5: Run frontend build**

Run:

```bash
npm.cmd run build
```

Expected:

```text
✓ built
```

- [ ] **Step 6: Commit Task 6**

Run:

```bash
git add api/webui/src/main.tsx api/webui/src/styles.css
git commit -m "feat: confirm dashboard execution actions"
```

## Task 7: Browser Smoke Test

**Files:**
- No source files expected.

- [ ] **Step 1: Build frontend**

Run:

```bash
npm.cmd run build
```

Expected:

```text
✓ built
```

- [ ] **Step 2: Run focused backend tests**

Run:

```bash
python -m pytest tests\test_dashboard_summary.py tests\test_dashboard_api.py tests\test_content_tracking_api.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Start a temporary API server**

Use an unused port such as `8084`:

```bash
python -m uvicorn api.main:app --host 127.0.0.1 --port 8084
```

Expected:

```text
Uvicorn running on http://127.0.0.1:8084
```

- [ ] **Step 4: Visit `/research` in a browser**

Open:

```text
http://127.0.0.1:8084/research
```

Expected:

- First screen shows 今日增长判断.
- First screen shows 今日行动建议.
- Monitoring cards show at least 4 cards.
- 综合机会榜 renders either rows or an empty state.
- No React runtime error appears in browser console.

- [ ] **Step 5: Test drawer behavior**

If opportunity rows exist:

1. Click `详情`.
2. Confirm drawer opens.
3. Confirm drawer shows type, score, reason, evidence JSON.
4. Close drawer.

If no rows exist:

1. Confirm empty state copy is visible.
2. Confirm page still shows decision summary.

- [ ] **Step 6: Test confirmation modal behavior**

If opportunity rows exist:

1. Click `立即执行`.
2. Confirm modal opens.
3. Click `取消`.
4. Confirm modal closes and no API call starts.

If no rows exist, skip this step and record: `Skipped because no opportunities were present in local data`.

- [ ] **Step 7: Stop temporary server**

Stop the process started in Step 3 with `Ctrl+C`, or kill that exact process id if it was launched in the background.

## Task 8: Final Regression and Delivery Notes

**Files:**
- No source files expected unless tests reveal a defect.

- [ ] **Step 1: Run complete focused test set**

Run:

```bash
python -m pytest tests\test_dashboard_summary.py tests\test_dashboard_api.py tests\test_tikhub_endpoints.py tests\test_creator_discovery_postprocess.py tests\test_creator_discovery_scoring.py tests\test_monitor_pools.py tests\test_keyword_heat.py tests\test_keyword_heat_dual_track.py tests\test_keyword_opportunities.py tests\test_competitor_composition.py tests\test_content_tracking_api.py tests\test_account_profiles.py tests\test_research_models.py tests\test_research_schema_migration.py tests\test_growth_intelligence_models.py tests\test_growth_intelligence_repository.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run frontend production build**

Run:

```bash
npm.cmd run build
```

Expected:

```text
✓ built
```

The existing Vite large chunk warning is acceptable for this task.

- [ ] **Step 3: Check git status**

Run:

```bash
git status --short
```

Expected:

- Only intentional dashboard files are modified or added.
- Existing unrelated dirty files remain untouched.

- [ ] **Step 4: Final commit if needed**

If fixes were made after Task 6:

```bash
git add research/dashboard.py api/routers/reports.py tests/test_dashboard_summary.py tests/test_dashboard_api.py api/webui/src/main.tsx api/webui/src/styles.css
git commit -m "fix: stabilize boss dashboard display"
```

- [ ] **Step 5: Delivery summary**

Report:

- Backend endpoint added: `/api/reports/dashboard-summary`.
- Frontend homepage now shows decision summary, actions, monitoring cards, and opportunity board.
- Detail drawer and confirmation modal are implemented.
- Tests run and results.
- Any skipped browser step due to missing local sample data.

## Self-Review

Spec coverage:

- Mixed homepage: Task 4.
- Boss-facing decision summary: Task 1 and Task 4.
- Conservative sample-state handling: Task 1.
- 24h + 7d homepage, 30d drawer slot: Task 1 and Task 5.
- Balanced opportunity score: Task 1.
- One-sentence opportunity reason: Task 1 and Task 4.
- View detail: Task 5.
- Monitor / immediate execution action path: Task 6.
- Lightweight confirmation modal: Task 6.
- Tests and build verification: Tasks 1, 2, 7, 8.

Placeholder scan:

- The plan contains no placeholder markers or undefined deferred-work instructions.
- Each code-changing task includes exact file paths and concrete code.

Type consistency:

- `DashboardSummary`, `DashboardOpportunity`, `DashboardAction`, and `PendingExecution` match the backend response fields.
- Frontend action names use existing strings: `view_detail`, `monitor`, `crawl_now`, `search_now`.
